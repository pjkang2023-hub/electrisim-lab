"""
One EMT run of the 800 VDC factory islanded at full load (the grid lost at 20 ms, the turbine off),
for a sample of three design inputs; appends its outcome to samples.jsonl.

Run with Electrisim's own Python (it calls Electrisim's backend read-only, as the reference tests do):
    ..\\..\\electrisim\\.venv\\Scripts\\python.exe emt_sample.py <lineup_store_mw> <hallb_store_mw> <floor_pu>

Inputs:  lineup_store_mw - each lineup's (A, B, catcher) bus-store converter rating;
         hallb_store_mw  - each of Hall B's two bus-store converter ratings;
         floor_pu        - the easing floor of every lineup rectifier and Hall B SST
                           (each easing below 0.85 pu, back over 5 s).
Outputs: the lowest 800 V bus voltage over the run (pu), racks lost, converters blocked.
"""
import contextlib
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)
BACKEND = os.path.join(os.path.dirname(LAB), 'electrisim', 'backend')
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)
import app as flask_app        # noqa: E402

RECTIFIERS = [f'{g} rectifier {k}' for g in ('Lineup A', 'Lineup B', 'Catcher B') for k in (1, 2, 3, 4)]
SSTS = [f'Hall B SST {k}' for k in (1, 2, 3)]
LINEUP_STORES = ('Lineup A DC Store', 'Lineup B DC Store', 'Catcher B DC Store')
HALLB_STORES = ('Hall B DC Store 1', 'Hall B DC Store 2')


def variant(payload, changes):
    p = json.loads(json.dumps(payload))
    by_label = {v.get('userFriendlyName'): k for k, v in p.items() if isinstance(v, dict)}
    for label, fields in changes.items():
        p[by_label[label]].update(fields)
    return p


def run(lineup_mw, hallb_mw, floor):
    with open(os.path.join(LAB, 'refs', 'reference_ai_factory_800vdc.diagram_payload.json'), encoding='utf-8') as fh:
        base = json.load(fh)
    ease = {'uv_ease_pu': '0.85', 'uv_floor_pu': f'{floor:.4f}', 'uv_restore_s': '5'}
    changes = {'Gas turbine': {'in_service': 'false'}}
    changes.update({f'{s} converter': {'rated_mw': f'{lineup_mw:.4f}'} for s in LINEUP_STORES})
    changes.update({f'{s} converter': {'rated_mw': f'{hallb_mw:.4f}'} for s in HALLB_STORES})
    changes.update({r: ease for r in RECTIFIERS + SSTS})
    p = variant(base, changes)
    p['0'] = {'typ': 'EmtStudy Parameters', 'user_email': 't@t', 'duration_ms': '300', 'frequency': '60',
              'time_step_us': '10', 'island_time_ms': '20', 'profile_start_s': '0.15'}
    t0 = time.time()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        out = json.loads(flask_app.app.test_client().post('/', json=p).get_data(as_text=True))
    if out.get('error'):
        return {'lineup_store_mw': lineup_mw, 'hallb_store_mw': hallb_mw, 'floor_pu': floor, 'error': True,
                'seconds': round(time.time() - t0, 1)}
    emt = out['emt']
    lows = {b['label']: b['v_min_pu'] for b in emt['buses'] if b['label'].endswith('800 V')}
    return {
        'lineup_store_mw': lineup_mw, 'hallb_store_mw': hallb_mw, 'floor_pu': floor, 'error': False,
        'v800_min_pu': round(min(lows.values()), 4), 'v800_min_bus': min(lows, key=lows.get),
        'racks_lost': sum(1 for l in emt['loads'] if l.get('t_lost_ms')),
        'blocked': sorted(b['label'] for b in emt['converters_blocked']),
        'seconds': round(time.time() - t0, 1),
    }


if __name__ == '__main__':
    r = run(float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]))
    with open(os.path.join(HERE, 'samples.jsonl'), 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(r) + '\n')
    print(json.dumps(r))
