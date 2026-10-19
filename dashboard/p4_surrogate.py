import json
import os
import re
import subprocess
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import ELECTRISIM_PY, EXP, LAB_PY, read_jsonl, run_script

import surrogate as S   # 04_omlt_surrogate

FOLDER = EXP['surrogate']
SAMPLES = os.path.join(FOLDER, 'samples.jsonl')
LOG = os.path.join(FOLDER, 'sweep.log')

st.title('4 · Surrogate design')
st.write('The 800 VDC factory islanded at full load (grid lost at 20 ms, turbine off), in EMT, over three design '
         'inputs: the lineup and Hall B bus-store converter ratings and the easing floor of the lineup rectifiers '
         'and Hall B SSTs. A ReLU network fitted to the runs goes into a Pyomo model through OMLT, which finds '
         'the least converter rating that holds the 800 V.')

# --- The sweep ---------------------------------------------------------------------------------
rows = [r for r in read_jsonl(SAMPLES) if not r.get('error')]


def sweep_state():
    """(running, done, total) from the sweep's log: its last '[k/N]' line, and whether it changed lately."""
    if not os.path.exists(LOG):
        return False, 0, 0
    text = open(LOG, encoding='utf-8').read()
    marks = re.findall(r'^\[(\d+)/(\d+)\]', text, flags=re.M)
    done, total = (int(marks[-1][0]), int(marks[-1][1])) if marks else (0, 0)
    head = re.search(r'(\d+) to run', text)
    total = total or (int(head.group(1)) if head else 0)
    fresh = time.time() - os.path.getmtime(LOG) < 15 * 60      # a run takes minutes; quiet longer means stopped
    return fresh and (total == 0 or done < total), done, total


running, done_now, total_now = sweep_state()
st.subheader('EMT sweep')
a, b, c = st.columns(3)
a.metric('Runs done', len(rows))
b.metric('Sweep', f'running, {done_now} of {total_now}' if running else 'idle')
n_pts = c.number_input('Latin-hypercube points', 20, 400, 96, help='Plus the 8 corners. Runs already done are skipped.')
if st.button('Start or resume the sweep', disabled=running,
             help='Five EMT runs at a time, about 80 s each alone; it keeps running if you leave this page.'):
    with open(LOG, 'w', encoding='utf-8') as log:
        subprocess.Popen([LAB_PY, 'sweep.py', str(n_pts), '5'], cwd=FOLDER, stdout=log, stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    st.rerun()
if os.path.exists(LOG):
    with st.expander('Sweep log (last lines)'):
        st.code(''.join(open(LOG, encoding='utf-8').readlines()[-8:]))

if len(rows) < 12:
    st.info('At least a dozen runs are needed to fit the surrogate.')
    st.stop()

# --- The surrogate -----------------------------------------------------------------------------
st.subheader('Surrogate')
_, x, y = S.load()
mlp = S.fit(x, y)
floor = st.slider('Easing floor shown', 0.1, 1.0, 0.1, 0.05)
g1, g2 = np.meshgrid(np.linspace(S.LO[0], S.HI[0], 60), np.linspace(S.LO[1], S.HI[1], 60))
grid = np.c_[g1.ravel(), g2.ravel(), np.full(g1.size, floor)]
pred = mlp.predict((grid - S.LO) / (S.HI - S.LO)).reshape(g1.shape)
fig = go.Figure(go.Contour(x=g1[0], y=g2[:, 0], z=pred, colorscale='RdYlGn', zmin=0.0, zmax=1.0,
                           colorbar=dict(title='lowest 800 V (pu)'), contours=dict(showlabels=True)))
near = np.abs(x[:, 2] - floor) <= 0.1
fig.add_trace(go.Scatter(x=x[near, 0], y=x[near, 1], mode='markers', marker=dict(color=y[near], colorscale='RdYlGn',
                                                                                 cmin=0, cmax=1, line=dict(width=1, color='black')),
                         text=[f'{v:.3f} pu' for v in y[near]], name='EMT runs, floor within 0.1'))
fig.update_layout(height=520, xaxis_title='lineup store converters (MW each)', yaxis_title='Hall B store converters (MW each)')
st.plotly_chart(fig, width='stretch')

# --- The optimum -------------------------------------------------------------------------------
st.subheader('Least converter rating')
v_limit = st.slider('The 800 V must stay at or above (pu)', 0.80, 0.98, 0.92, 0.01)
if st.button('Optimise (OMLT, HiGHS)', type='primary'):
    with st.spinner('Solving the network as a MILP…'):
        st.session_state['opt'] = S.optimise(mlp, v_limit)
        st.session_state.pop('check', None)
best = st.session_state.get('opt')
if best is None and 'opt' in st.session_state:
    st.error('No design within the bounds keeps the 800 V there, by the surrogate.')
elif best:
    k = st.columns(4)
    k[0].metric('Lineup stores', f"{best['lineup_store_mw']:.2f} MW each")
    k[1].metric('Hall B stores', f"{best['hallb_store_mw']:.2f} MW each")
    k[2].metric('Easing floor', f"{best['floor_pu']:.2f}")
    k[3].metric('Total (3 + 2 converters)', f"{best['total_store_mw']:.2f} MW", f"surrogate {best['surrogate_v800_pu']:.3f} pu",
                delta_color='off')
    if st.button('Check it with a real EMT run (about 80 s)'):
        with st.spinner('Running EMT…'):
            ok, out, err = run_script(ELECTRISIM_PY, 'emt_sample.py',
                                      [best['lineup_store_mw'], best['hallb_store_mw'], best['floor_pu']], FOLDER)
        st.session_state['check'] = out.strip().splitlines()[-1] if ok else err[-800:]
    if 'check' in st.session_state:

        try:
            chk = json.loads(st.session_state['check'])
            good = chk['v800_min_pu'] >= v_limit and chk['racks_lost'] == 0
            (st.success if good else st.warning)(
                f"EMT: lowest 800 V {chk['v800_min_pu']:.4f} pu at {chk['v800_min_bus']}; racks lost {chk['racks_lost']}; "
                f"blocked: {', '.join(chk['blocked']) or 'none'}")
        except Exception:
            st.error(st.session_state['check'])
