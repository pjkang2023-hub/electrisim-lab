"""
The 800 VDC AI factory's site energy over a year, in PyPSA: the substation battery sized and the
gas turbine and utility dispatched hour by hour, against a tariff - and what the study's back-up
requirement (10 minutes of the whole site from storage) costs net of what the battery earns.

    ..\\.venv\\Scripts\\python.exe factory_year.py            (all cases; writes results.json)

ASSUMPTIONS (stated, not from the whitepaper; change them in CASE_DEFAULTS):
  load      racks at the training cycle's mean, 17.9 MW, flat all year (training clusters run flat);
            cooling 2.65 MW mean, +-30 % by season (peak in July) and +-15 % by hour (peak 15:00)
            - together the 20.55 MW the study's day used.
  utility   up to 40 MW (one 40 MVA 245/34.5 kV transformer, N-1); time-of-use energy price:
            50 $/MWh off-peak (22:00-07:00), 70 mid, 150 on-peak (14:00-20:00, June-September);
            optional demand charge per kW of each month's peak import.
  turbine   35 MW, 60 $/MWh (the study's marginal cost); linear, no minimum load (no unit commitment).
  battery   power (charger and discharger, 96 % each way) and energy sized by the optimiser;
            annualised capital 60,000 $/MW-yr and 25,000 $/MWh-yr (about 450 $/kW and 190 $/kWh at
            an 8 % capital charge over 15 years); no degradation cost.
  back-up   optional: discharger at least the site's peak, energy never below 10 minutes of it.
"""
import json
import os

import numpy as np
import pandas as pd
import pypsa

HERE = os.path.dirname(os.path.abspath(__file__))
HOURS = pd.date_range('2018-01-01', periods=8760, freq='h')

CASE_DEFAULTS = dict(
    racks_mw=17.9, cooling_mw=2.65, grid_mw=40.0, off=50.0, mid=70.0, on=150.0, demand_usd_kw_month=0.0,
    gt_mw=35.0, gt_cost=60.0, bat_mw_cost=60_000.0, bat_mwh_cost=25_000.0, eta=0.96, backup_min=0.0,
    battery=True,
)


def load_profile(c):
    doy = HOURS.dayofyear.values
    hod = HOURS.hour.values
    seasonal = 1 + 0.30 * np.cos(2 * np.pi * (doy - 196) / 365)       # peak about 15 July
    daily = 1 + 0.15 * np.cos(2 * np.pi * (hod - 15) / 24)            # peak at 15:00
    return c['racks_mw'] + c['cooling_mw'] * seasonal * daily


def tariff(c):
    hod, month = HOURS.hour.values, HOURS.month.values
    price = np.full(len(HOURS), c['mid'])
    price[(hod >= 22) | (hod < 7)] = c['off']
    price[(hod >= 14) & (hod < 20) & (month >= 6) & (month <= 9)] = c['on']
    return price


def build(c):
    n = pypsa.Network()
    n.set_snapshots(HOURS)
    n.add('Bus', 'site', carrier='AC')
    load = load_profile(c)
    n.add('Load', 'site load', bus='site', p_set=pd.Series(load, HOURS))
    n.add('Generator', 'utility', bus='site', p_nom=c['grid_mw'], marginal_cost=pd.Series(tariff(c), HOURS))
    n.add('Generator', 'gas turbine', bus='site', p_nom=c['gt_mw'], marginal_cost=c['gt_cost'])
    if c['battery']:
        n.add('Bus', 'battery', carrier='battery')
        n.add('Store', 'battery energy', bus='battery', e_nom_extendable=True, e_cyclic=True,
              capital_cost=c['bat_mwh_cost'])
        n.add('Link', 'battery charger', bus0='site', bus1='battery', efficiency=c['eta'],
              p_nom_extendable=True, capital_cost=c['bat_mw_cost'])
        n.add('Link', 'battery discharger', bus0='battery', bus1='site', efficiency=c['eta'],
              p_nom_extendable=True, capital_cost=0.0,
              p_nom_min=float(load.max()) if c['backup_min'] > 0 else 0.0)
    return n, load


def extra(c, load):
    def f(n, snapshots):
        m = n.model
        if c['battery']:
            # Charger and discharger are one converter: the same rating both ways.
            m.add_constraints(m['Link-p_nom'].loc['battery charger'] == m['Link-p_nom'].loc['battery discharger'],
                              name='battery converter one rating')
            if c['backup_min'] > 0:
                # Back-up: never less than backup_min minutes of the site's peak, delivered through the
                # discharger (energy before its losses).
                reserve = float(load.max()) * c['backup_min'] / 60 / c['eta']
                m.add_constraints(m['Store-e'].loc[:, 'battery energy'] >= reserve, name='backup reserve')
        if c['demand_usd_kw_month'] > 0:
            # Each month's peak import, charged per kW.
            months = sorted(set(HOURS.month))
            peak = m.add_variables(lower=0, coords=[pd.Index(months, name='month')], name='monthly peak')
            p_grid = m['Generator-p'].loc[:, 'utility']
            for mo in months:
                sel = HOURS[HOURS.month == mo]
                m.add_constraints(peak.loc[mo] >= p_grid.loc[sel], name=f'peak {mo}')
            m.objective = m.objective + (peak * (c['demand_usd_kw_month'] * 1000)).sum()
    return f


def run(label, **over):
    return run_network(label, **over)[0]


def run_network(label, **over):
    """The case's summary, its solved network and its hourly series (None when not solved)."""
    c = {**CASE_DEFAULTS, **over}
    n, load = build(c)
    status, cond = n.optimize(solver_name='highs', extra_functionality=extra(c, load), log_to_console=False)
    if status != 'ok':
        return {'case': label, 'status': f'{status}/{cond}'}, None, None
    g = n.generators_t.p
    series = pd.DataFrame({'load': load, 'utility': g['utility'], 'gas turbine': g['gas turbine'],
                           'price': tariff(c)}, index=HOURS)
    if c['battery']:
        series['battery discharge'] = n.links_t.p1['battery discharger'].mul(-1).values
        series['battery charge'] = n.links_t.p0['battery charger'].values
        series['battery energy'] = n.stores_t.e['battery energy'].values
    return _summary(label, c, n, load), n, series


def _summary(label, c, n, load):
    g = n.generators_t.p
    price = tariff(c)
    grid_mwh = float(g['utility'].sum())
    out = {
        'case': label, 'status': 'ok',
        'load_mwh': round(float(load.sum()), 0), 'load_peak_mw': round(float(load.max()), 2),
        'grid_mwh': round(grid_mwh, 0), 'grid_peak_mw': round(float(g['utility'].max()), 2),
        'gt_mwh': round(float(g['gas turbine'].sum()), 0),
        'gt_full_load_hours': round(float(g['gas turbine'].sum()) / c['gt_mw'], 0) if c['gt_mw'] > 0 else 0.0,
        'grid_energy_cost_usd': round(float((g['utility'] * price).sum()), 0),
        'gt_cost_usd': round(float(g['gas turbine'].sum()) * c['gt_cost'], 0),
        'total_cost_usd': round(float(n.objective), 0),
    }
    if c['battery']:
        p = float(n.links.p_nom_opt['battery discharger'])
        e = float(n.stores.e_nom_opt['battery energy'])
        out.update(battery_mw=round(p, 2), battery_mwh=round(e, 2), battery_hours=round(e / p, 2) if p > 1e-6 else None,
                   battery_capital_usd=round(p * c['bat_mw_cost'] + e * c['bat_mwh_cost'], 0),
                   battery_cycles=round(float(n.links_t.p0['battery discharger'].sum()) / e, 1) if e > 1e-6 else 0.0)
    return out


CASES = [
    ('No battery', dict(battery=False)),
    ('Battery sized freely', {}),
    ('Back-up required (10 min of the site)', dict(backup_min=10.0)),
    ('No battery, demand charge 15 $/kW-month', dict(battery=False, demand_usd_kw_month=15.0)),
    ('Battery sized freely, demand charge 15 $/kW-month', dict(demand_usd_kw_month=15.0)),
    ('Back-up required, demand charge 15 $/kW-month', dict(backup_min=10.0, demand_usd_kw_month=15.0)),
    ('Battery sized freely, on-peak 300 $/MWh', dict(on=300.0)),
    ('Battery sized freely, gas at 90 $/MWh', dict(gt_cost=90.0)),
    # The turbine on standby only (not dispatched for energy): the utility carries the site.
    ('Turbine standby: no battery', dict(gt_mw=0.0, battery=False)),
    ('Turbine standby: battery sized freely', dict(gt_mw=0.0)),
    ('Turbine standby: back-up required', dict(gt_mw=0.0, backup_min=10.0)),
    ('Turbine standby: no battery, demand charge 15 $/kW-month', dict(gt_mw=0.0, battery=False, demand_usd_kw_month=15.0)),
    ('Turbine standby: battery sized freely, demand charge 15 $/kW-month', dict(gt_mw=0.0, demand_usd_kw_month=15.0)),
    ('Turbine standby: back-up required, demand charge 15 $/kW-month', dict(gt_mw=0.0, backup_min=10.0, demand_usd_kw_month=15.0)),
    ('Turbine standby: battery sized freely, on-peak 300 $/MWh, demand charge 15', dict(gt_mw=0.0, on=300.0, demand_usd_kw_month=15.0)),
]

if __name__ == '__main__':
    import logging
    import warnings
    logging.disable(logging.WARNING)
    warnings.filterwarnings('ignore')
    results = []
    for label, over in CASES:
        r = run(label, **over)
        results.append(r)
        print(f"{label:72s} {r['status']:4s} total {r.get('total_cost_usd', 0) / 1e6:6.3f} M$  "
              f"grid {r.get('grid_mwh', 0):7.0f} MWh (peak {r.get('grid_peak_mw', 0):5.2f})  "
              f"GT {r.get('gt_mwh', 0):7.0f} MWh  battery {r.get('battery_mw', 0) or 0:5.2f} MW / "
              f"{r.get('battery_mwh', 0) or 0:6.2f} MWh  {r.get('battery_cycles', 0) or 0:5.1f} cycles")
    with open(os.path.join(HERE, 'results.json'), 'w', encoding='utf-8') as fh:
        json.dump(results, fh, indent=1)
