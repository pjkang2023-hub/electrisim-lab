"""
Captures the network Electrisim's load flow solves for a reference drawing, read-only.

Run with Electrisim's own Python (it imports Electrisim's backend; nothing is installed or edited):
    ..\\..\\electrisim\\.venv\\Scripts\\python.exe capture_net.py reference_pcs3750_mv
Writes <name>.lf_net.pkl (the pandapower net after its last load flow, with Electrisim's records)
beside this script.
"""
import contextlib
import copy
import io
import json
import os
import pickle
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)
BACKEND = os.path.join(os.path.dirname(LAB), 'electrisim', 'backend')
NAME = sys.argv[1] if len(sys.argv) > 1 else 'reference_pcs3750_mv'

sys.path.insert(0, BACKEND)
os.chdir(BACKEND)
import pandapower as pp                      # noqa: E402
import app as flask_app                      # noqa: E402
import pandapower_electrisim as pe           # noqa: E402

captured = {}
_runpp = pp.runpp


def grab(net, *a, **k):
    out = _runpp(net, *a, **k)
    captured['net'] = net                     # the last load flow's net, results included
    return out


pp.runpp = grab
pe.pp.runpp = grab

with open(os.path.join(LAB, 'refs', f'{NAME}.diagram_payload.json'), encoding='utf-8') as fh:
    payload = json.load(fh)
buf = io.StringIO()
with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
    out = json.loads(flask_app.app.test_client().post('/', json=payload).get_data(as_text=True))
print('load flow error:', out.get('error'), '| study:', payload['0'].get('typ'))
net = copy.deepcopy(captured['net'])
with open(os.path.join(HERE, f'{NAME}.lf_net.pkl'), 'wb') as fh:
    pickle.dump(net, fh)
for t in ('bus', 'line', 'trafo', 'load', 'gen', 'sgen', 'ext_grid', 'storage', 'shunt', 'impedance', 'switch',
          'bus_dc', 'line_dc', 'load_dc', 'source_dc', 'vsc'):
    if t in net and len(net[t]):
        print(f'{t:10s} {len(net[t]):4d}', list(net[t].columns)[:14])
print('electrisim records:', [k for k in vars(net) if k.startswith('electrisim')][:30] if hasattr(net, '__dict__') else '')
print('res_ext_grid', net.res_ext_grid[['p_mw', 'q_mvar']].round(4).to_dict('records'))
