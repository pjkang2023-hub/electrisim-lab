"""
A neural-network surrogate of the factory island's lowest 800 V (from the EMT sweep), embedded in a
Pyomo model with OMLT, and the least store-converter MW that keeps the 800 V above a limit.

    ..\\.venv\\Scripts\\python.exe surrogate.py [v_limit_pu] [--check]

  - fits a ReLU MLP (scikit-learn) to samples.jsonl: inputs the lineup and Hall B store-converter
    ratings and the easing floor, output the lowest 800 V bus voltage (pu); 5-fold cross-validation;
  - writes the network into OMLT (ReluBigMFormulation: an exact MILP of the ReLU network) and
    minimises the converters' total rating (3 lineup stores + 2 Hall B stores) subject to the
    surrogate's 800 V at or above v_limit_pu, solved with HiGHS;
  - --check runs EMT at the optimum (emt_sample.py, Electrisim's Python) and compares.
"""
import json
import os
import subprocess
import sys

import numpy as np
import pyomo.environ as pyo
from omlt import OffsetScaling, OmltBlock
from omlt.neuralnet import NetworkDefinition, ReluBigMFormulation
from omlt.neuralnet.layer import DenseLayer, InputLayer
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.neural_network import MLPRegressor

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'electrisim', '.venv', 'Scripts', 'python.exe')
NAMES = ['lineup_store_mw', 'hallb_store_mw', 'floor_pu']
LO = np.array([2.5, 2.5, 0.1])
HI = np.array([8.0, 7.0, 1.0])
V_LIMIT = float(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else 0.92


def load():
    rows = [json.loads(l) for l in open(os.path.join(HERE, 'samples.jsonl'), encoding='utf-8')]
    rows = [r for r in rows if not r['error']]
    x = np.array([[r[n] for n in NAMES] for r in rows])
    y = np.clip(np.array([r['v800_min_pu'] for r in rows]), 0.0, 1.05)
    return rows, x, y


def fit(x, y, seed=0):
    return MLPRegressor(hidden_layer_sizes=(16, 16), activation='relu', solver='lbfgs', alpha=1e-3,
                        max_iter=5000, random_state=seed).fit((x - LO) / (HI - LO), y)


def omlt_network(mlp):
    scaling = OffsetScaling(offset_inputs=list(LO), factor_inputs=list(HI - LO), offset_outputs=[0.0], factor_outputs=[1.0])
    net = NetworkDefinition(scaling_object=scaling, scaled_input_bounds={i: (0.0, 1.0) for i in range(3)})
    prev = InputLayer([3])
    net.add_layer(prev)
    n_layers = len(mlp.coefs_)
    for k, (w, b) in enumerate(zip(mlp.coefs_, mlp.intercepts_)):
        layer = DenseLayer(prev.output_size, [w.shape[1]], weights=w, biases=b,
                           activation='relu' if k < n_layers - 1 else 'linear')
        net.add_layer(layer)
        net.add_edge(prev, layer)
        prev = layer
    return net


def optimise(mlp, v_limit):
    m = pyo.ConcreteModel()
    m.nn = OmltBlock()
    m.nn.build_formulation(ReluBigMFormulation(omlt_network(mlp)))
    lineup, hallb, floor = m.nn.inputs[0], m.nn.inputs[1], m.nn.inputs[2]
    m.v = pyo.Constraint(expr=m.nn.outputs[0] >= v_limit)
    m.obj = pyo.Objective(expr=3 * lineup + 2 * hallb)
    res = pyo.SolverFactory('appsi_highs').solve(m)
    if pyo.check_optimal_termination(res) is False:
        return None
    return {'lineup_store_mw': round(pyo.value(lineup), 3), 'hallb_store_mw': round(pyo.value(hallb), 3),
            'floor_pu': round(pyo.value(floor), 3), 'surrogate_v800_pu': round(pyo.value(m.nn.outputs[0]), 4),
            'total_store_mw': round(pyo.value(m.obj), 3)}


if __name__ == '__main__':
    rows, x, y = load()
    xs = (x - LO) / (HI - LO)
    cv = cross_val_predict(MLPRegressor(hidden_layer_sizes=(16, 16), activation='relu', solver='lbfgs', alpha=1e-3,
                                        max_iter=5000, random_state=0), xs, y, cv=KFold(5, shuffle=True, random_state=0))
    err = np.abs(cv - y)
    ok = y >= V_LIMIT
    agree = np.mean((cv >= V_LIMIT) == ok)
    print(f'{len(y)} samples; {int(ok.sum())} hold the 800 V at {V_LIMIT} pu or above; '
          f'cross-validated error: mean {err.mean():.4f} pu, 90th percentile {np.percentile(err, 90):.4f} pu, '
          f'worst {err.max():.4f} pu; pass/fail agreement {100 * agree:.1f} %')
    mlp = fit(x, y)
    best = optimise(mlp, V_LIMIT)
    print('optimum:', json.dumps(best))
    out = {'samples': len(y), 'holding': int(ok.sum()), 'v_limit_pu': V_LIMIT,
           'cv_mae_pu': round(float(err.mean()), 4), 'cv_p90_pu': round(float(np.percentile(err, 90)), 4),
           'cv_max_pu': round(float(err.max()), 4), 'cv_pass_fail_agreement': round(float(agree), 3), 'optimum': best}
    if best and '--check' in sys.argv:
        res = subprocess.run([PY, os.path.join(HERE, 'emt_sample.py'), str(best['lineup_store_mw']),
                              str(best['hallb_store_mw']), str(best['floor_pu'])], capture_output=True, text=True)
        check = json.loads([l for l in res.stdout.splitlines() if l.startswith('{')][-1])
        out['emt_check'] = check
        print('EMT at the optimum:', json.dumps(check))
    with open(os.path.join(HERE, f'result_{V_LIMIT:.2f}.json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=1)
