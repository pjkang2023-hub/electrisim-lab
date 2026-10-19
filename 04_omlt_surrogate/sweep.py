"""
The EMT sweep behind the surrogate: a Latin-hypercube sample of the three inputs, each point one
emt_sample.py run in Electrisim's own Python, WORKERS at a time. Points already in samples.jsonl
are skipped, so a stopped sweep resumes.
    ..\\.venv\\Scripts\\python.exe sweep.py [n_points] [workers]
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from scipy.stats import qmc

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'electrisim', '.venv', 'Scripts', 'python.exe')
BOUNDS = {'lineup_store_mw': (2.5, 8.0), 'hallb_store_mw': (2.5, 7.0), 'floor_pu': (0.1, 1.0)}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 96
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 5

lo = [b[0] for b in BOUNDS.values()]
hi = [b[1] for b in BOUNDS.values()]
points = qmc.scale(qmc.LatinHypercube(d=3, seed=18).random(N), lo, hi).round(3).tolist()
# The corners too: the surrogate should not extrapolate there.
points += [[a, b, c] for a in (2.5, 8.0) for b in (2.5, 7.0) for c in (0.1, 1.0)]

done = set()
path = os.path.join(HERE, 'samples.jsonl')
if os.path.exists(path):
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            r = json.loads(line)
            done.add((round(r['lineup_store_mw'], 3), round(r['hallb_store_mw'], 3), round(r['floor_pu'], 3)))
todo = [p for p in points if tuple(round(x, 3) for x in p) not in done]
print(f'{len(points)} points, {len(todo)} to run, {WORKERS} at a time', flush=True)


def one(p):
    res = subprocess.run([PY, os.path.join(HERE, 'emt_sample.py'), *map(str, p)], capture_output=True, text=True)
    line = [l for l in res.stdout.splitlines() if l.startswith('{')]
    return line[-1] if line else f'FAILED {p}: {res.stderr[-300:]}'


with ThreadPoolExecutor(WORKERS) as pool:
    for k, out in enumerate(pool.map(one, todo), 1):
        print(f'[{k}/{len(todo)}] {out}', flush=True)
