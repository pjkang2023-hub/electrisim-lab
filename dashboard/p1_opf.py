import json
import os

import pandas as pd
import plotly.express as px
import streamlit as st

from common import EXP, LAB

import acdc_opf as A   # 01_pyomo_acdc_opf

st.title('1 · AC/DC optimal power flow')
st.write('The PCS3750C-MV reference built from its spec in Pyomo and solved with Ipopt: the AC networks, '
         'each DC quadrant\'s AFE, batteries and grid-forming inverter, every converter within its rating '
         'circle, the inverters\' 0.6 S reactive cap.')

refs = {'3 blocks (10.8 MW)': 'reference_pcs3750_mv', '9 blocks (30 MW)': 'reference_pcs3750_mv_9blocks'}
c1, c2, c3 = st.columns(3)
ref = refs[c1.selectbox('Reference', list(refs))]
with open(os.path.join(LAB, 'refs', f'{ref}.spec.json'), encoding='utf-8') as fh:
    spec = json.load(fh)
blocks = sorted({p['id'][:2] for p in spec['pcs']})
mode = c2.selectbox('Mode', ['opf', 'shed', 'lf'], format_func={
    'opf': 'OPF: least losses', 'shed': 'Least shed, then least losses', 'lf': 'Load-flow check (Electrisim\'s controls)'}.get)
out = c3.multiselect('Blocks out of service (their inverters)', blocks)
c4, c5, c6 = st.columns(3)
batteries = c4.checkbox('Batteries may discharge', value=False,
                        help='Stored energy is priced at twice the grid\'s, so they discharge only where needed.')
limits = c5.checkbox('Enforce line and transformer ratings', value=mode != 'lf', disabled=mode == 'lf')
factor = c6.slider('Transformer rating factor', 0.8, 1.5, 1.0, 0.01, disabled=not limits,
                   help='The transformers\' nameplate times this - for example 1.1 for a 10 % overload.')
v_load = None
if mode == 'lf':
    v_load = st.number_input('Load-side bus voltage (pu), as Electrisim\'s load flow settles', value=0.99771, format='%.5f')

if st.button('Solve', type='primary'):
    with st.spinner('Solving with Ipopt…'):
        m = A.build(spec, mode, tuple(out), batteries, branch_limits=limits and mode != 'lf', trafo_factor=factor)
        if v_load:
            for g in m.G:
                m.V[m.meta['G'][g]['bus']].fix(v_load)
        status = A.solve(m)
        st.session_state['opf'] = (status, A.report(m, ref))

if 'opf' in st.session_state:
    status, r = st.session_state['opf']
    if status != 'optimal':
        st.error(f'Ipopt: {status}. No dispatch meets every constraint - the figures below are the point it '
                 'stopped at, not a solution. Try "Least shed", batteries, or a higher transformer rating factor.')
    else:
        st.success('Ipopt: optimal')
    k = st.columns(5)
    k[0].metric('Grid import', f"{r['grid_p_mw']:.3f} MW", f"{r['grid_q_mvar']:.3f} Mvar", delta_color='off')
    k[1].metric('Racks served', f"{r['racks_served_mw']:.3f} MW")
    k[2].metric('Racks shed', f"{sum(r['racks_shed_mw'].values()):.3f} MW")
    k[3].metric('Batteries', f"{r['battery_mw']:.3f} MW")
    k[4].metric('Inverters, most loaded', f"{r['gfm_loading_pct']:.1f} %")
    a, b = st.columns(2)
    v = pd.DataFrame({'bus': list(r['v_pu']), 'vm_pu': list(r['v_pu'].values())})
    fig = px.bar(v, x='bus', y='vm_pu', title='Bus voltages (pu)', range_y=[0.85, 1.12])
    fig.add_hline(y=1.1, line_dash='dot')
    fig.add_hline(y=0.9, line_dash='dot')
    a.plotly_chart(fig, width='stretch')
    t = pd.DataFrame({'transformer': list(r['trafo_loading_pct']), 'loading_pct': list(r['trafo_loading_pct'].values())})
    fig = px.bar(t, x='transformer', y='loading_pct', title='Transformer loading (% of nameplate)')
    fig.add_hline(y=100, line_dash='dot')
    b.plotly_chart(fig, width='stretch')
    st.dataframe(pd.DataFrame({'Hall': list(r['racks_shed_mw']), 'Shed (MW)': list(r['racks_shed_mw'].values())}),
                 hide_index=True)
    with st.expander('Every figure'):
        st.json(r)
st.caption(f"Model: {os.path.join(EXP['opf'], 'acdc_opf.py')} · its README states the method and limits.")
