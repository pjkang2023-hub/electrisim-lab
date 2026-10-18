"""
What limits each screened site: its load set 5 % past its headroom, the violations Electrisim's
screening counts. Run with Electrisim's Python after screen_sites.py:
    ..\\..\\electrisim\\.venv\\Scripts\\python.exe binding_limits.py p1rhs0_1247
"""
import contextlib
import io
import json
import os
import sys
from copy import deepcopy

import pandapower as pp

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'electrisim', 'backend'))
import data_center_site_screening_electrisim as ss   # noqa: E402

NAME = sys.argv[1] if len(sys.argv) > 1 else 'p1rhs0_1247'
net = pp.from_json(os.path.join(HERE, f'{NAME}.pp.json'))
with open(os.path.join(HERE, f'{NAME}.screening.json'), encoding='utf-8') as fh:
    out = json.load(fh)
limits = {'voltage_limits': True, 'thermal_limits': True, 'min_vm_pu': 0.95, 'max_vm_pu': 1.05, 'max_loading_percent': 100.0}
heads = {}
for r in out['screening_results']:
    heads.setdefault(r['site_name'], r['headroom_mw'])

summary = {}
for site, headroom in heads.items():
    n = deepcopy(net)
    bus_name = out['sites'][site]['bus']
    b = int(n.bus.index[n.bus.name == bus_name][0])
    li = pp.create_load(n, b, p_mw=0.0, q_mvar=0.0, name=site)
    ss._set_load_mw(n, li, headroom * 1.05 + 0.01, 0.95)
    with contextlib.redirect_stdout(io.StringIO()):
        ok = ss._run_pf(n)
    count, details = ss._count_violations(n, **limits) if ok else (-1, [])
    kinds = {}
    for d in details:
        kinds.setdefault(d.get('kind'), []).append(d)
    first = {k: (v[0].get('text'), v[0].get('id')) for k, v in kinds.items()}
    summary[site] = {'headroom_mw': headroom, 'bus': bus_name, 'violations_just_past': count, 'first_of_each_kind': first,
                     'substation_transformer_pct': round(float(n.res_trafo.loading_percent.iloc[0]), 1) if ok else None,
                     'v_min_pu': round(float(n.res_bus.vm_pu.min()), 4) if ok else None}
    print(f"{site:26s} {headroom:6g} MW  past it: {count:4d} violations  trafo {summary[site]['substation_transformer_pct']} %  "
          f"Vmin {summary[site]['v_min_pu']}  {first}")
with open(os.path.join(HERE, f'{NAME}.binding.json'), 'w', encoding='utf-8') as fh:
    json.dump(summary, fh, indent=1)
