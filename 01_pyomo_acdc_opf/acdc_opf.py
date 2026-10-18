"""
An AC/DC optimal power flow for the PCS3750C-MV reference, in Pyomo with Ipopt.

Built from the reference's spec (refs/<name>.spec.json), not from Electrisim's internal network:
  AC   - the utility POI, each block's 505 V grid- and load-side buses, the 34.5 kV backbone ring and
         its hall feeders; lines as pi sections, transformers as a series impedance with their iron
         loss and magnetising current (pandapower's defaults Electrisim filled in: 2.25 kW, 0.1 %);
         polar power flow, per unit on 1 MVA.
  DC   - each block's four DC buses, a node each: its AFE's DC power and its batteries' (held at
         nothing unless --batteries) feed its grid-forming inverter's DC input.
  AFE  - a VSC: its reactor's loss r (P^2 + Q^2) / V^2; its MVA within its rating times min(V, 1)
         (current-limited below nominal voltage, as the specification's derating has it).
  GFM  - a grid-forming PCS: 98.5 % efficient; P >= 0; within its rating times min(V, 1); |Q| at most
         its q_max_percent of its rating (the 0.6 S cap).
  SST  - each hall's racks through its 99 % DC/DC and 98.5 % rectifier, each with its 7 kW no-load loss:
         a constant-power load at its MV bus.

Modes:
  --mode lf     fix the controls as Electrisim's load flow has them (AFE Q = 0, the inverters sharing
                equally, each load-side bus at Electrisim's voltage) - a check of the model;
  --mode opf    minimise the utility's import (the network's losses), every control free;
  --mode shed   maximise the racks served (each hall from 0 to its full load), then minimise losses.
  --out B3      take Block 3's four inverters out of service (as Electrisim's test does).
"""
import argparse
import cmath
import json
import math
import os

import pyomo.environ as pyo

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)
IPOPT = os.path.join(LAB, 'data', 'ipopt', 'Ipopt-3.14.20-win64-msvs2022-md', 'bin', 'ipopt.exe')
SB = 1.0                     # MVA base
F_HZ = 60.0
PFE_KW, I0_PCT = 2.25, 0.1   # the transformers' iron loss and magnetising current, as Electrisim's builder sets them
V_MIN, V_MAX = 0.9, 1.1
BAT_PRICE = 2.0              # stored energy against the grid's, in the objective


def derate(curve, inlet):
    """The rating factor at an inlet temperature: linear between the curve's points ('35:1.10, 45:1.00, ...')."""
    pts = sorted((float(a), float(b)) for a, b in (x.split(':') for x in curve.split(',')))
    if inlet <= pts[0][0]:
        return pts[0][1]
    for (t0, f0), (t1, f1) in zip(pts, pts[1:]):
        if inlet <= t1:
            return f0 + (f1 - f0) * (inlet - t0) / (t1 - t0)
    return pts[-1][1]


def build(spec, mode, out_blocks=(), batteries=False, rack_scale=1.0, branch_limits=True, trafo_factor=1.0):
    vn = {b['id']: b['vn_kv'] for b in spec['buses']}
    buses = list(vn)
    m = pyo.ConcreteModel()
    m.B = pyo.Set(initialize=buses)

    # Branches: (from, to, series y, shunt y at from, shunt y at to, rating MVA or None)
    branches = []
    for l in spec['lines']:
        zb = vn[l['from_bus']] ** 2 / SB
        z = complex(l['r_ohm_per_km'], l['x_ohm_per_km']) * l['length_km'] / zb
        bsh = 2 * math.pi * F_HZ * l['c_nf_per_km'] * 1e-9 * l['length_km'] * zb
        branches.append((l['id'], l['from_bus'], l['to_bus'], 1 / z, 0.5j * bsh, 0.5j * bsh,
                         math.sqrt(3) * vn[l['from_bus']] * l['max_i_ka']))
    for t in spec['transformers']:
        sn = t['sn_mva']
        zk, rk = t['vk_percent'] / 100 * SB / sn, t['vkr_percent'] / 100 * SB / sn
        z = complex(rk, math.sqrt(zk ** 2 - rk ** 2))
        g = PFE_KW / 1000 / SB
        y0 = I0_PCT / 100 * sn / SB
        ym = complex(g, -math.sqrt(max(y0 ** 2 - g ** 2, 0.0)))
        branches.append((t['id'], t['hv_bus'], t['lv_bus'], 1 / z, ym, 0j, sn))
    m.L = pyo.Set(initialize=[b[0] for b in branches])
    br = {b[0]: b for b in branches}

    m.V = pyo.Var(m.B, bounds=(V_MIN, V_MAX), initialize=1.0)
    m.th = pyo.Var(m.B, bounds=(-math.pi / 2, math.pi / 2), initialize=0.0)
    # Angle references: the utility side, and the inverter island (its first load-side bus in service).
    m.th['POI'].fix(0.0)
    grid = spec['external_grids'][0]
    m.V[grid['bus']].fix(grid.get('vm_pu', 1.0))

    # Branch flows at each end (MW, Mvar).
    def flows(l, end):
        _, f, t, ys, yf, yt, _ = br[l]
        a, b = (f, t) if end == 'f' else (t, f)
        ysh = yf if end == 'f' else yt
        g, bb = ys.real, ys.imag
        gs, bs = ysh.real, ysh.imag
        va, vb, d = m.V[a], m.V[b], m.th[a] - m.th[b]
        p = (g + gs) * va ** 2 - va * vb * (g * pyo.cos(d) + bb * pyo.sin(d))
        q = -(bb + bs) * va ** 2 - va * vb * (g * pyo.sin(d) - bb * pyo.cos(d))
        return p, q

    m.pf = pyo.Expression(m.L, rule=lambda m, l: flows(l, 'f')[0])
    m.qf = pyo.Expression(m.L, rule=lambda m, l: flows(l, 'f')[1])
    m.pt = pyo.Expression(m.L, rule=lambda m, l: flows(l, 't')[0])
    m.qt = pyo.Expression(m.L, rule=lambda m, l: flows(l, 't')[1])
    m.rate = pyo.ConstraintList()
    for l in (m.L if branch_limits else []):
        s = br[l][6] * (trafo_factor if l.endswith(('_T1', '_T2')) else 1.0)
        for p, q, bus in ((m.pf[l], m.qf[l], br[l][1]), (m.pt[l], m.qt[l], br[l][2])):
            m.rate.add(p ** 2 + q ** 2 <= (s * m.V[bus]) ** 2 * 1.0)

    # The utility.
    m.Pg = pyo.Var(initialize=11.0)
    m.Qg = pyo.Var(initialize=0.5)

    # Converters, by DC bus.
    pcs = [p for p in spec['pcs'] if p['id'][:2] not in out_blocks]
    afe = spec['vscs']
    m.A = pyo.Set(initialize=[a['id'] for a in afe])
    m.G = pyo.Set(initialize=[p['id'] for p in pcs])
    A, G = {a['id']: a for a in afe}, {p['id']: p for p in pcs}
    s_afe = {a: A[a]['rated_mva'] * derate(A[a]['derate_temp_curve'], A[a]['inlet_c']) for a in m.A}
    s_gfm = {g: G[g]['s_rated_mva'] * derate(G[g]['derate_temp_curve'], G[g]['inlet_c']) for g in m.G}
    r_afe = {a: A[a]['r_ohm'] / (vn[A[a]['bus']] ** 2 / SB) for a in m.A}
    eta = {g: G[g]['efficiency_percent'] / 100 for g in m.G}

    m.Pa = pyo.Var(m.A, initialize=0.96)            # AFE, AC side (into it)
    m.Qa = pyo.Var(m.A, initialize=0.0)
    m.ua = pyo.Var(m.A, bounds=(0, 1), initialize=1.0)
    m.Pi = pyo.Var(m.G, bounds=(0, None), initialize=0.93)   # GFM, AC side (out of it)
    m.Qi = pyo.Var(m.G, initialize=0.04)
    m.ui = pyo.Var(m.G, bounds=(0, 1), initialize=1.0)
    m.conv = pyo.ConstraintList()
    for a in m.A:
        m.conv.add(m.ua[a] <= m.V[A[a]['bus']])
        m.conv.add(m.Pa[a] ** 2 + m.Qa[a] ** 2 <= (s_afe[a] * m.ua[a]) ** 2)
    for g in m.G:
        m.conv.add(m.ui[g] <= m.V[G[g]['bus']])
        m.conv.add(m.Pi[g] ** 2 + m.Qi[g] ** 2 <= (s_gfm[g] * m.ui[g]) ** 2)
        qcap = G[g].get('q_max_percent', 100) / 100 * s_gfm[g]
        m.Qi[g].setlb(-qcap)
        m.Qi[g].setub(qcap)

    # DC buses: AFE's DC power + batteries = the inverter's DC input.
    bat = {}
    for b in spec['batteries']:
        bat.setdefault(b['bus'], []).append(b)
    dc_buses = sorted({a['bus_dc'] for a in afe})
    m.D = pyo.Set(initialize=dc_buses)
    bat_dis = {d: sum(b['capacity_kwh'] / 1000 * b['c_rate_discharge'] for b in bat.get(d, [])) for d in dc_buses}
    bat_ch = {d: sum(b['capacity_kwh'] / 1000 * b['c_rate_charge'] for b in bat.get(d, [])) for d in dc_buses}
    # Discharge and charge apart, so the stored energy can be priced (a store is not a free source).
    m.Pdis = pyo.Var(m.D, bounds=lambda m, d: (0, bat_dis[d] if batteries else 0), initialize=0.0)
    m.Pch = pyo.Var(m.D, bounds=lambda m, d: (0, bat_ch[d] if batteries else 0), initialize=0.0)
    m.Pb = pyo.Expression(m.D, rule=lambda m, d: m.Pdis[d] - m.Pch[d])
    m.dc = pyo.ConstraintList()
    for d in dc_buses:
        a_dc = sum(m.Pa[a] - r_afe[a] * (m.Pa[a] ** 2 + m.Qa[a] ** 2) / m.V[A[a]['bus']] ** 2 for a in m.A if A[a]['bus_dc'] == d)
        g_dc = sum(m.Pi[g] / eta[g] for g in m.G if G[g]['bus_dc'] == d)
        m.dc.add(a_dc + m.Pb[d] == g_dc)

    # SSTs and their racks.
    racks = {r['bus']: r for r in spec['dc_loads']}
    sst = {s['bus_mv']: s for s in spec['ssts']}
    m.H = pyo.Set(initialize=list(sst))
    full = {h: racks[sst[h]['bus_lv_dc']]['p_mw'] * rack_scale for h in m.H}
    m.Pr = pyo.Var(m.H, bounds=lambda m, h: (0, full[h]), initialize=lambda m, h: full[h])
    if mode != 'shed':
        for h in m.H:
            m.Pr[h].fix(full[h])

    def sst_mv(h):
        s = sst[h]
        dc_in = m.Pr[h] / (s['dcdc_efficiency_percent'] / 100) + s['dcdc_no_load_kw'] / 1000
        return dc_in / (s['rect_efficiency_percent'] / 100) + s['rect_no_load_kw'] / 1000

    # Bus balances: generation - load = flows out.
    m.bal = pyo.ConstraintList()
    for bus in buses:
        p_out = sum(m.pf[l] for l in m.L if br[l][1] == bus) + sum(m.pt[l] for l in m.L if br[l][2] == bus)
        q_out = sum(m.qf[l] for l in m.L if br[l][1] == bus) + sum(m.qt[l] for l in m.L if br[l][2] == bus)
        p_in, q_in = 0, 0
        if bus == grid['bus']:
            p_in, q_in = p_in + m.Pg, q_in + m.Qg
        p_in -= sum(m.Pa[a] for a in m.A if A[a]['bus'] == bus)
        q_in -= sum(m.Qa[a] for a in m.A if A[a]['bus'] == bus)
        p_in += sum(m.Pi[g] for g in m.G if G[g]['bus'] == bus)
        q_in += sum(m.Qi[g] for g in m.G if G[g]['bus'] == bus)
        if bus in sst:
            p_in -= sst_mv(bus)
        m.bal.add(p_in == p_out)
        m.bal.add(q_in == q_out)

    # The inverter island's angle reference: the first load-side bus with an inverter.
    ref = next(G[g]['bus'] for g in m.G)
    m.th[ref].fix(0.0)

    if mode == 'lf':
        # Electrisim's load flow: AFEs at no Q, the inverters sharing P and Q equally, each load-side bus
        # at Electrisim's voltage.
        for a in m.A:
            m.Qa[a].fix(0.0)
        gs = list(m.G)
        m.share = pyo.ConstraintList()
        for g in gs[1:]:
            m.share.add(m.Pi[g] == m.Pi[gs[0]])
            m.share.add(m.Qi[g] == m.Qi[gs[0]])
        m.Pg.setlb(None)
        m.obj = pyo.Objective(expr=0.0)
    else:
        # A data center imports: no export at the POI. Stored energy costs more than the grid's
        # (BAT_PRICE times), so the batteries discharge only where the network needs them.
        m.Pg.setlb(0.0)
        energy = m.Pg + BAT_PRICE * sum(m.Pdis[d] for d in m.D)
        if mode == 'opf':
            m.obj = pyo.Objective(expr=energy)
        else:
            shed = [full[h] - m.Pr[h] for h in m.H]
            # Most racks served; then the least energy; a small square to spread any shed evenly.
            m.obj = pyo.Objective(expr=100 * sum(shed) + energy + 0.01 * sum(s ** 2 for s in shed))
    m.meta = {'br': br, 'A': A, 'G': G, 's_afe': s_afe, 's_gfm': s_gfm, 'full': full, 'sst_mv': sst_mv}
    return m


def solve(m, tee=False):
    res = pyo.SolverFactory('ipopt', executable=IPOPT).solve(m, tee=tee)
    return str(res.solver.termination_condition)


def report(m, label):
    v = lambda x: pyo.value(x)
    meta = m.meta
    out = {
        'case': label,
        'grid_p_mw': round(v(m.Pg), 4), 'grid_q_mvar': round(v(m.Qg), 4),
        'racks_served_mw': round(sum(v(m.Pr[h]) for h in m.H), 4),
        'racks_shed_mw': {h: round(meta['full'][h] - v(m.Pr[h]), 4) for h in m.H},
        'gfm_p_mw': sorted({round(v(m.Pi[g]), 4) for g in m.G}),
        'gfm_q_mvar': sorted({round(v(m.Qi[g]), 4) for g in m.G}),
        'gfm_loading_pct': round(max(math.hypot(v(m.Pi[g]), v(m.Qi[g])) / meta['s_gfm'][g] * 100 for g in m.G), 2),
        'afe_p_mw': sorted({round(v(m.Pa[a]), 4) for a in m.A}),
        'afe_q_mvar': sorted({round(v(m.Qa[a]), 4) for a in m.A}),
        'battery_mw': round(sum(v(m.Pb[d]) for d in m.D), 4),
        'trafo_loading_pct': {l: round(max(math.hypot(v(m.pf[l]), v(m.qf[l])) / v(m.V[meta['br'][l][1]]),
                                            math.hypot(v(m.pt[l]), v(m.qt[l])) / v(m.V[meta['br'][l][2]])) / meta['br'][l][6] * 100, 1)
                              for l in m.L if l.endswith(('_T1', '_T2'))},
        'v_pu': {b: round(v(m.V[b]), 4) for b in m.B},
    }
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--ref', default='reference_pcs3750_mv')
    ap.add_argument('--mode', choices=('lf', 'opf', 'shed'), default='opf')
    ap.add_argument('--out', nargs='*', default=[], help='blocks whose inverters are out, e.g. B3')
    ap.add_argument('--batteries', action='store_true', help='let the batteries discharge or charge')
    ap.add_argument('--fix-load-v', type=float, default=None, help='lf mode: each load-side bus at this voltage')
    ap.add_argument('--no-branch-limits', action='store_true', help="leave the lines' and transformers' ratings out")
    ap.add_argument('--trafo-factor', type=float, default=1.0, help="the transformers' rating times this (an overload)")
    args = ap.parse_args()
    with open(os.path.join(LAB, 'refs', f'{args.ref}.spec.json'), encoding='utf-8') as fh:
        spec = json.load(fh)
    m = build(spec, args.mode, tuple(args.out), args.batteries,
              branch_limits=not args.no_branch_limits and args.mode != 'lf', trafo_factor=args.trafo_factor)
    if args.mode == 'lf' and args.fix_load_v:
        for g in m.G:
            m.V[m.meta['G'][g]['bus']].fix(args.fix_load_v)
    status = solve(m)
    print('Ipopt:', status)
    print(json.dumps(report(m, f"{args.ref} {args.mode} out={args.out} batteries={args.batteries}"), indent=1))
