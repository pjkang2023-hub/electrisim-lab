"""
Optimise over the surrogate, check the answer in EMT, learn from it, repeat.

    ..\\.venv\\Scripts\\python.exe adaptive.py [v_limit_pu] [max_rounds] [ensemble]

Each round: fit an ensemble of ReLU networks (different seeds) to every EMT run so far; with OMLT,
find the least converter rating (3 lineup + 2 Hall B stores) that EVERY network says holds the 800 V
at v_limit_pu or above - conservative where they disagree; run EMT there (emt_sample.py, which
appends the run to samples.jsonl). Stop when EMT confirms it (800 V at the limit or above, no rack
lost); otherwise the failed run joins the data and the next round refits. Writes adaptive.json.
"""
import json
import os
import subprocess
import sys

import numpy as np
import pyomo.environ as pyo
from omlt import OmltBlock
from omlt.neuralnet import ReluBigMFormulation

import surrogate as S

V_LIMIT = float(sys.argv[1]) if len(sys.argv) > 1 else 0.92
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 8
ENSEMBLE = int(sys.argv[3]) if len(sys.argv) > 3 else 3


def optimise_ensemble(nets, v_limit):
    m = pyo.ConcreteModel()
    m.nn = pyo.Block(range(len(nets)))
    for k, mlp in enumerate(nets):
        m.nn[k].net = OmltBlock()
        m.nn[k].net.build_formulation(ReluBigMFormulation(S.omlt_network(mlp)))
    first = m.nn[0].net
    m.same = pyo.ConstraintList()          # one design: every network sees the same inputs
    for k in range(1, len(nets)):
        for i in range(3):
            m.same.add(m.nn[k].net.inputs[i] == first.inputs[i])
    m.hold = pyo.ConstraintList()
    for k in range(len(nets)):
        m.hold.add(m.nn[k].net.outputs[0] >= v_limit)
    m.obj = pyo.Objective(expr=3 * first.inputs[0] + 2 * first.inputs[1])
    res = pyo.SolverFactory('appsi_highs').solve(m)
    if not pyo.check_optimal_termination(res):
        return None
    x = [round(pyo.value(first.inputs[i]), 3) for i in range(3)]
    return {'lineup_store_mw': x[0], 'hallb_store_mw': x[1], 'floor_pu': x[2],
            'surrogate_v800_pu': [round(pyo.value(m.nn[k].net.outputs[0]), 4) for k in range(len(nets))],
            'total_store_mw': round(3 * x[0] + 2 * x[1], 3)}


def main():
    history = []
    for rnd in range(1, ROUNDS + 1):
        if not round_once(rnd, history):
            break
    with open(os.path.join(S.HERE, f'adaptive_{V_LIMIT:.2f}.json'), 'w', encoding='utf-8') as fh:
        json.dump(history, fh, indent=1)


def round_once(rnd, history):
    """One round; False when it should stop (confirmed, or no design)."""
    _, x, y = S.load()
    nets = [S.fit(x, y, seed=s) for s in range(ENSEMBLE)]
    best = optimise_ensemble(nets, V_LIMIT)
    if best is None:
        print(f'round {rnd}: no design within the bounds that every network says holds', flush=True)
        history.append({'round': rnd, 'samples': len(y), 'optimum': None})
        return False
    res = subprocess.run([S.PY, os.path.join(S.HERE, 'emt_sample.py'), str(best['lineup_store_mw']),
                          str(best['hallb_store_mw']), str(best['floor_pu'])], capture_output=True, text=True)
    emt = json.loads([l for l in res.stdout.splitlines() if l.startswith('{')][-1])
    good = emt['v800_min_pu'] >= V_LIMIT and emt['racks_lost'] == 0
    history.append({'round': rnd, 'samples': len(y), 'optimum': best, 'emt': emt, 'confirmed': good})
    print(f"round {rnd} ({len(y)} samples): lineup {best['lineup_store_mw']} MW, Hall B {best['hallb_store_mw']} MW, "
          f"floor {best['floor_pu']}, total {best['total_store_mw']} MW; surrogates {best['surrogate_v800_pu']} -> "
          f"EMT {emt['v800_min_pu']} pu, {emt['racks_lost']} racks lost: {'CONFIRMED' if good else 'failed, learning'}",
          flush=True)
    return not good


if __name__ == '__main__':
    main()
