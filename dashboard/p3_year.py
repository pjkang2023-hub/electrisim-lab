import logging
import warnings

import pandas as pd
import plotly.express as px
import streamlit as st

import factory_year as F   # 03_pypsa_sizing

warnings.filterwarnings('ignore')
logging.disable(logging.WARNING)
D = F.CASE_DEFAULTS

st.title('3 · Annual sizing')
st.write('The 800 VDC factory as one bus over 8,760 hours in PyPSA: the battery sized, the turbine and the '
         'utility dispatched against the tariff. Every input below is an assumption, not the whitepaper\'s.')

with st.form('year'):
    st.subheader('Load')
    a, b = st.columns(2)
    racks = a.number_input('Racks, flat (MW)', 0.0, 200.0, D['racks_mw'])
    cooling = b.number_input('Cooling, mean (MW)', 0.0, 50.0, D['cooling_mw'])
    st.subheader('Utility')
    a, b, c, d, e = st.columns(5)
    grid = a.number_input('Import limit (MW)', 0.0, 500.0, D['grid_mw'])
    off = b.number_input('Off-peak $/MWh (22-07)', 0.0, 1000.0, D['off'])
    mid = c.number_input('Mid $/MWh', 0.0, 1000.0, D['mid'])
    on = d.number_input('On-peak $/MWh (14-20, Jun-Sep)', 0.0, 2000.0, D['on'])
    demand = e.number_input('Demand charge $/kW-month', 0.0, 100.0, 0.0)
    st.subheader('Gas turbine and battery')
    a, b, c, d, e = st.columns(5)
    gt = a.number_input('Turbine (MW, 0 = standby)', 0.0, 500.0, D['gt_mw'])
    gt_cost = b.number_input('Turbine $/MWh', 0.0, 1000.0, D['gt_cost'])
    battery = c.checkbox('Allow a battery', True)
    mw_cost = d.number_input('Battery $/MW-yr', 0.0, 1e6, D['bat_mw_cost'], step=5000.0)
    mwh_cost = e.number_input('Battery $/MWh-yr', 0.0, 1e6, D['bat_mwh_cost'], step=5000.0)
    backup = st.slider('Back-up required (minutes of the site\'s peak from the battery; 0 = none)', 0, 60, 0)
    go = st.form_submit_button('Optimise the year', type='primary')

if go:
    with st.spinner('Solving 8,760 hours with HiGHS…'):
        s, n, series = F.run_network('dashboard', racks_mw=racks, cooling_mw=cooling, grid_mw=grid, off=off, mid=mid, on=on,
                                     demand_usd_kw_month=demand, gt_mw=gt, gt_cost=gt_cost, battery=battery,
                                     bat_mw_cost=mw_cost, bat_mwh_cost=mwh_cost, backup_min=float(backup))
    st.session_state['year_result'] = (s, series)

if 'year_result' in st.session_state:
    s, series = st.session_state['year_result']
    if s['status'] != 'ok':
        st.error(f"Not solved: {s['status']}. The import limit and turbine may not cover the load.")
    else:
        k = st.columns(5)
        k[0].metric('Cost a year', f"{s['total_cost_usd'] / 1e6:.3f} M$")
        k[1].metric('Utility', f"{s['grid_mwh'] / 1e3:.1f} GWh", f"peak {s['grid_peak_mw']:.2f} MW", delta_color='off')
        k[2].metric('Turbine', f"{s['gt_mwh'] / 1e3:.1f} GWh", f"{s['gt_full_load_hours']:.0f} h at full load", delta_color='off')
        if 'battery_mw' in s:
            k[3].metric('Battery', f"{s['battery_mw']:.2f} MW / {s['battery_mwh']:.2f} MWh")
            k[4].metric('Battery cycles a year', f"{s['battery_cycles']:.1f}")
        week = st.slider('Week to plot', 1, 52, 28)
        w = series.iloc[(week - 1) * 168: week * 168]
        cols = [c for c in ('utility', 'gas turbine', 'battery discharge') if c in w]
        fig = px.area(w[cols], title=f'Supply, week {week} (MW)')
        fig.add_scatter(x=w.index, y=w['load'], name='load', line=dict(color='black'))
        st.plotly_chart(fig, width='stretch')
        a, b = st.columns(2)
        a.plotly_chart(px.line(w['price'], title='Tariff ($/MWh)'), width='stretch')
        if 'battery energy' in w:
            b.plotly_chart(px.line(w['battery energy'], title='Battery energy (MWh)'), width='stretch')
        with st.expander('Every figure'):
            st.json(s)
