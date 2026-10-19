"""
A SMART-DS substation, solved in OpenDSS at its peak loads, reduced to its medium-voltage network
as a balanced pandapower net - the level Electrisim's site screening works at.

Run with Electrisim's own Python (it has OpenDSSDirect.py and pandapower; nothing is installed):
    ..\\..\\electrisim\\.venv\\Scripts\\python.exe convert_feeder.py <substation folder>

Kept: the source (an external grid at its bus), the substation transformer (at the tap its
regulator settled on), and every line between buses of 1 kV and above, as positive-sequence
sections (Z1 = mean self - mean mutual impedance; a single-phase lateral as its self impedance).
Lumped: each distribution transformer, with the low-voltage network and loads behind it, becomes a
load on its MV bus equal to the power OpenDSS has entering its primary (its losses included).
Writes <substation>.pp.json (pandapower), <substation>.compare.json (pandapower against OpenDSS).
"""
import json
import math
import os
import sys

import numpy as np
import opendssdirect as dss
import pandapower as pp

HERE = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.abspath(sys.argv[1])
NAME = os.path.basename(SUB.rstrip('\\/'))
MV_KV = 1.0                                  # buses at or above this (line to line) are kept
TO_KM = {0: 1.0, 1: 1.609344, 2: 0.3048e-3 * 1000 / 1000 * 0.3048 * 0 + 0.0003048 * 1000 / 1000, 3: 1.0,
         4: 1e-3, 5: 0.3048e-3, 6: 0.0254e-3, 7: 1e-5}   # OpenDSS length units: none, mi, kft, km, m, ft, in, cm
TO_KM[2] = 0.3048                            # kft


def bus_of(term):
    return term.split('.')[0].lower()


dss.Basic.ClearAll()
dss.Text.Command(f'compile "{os.path.join(SUB, "Master.dss")}"')
dss.Text.Command('set mode=snapshot')
dss.Solution.Solve()
assert dss.Solution.Converged(), 'OpenDSS did not converge'
total_p, total_q = (-x / 1000 for x in dss.Circuit.TotalPower())     # MW, Mvar from the source

# Buses: line-to-line base and solved voltage (mean of its phases, pu).
kv_ll, v_dss, xy = {}, {}, {}
for b in dss.Circuit.AllBusNames():
    dss.Circuit.SetActiveBus(b)
    base = dss.Bus.kVBase() * math.sqrt(3)
    kv_ll[b] = base
    mags = dss.Bus.puVmagAngle()[0::2]
    v_dss[b] = float(np.mean(mags)) if mags else float('nan')
    xy[b] = (dss.Bus.X(), dss.Bus.Y())
mv = {b for b, kv in kv_ll.items() if kv >= MV_KV}

net = pp.create_empty_network(name=f'SMART-DS {NAME} (MV reduction)', f_hz=60.0, sn_mva=1.0)
bidx = {}
for b in sorted(mv):
    x, y = xy[b]
    bidx[b] = pp.create_bus(net, vn_kv=round(kv_ll[b], 3), name=b, geodata=(x, y) if (x or y) else None)

# Source.
dss.Vsources.First()
src = bus_of(dss.CktElement.BusNames()[0])
pp.create_ext_grid(net, bidx[src], vm_pu=dss.Vsources.PU(), name='Utility source', s_sc_max_mva=1000, rx_max=0.1)

# Lines between MV buses.
n_lines = 0
i = dss.Lines.First()
while i:
    b1, b2 = bus_of(dss.Lines.Bus1()), bus_of(dss.Lines.Bus2())
    if b1 in mv and b2 in mv and b1 != b2:
        n = dss.Lines.Phases()
        r = np.array(dss.Lines.RMatrix()).reshape(n, n)
        x = np.array(dss.Lines.XMatrix()).reshape(n, n)
        c = np.array(dss.Lines.CMatrix()).reshape(n, n)
        off = ~np.eye(n, dtype=bool)
        z1 = lambda m: float(np.mean(np.diag(m)) - (np.mean(m[off]) if n > 1 else 0.0))
        unit_km = TO_KM.get(dss.Lines.Units(), 1.0)
        length_km = max(dss.Lines.Length() * unit_km, 1e-4)
        per_km = 1.0 / unit_km                    # matrices are per the line's length unit
        if abs(complex(z1(r), z1(x))) * per_km * length_km < 1e-3:
            # A switch or jumper (under 1 mOhm): a closed bus-bus switch, not a near-zero impedance.
            pp.create_switch(net, bidx[b1], bidx[b2], et='b', closed=True, name=dss.Lines.Name())
            i = dss.Lines.Next()
            continue
        pp.create_line_from_parameters(
            net, bidx[b1], bidx[b2], length_km=length_km,
            r_ohm_per_km=max(z1(r) * per_km, 1e-4), x_ohm_per_km=max(z1(x) * per_km, 1e-4),
            c_nf_per_km=max(float(np.mean(np.diag(c)) - (np.mean(c[off]) if n > 1 else 0.0)), 0.0) * per_km,
            max_i_ka=max(dss.Lines.NormAmps(), 1.0) / 1000, name=dss.Lines.Name(),
            parallel=1)
        n_lines += 1
    i = dss.Lines.Next()

# Transformers: MV to MV kept; MV to LV lumped as the load at its primary.
n_lumped, n_trafo = 0, 0
i = dss.Transformers.First()
while i:
    buses = [bus_of(t) for t in dss.CktElement.BusNames()]
    name = dss.Transformers.Name()
    if all(b in mv for b in buses[:2]):
        dss.Transformers.Wdg(1)
        kva, kv_hv = dss.Transformers.kVA(), dss.Transformers.kV()
        r1 = dss.Transformers.R()
        dss.Transformers.Wdg(2)
        kv_lv, tap, r2 = dss.Transformers.kV(), dss.Transformers.Tap(), dss.Transformers.R()
        xhl = dss.Transformers.Xhl()
        vkr = r1 + r2
        pp.create_transformer_from_parameters(
            net, bidx[buses[0]], bidx[buses[1]], sn_mva=kva / 1000, vn_hv_kv=kv_hv, vn_lv_kv=kv_lv * tap,
            vkr_percent=vkr, vk_percent=math.hypot(vkr, xhl), pfe_kw=0.0, i0_percent=0.0, name=name)
        n_trafo += 1
    elif buses[0] in mv:
        powers = dss.CktElement.Powers()                 # kW, kvar per conductor, terminal 1 first
        nc = len(powers) // (2 * len(buses))
        p = sum(powers[0:2 * nc:2]) / 1000
        q = sum(powers[1:2 * nc:2]) / 1000
        pp.create_load(net, bidx[buses[0]], p_mw=p, q_mvar=q, name=f'{name} (lumped)')
        n_lumped += 1
    i = dss.Transformers.Next()

# Loads directly on MV buses.
i = dss.Loads.First()
while i:
    b = bus_of(dss.CktElement.BusNames()[0])
    if b in mv:
        powers = dss.CktElement.Powers()
        pp.create_load(net, bidx[b], p_mw=sum(powers[0::2]) / 1000, q_mvar=sum(powers[1::2]) / 1000, name=dss.Loads.Name())
    i = dss.Loads.Next()

pp.runpp(net, init="dc", max_iteration=100)
diff = [abs(net.res_bus.at[bidx[b], 'vm_pu'] - v_dss[b]) for b in mv if not math.isnan(v_dss[b])]
cmp = {
    'substation': NAME, 'mv_buses': len(mv), 'lines': n_lines, 'mv_transformers': n_trafo,
    'lumped_transformers': n_lumped, 'loads_mw': round(float(net.load.p_mw.sum()), 4),
    'opendss_source_p_mw': round(total_p, 4), 'opendss_source_q_mvar': round(total_q, 4),
    'pandapower_source_p_mw': round(float(net.res_ext_grid.p_mw.sum()), 4),
    'pandapower_source_q_mvar': round(float(net.res_ext_grid.q_mvar.sum()), 4),
    'v_diff_pu_max': round(float(max(diff)), 4), 'v_diff_pu_mean': round(float(np.mean(diff)), 5),
    'v_min_pu': {'opendss': round(min(v_dss[b] for b in mv), 4), 'pandapower': round(float(net.res_bus.vm_pu.min()), 4)},
    'substation_transformer_loading_pct': [round(float(x), 1) for x in net.res_trafo.loading_percent],
}
pp.to_json(net, os.path.join(HERE, f'{NAME}.pp.json'))
with open(os.path.join(HERE, f'{NAME}.compare.json'), 'w', encoding='utf-8') as fh:
    json.dump(cmp, fh, indent=1)
# For a map: each MV bus's coordinates (longitude, latitude) and voltage, and each line's ends.
name_of = {i: b for b, i in bidx.items()}
geo = {'buses': [{'bus': b, 'x': xy[b][0], 'y': xy[b][1], 'vm_pu': round(float(net.res_bus.at[i, 'vm_pu']), 4)}
                 for b, i in bidx.items()],
       'lines': [[name_of[int(f)], name_of[int(t)]] for f, t in zip(net.line.from_bus, net.line.to_bus)]
                + [[name_of[int(s.bus)], name_of[int(s.element)]] for s in net.switch.itertuples() if s.et == 'b'],
       'substation_bus': name_of[int(net.trafo.lv_bus.iloc[0])]}
with open(os.path.join(HERE, f'{NAME}.geo.json'), 'w', encoding='utf-8') as fh:
    json.dump(geo, fh)
print(json.dumps(cmp, indent=1))
