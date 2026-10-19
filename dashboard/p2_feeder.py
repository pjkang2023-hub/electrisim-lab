import os
import re
import urllib.request

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import ELECTRISIM_PY, EXP, LAB, LAB_PY, read_json, run_script

import fetch_smartds   # 02_smartds_site_screening

FOLDER = EXP['feeder']
DATA = os.path.join(LAB, 'data', 'smartds')
BUCKET = 'https://oedi-data-lake.s3.amazonaws.com'

st.title('2 · Feeder site screening')
st.write('A SMART-DS substation (NREL, CC BY 4.0) solved in OpenDSS, reduced to its medium-voltage network, '
         'and screened with Electrisim\'s own Data Center Site Screening: how much each candidate site can take, '
         'and what limits it.')


@st.cache_data(ttl=3600)
def folders(prefix):
    xml = urllib.request.urlopen(f'{BUCKET}/?list-type=2&prefix={prefix}&delimiter=/', timeout=60).read().decode()
    return [p[len(prefix):].rstrip('/') for p in re.findall(r'<Prefix>([^<]+)</Prefix>', xml) if p != prefix]


@st.cache_data(ttl=3600)
def listing(prefix):
    return fetch_smartds.keys(prefix)


c1, c2, c3 = st.columns(3)
dataset = c1.selectbox('Dataset (2018)', ['AUS', 'GSO', 'SFO'])
regions = [r for r in folders(f'SMART-DS/v1.0/2018/{dataset}/') if r != 'full_dataset_analysis']
region = c2.selectbox('Region', regions, index=regions.index('P1R') if 'P1R' in regions else 0)
base = f'SMART-DS/v1.0/2018/{dataset}/{region}/scenarios/base_timeseries/opendss_no_loadshapes/'
subs = [s for s in folders(base) if s not in ('subtransmission',) and '.' not in s]
sub = c3.selectbox('Substation', subs)
prefix = f'{base}{sub}/'
local = os.path.join(DATA, *prefix.split('/'))
files = listing(prefix)
size_mb = sum(s for _, s in files) / 1e6
have = os.path.exists(os.path.join(local, 'Master.dss'))
st.caption(f'{len(files)} files, {size_mb:.2f} MB · {"downloaded" if have else "not downloaded"} · {prefix}')

a, b, c = st.columns(3)
if a.button('Download', disabled=have):
    with st.spinner(f'Downloading {size_mb:.2f} MB…'):
        ok, out, err = run_script(LAB_PY, 'fetch_smartds.py', [prefix, '--get'], FOLDER)
    if ok:
        st.rerun()
    st.error(err[-800:])
if b.button('Convert to pandapower (MV)', disabled=not have):
    with st.spinner('Solving in OpenDSS and reducing…'):
        ok, out, err = run_script(ELECTRISIM_PY, 'convert_feeder.py', [local], FOLDER)
    if not ok:
        st.error(err[-1200:])
sizes = c.text_input('Sizes to screen (MW)', '1,2,5')
converted = os.path.exists(os.path.join(FOLDER, f'{sub}.pp.json'))
if st.button('Screen the sites', type='primary', disabled=not converted):
    with st.spinner('Running Electrisim\'s site screening (about a minute)…'):
        ok, out, err = run_script(ELECTRISIM_PY, 'screen_sites.py', [sub, sizes], FOLDER)
        if ok:
            ok, out, err = run_script(ELECTRISIM_PY, 'binding_limits.py', [sub], FOLDER)
    if not ok:
        st.error(err[-1200:])

cmp = read_json(os.path.join(FOLDER, f'{sub}.compare.json'))
if cmp:
    st.subheader('The reduction against OpenDSS')
    k = st.columns(4)
    k[0].metric('Source, pandapower', f"{cmp['pandapower_source_p_mw']:.3f} MW")
    k[1].metric('Source, OpenDSS', f"{cmp['opendss_source_p_mw']:.3f} MW")
    k[2].metric('Voltage difference, mean', f"{cmp['v_diff_pu_mean']:.4f} pu")
    k[3].metric('Substation transformer', f"{cmp['substation_transformer_loading_pct'][0]:.1f} %")

scr = read_json(os.path.join(FOLDER, f'{sub}.screening.json'))
bind = read_json(os.path.join(FOLDER, f'{sub}.binding.json'), {})
if scr:
    st.subheader('Sites')
    rows = {}
    for r in scr['screening_results']:
        s = rows.setdefault(r['site_name'], {'Site': r['site_name'], 'Headroom (MW)': r['headroom_mw'],
                                             'Impedance from substation (ohm)': scr['sites'][r['site_name']]['z_from_substation_ohm']})
        s[f"{r['requested_mw']:g} MW: violations"] = r['case_violations']
    for name, s in rows.items():
        first = (bind.get(name) or {}).get('first_of_each_kind') or {}
        s['What limits it'] = '; '.join(f'{k}: {t} {i}' for k, (t, i) in first.items())
    st.dataframe(pd.DataFrame(rows.values()), hide_index=True, width='stretch')

geo = read_json(os.path.join(FOLDER, f'{sub}.geo.json'))
if geo:
    st.subheader('Map')
    pos = {b['bus']: (b['x'], b['y']) for b in geo['buses']}
    xs, ys = [], []
    for f, t in geo['lines']:
        if f in pos and t in pos:
            xs += [pos[f][0], pos[t][0], None]
            ys += [pos[f][1], pos[t][1], None]
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode='lines', line=dict(color='#999', width=1), hoverinfo='skip', name='lines'))
    bus = pd.DataFrame(geo['buses'])
    fig.add_trace(go.Scatter(x=bus.x, y=bus.y, mode='markers', marker=dict(size=5, color=bus.vm_pu, colorscale='Viridis',
                                                                            colorbar=dict(title='V (pu)')),
                             text=bus.bus, name='buses'))
    if scr:
        site_bus = {k: v['bus'] for k, v in scr['sites'].items()}
        sx = [pos[b][0] for b in site_bus.values() if b in pos]
        sy = [pos[b][1] for b in site_bus.values() if b in pos]
        names = [k for k, b in site_bus.items() if b in pos]
        fig.add_trace(go.Scatter(x=sx, y=sy, mode='markers+text', text=[f"{rows[k]['Headroom (MW)']:g} MW" for k in names],
                                 hovertext=[f"{k}: {rows[k]['Headroom (MW)']:g} MW" for k in names], hoverinfo='text',
                                 textposition='top center', marker=dict(size=14, symbol='star', color='crimson'),
                                 name='sites (headroom)'))
    sb = geo['substation_bus']
    if sb in pos:
        fig.add_trace(go.Scatter(x=[pos[sb][0]], y=[pos[sb][1]], mode='markers', marker=dict(size=16, symbol='square', color='black'),
                                 name='substation'))
    fig.update_layout(height=650, xaxis_title='longitude', yaxis_title='latitude', yaxis_scaleanchor='x',
                      legend=dict(orientation='h', yanchor='top', y=-0.12, x=0))
    st.plotly_chart(fig, width='stretch')
