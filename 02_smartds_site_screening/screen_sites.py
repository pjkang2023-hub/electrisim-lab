"""
Electrisim's Data Center Site Screening on the converted SMART-DS feeder, read-only: the same
site_screening_analysis() the app runs, called on the pandapower net from convert_feeder.py.

Run with Electrisim's own Python:
    ..\\..\\electrisim\\.venv\\Scripts\\python.exe screen_sites.py p1rhs0_1247 [sizes MW, e.g. 1,2,5]

Candidate sites: the substation's MV bus, each feeder's head, and each feeder's electrical middle
and far end (by impedance from the substation). Writes <substation>.screening.json.
"""
import contextlib
import io
import json
import os
import sys

import networkx as nx
import pandapower as pp
import pandapower.topology as top

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'electrisim', 'backend')
sys.path.insert(0, BACKEND)
import data_center_site_screening_electrisim as ss   # noqa: E402

NAME = sys.argv[1] if len(sys.argv) > 1 else 'p1rhs0_1247'
SIZES = sys.argv[2] if len(sys.argv) > 2 else '1,2,5'
net = pp.from_json(os.path.join(HERE, f'{NAME}.pp.json'))

# The substation's MV bus: the transformer's LV side. Feeders: the branches leaving it.
sub_mv = int(net.trafo.lv_bus.iloc[0])
g = top.create_nxgraph(net, respect_switches=True, calc_branch_impedances=True, branch_impedance_unit='ohm')
dist = nx.single_source_dijkstra_path_length(g, sub_mv, weight='z_ohm')
# Each feeder's head: SMART-DS names it <feeder>-<substation>x; else the substation bus's neighbours.
heads = (sorted(int(b) for b in net.bus.index if str(net.bus.at[b, 'name']).endswith(f'-{NAME}x'))
         or sorted(set(nx.neighbors(g, sub_mv))))
up = nx.shortest_path(g, sub_mv)
sites = {'Substation 12.47 kV bus': sub_mv}
for k, head in enumerate(heads, 1):
    h = g.copy()
    h.remove_nodes_from(up[head][:-1])          # the path above the head: what is left below it is its feeder
    feeder = nx.node_connected_component(h, head)
    if len(feeder) < 10:
        continue                                  # a stub, not a feeder
    far = max(feeder, key=lambda b: dist.get(b, 0))
    mid = min(feeder, key=lambda b: abs(dist.get(b, 0) - dist[far] / 2))
    sites[f'Feeder {k} head'] = head
    sites[f'Feeder {k} middle'] = mid
    sites[f'Feeder {k} far end'] = far

ids = []
for label, bus in sites.items():
    i = pp.create_load(net, bus, p_mw=0.0, q_mvar=0.0, name=label)
    ids.append(label)
print('sites:', {k: (str(net.bus.at[b, 'name']), round(dist.get(b, 0), 3)) for k, b in sites.items()})

params = {'site_load_ids': ','.join(ids), 'mw_sizes': SIZES, 'power_factor': '0.95', 'include_n11': 'false',
          'element_type': 'transformer', 'voltage_limits': 'true', 'thermal_limits': 'true',
          'min_vm_pu': '0.95', 'max_vm_pu': '1.05', 'max_loading_percent': '100'}
with contextlib.redirect_stdout(io.StringIO()):
    out = json.loads(ss.site_screening_analysis(net, params))
out['sites'] = {k: {'bus': str(net.bus.at[b, 'name']), 'z_from_substation_ohm': round(float(dist.get(b, 0)), 3)}
                for k, b in sites.items()}
with open(os.path.join(HERE, f'{NAME}.screening.json'), 'w', encoding='utf-8') as fh:
    json.dump(out, fh, indent=1)

rows = out.get('screening_results') or []
print('result keys:', list(out)[:12])
for r in rows:
    worst = (r.get('case_violation_details') or [])[:2]
    print(f"{r['site_name']:26s} {r['requested_mw']:5g} MW  headroom {r['headroom_mw']:6g} MW  "
          f"violations {r.get('case_violations')}  N-1 {r.get('worst_n1_violations')}  "
          f"{'; '.join(v.get('text', '') + ' ' + str(v.get('id', '')) for v in worst)[:150]}")
