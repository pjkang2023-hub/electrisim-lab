import os

import streamlit as st

from common import ELECTRISIM_PY, LAB, LAB_PY

st.title('Electrisim lab')
st.write(
    'Experiments with outside tools on Electrisim\'s reference networks, kept apart from the '
    'Electrisim install. Nothing here changes Electrisim; pages that need its studies call its '
    'backend read-only with its own Python.')
st.markdown('''
| Page | Question | Tools |
|---|---|---|
| **1 · AC/DC optimal power flow** | The PCS3750C-MV references with their DC buses, converter circles and batteries; the least load to shed when no dispatch exists | Pyomo, Ipopt |
| **2 · Feeder site screening** | Where a data center can connect on a real-looking utility feeder (SMART-DS), with Electrisim's own screening | OpenDSS, pandapower, Electrisim |
| **3 · Annual sizing** | The 800 VDC factory's battery and turbine over a year against a tariff; what back-up costs | PyPSA, HiGHS |
| **4 · Surrogate design** | A neural-network surrogate of the factory island's EMT, and the least store rating that holds the 800 V | OMLT, scikit-learn, HiGHS |
''')
st.caption(f'Lab Python: `{LAB_PY}` ({"found" if os.path.exists(LAB_PY) else "missing"}) · '
           f'Electrisim Python: `{ELECTRISIM_PY}` ({"found" if os.path.exists(ELECTRISIM_PY) else "missing"})')
st.caption(f'Each experiment\'s README in `{LAB}` states its method, results and limits.')
