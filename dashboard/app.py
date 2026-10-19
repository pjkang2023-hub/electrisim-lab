"""
The electrisim-lab dashboard: one page per experiment.
    .venv\\Scripts\\streamlit.exe run dashboard\\app.py        (http://127.0.0.1:8502)
"""
import streamlit as st

st.set_page_config(page_title='Electrisim lab', layout='wide')

pages = [
    st.Page('home.py', title='Overview', default=True),
    st.Page('p1_opf.py', title='1 · AC/DC optimal power flow'),
    st.Page('p2_feeder.py', title='2 · Feeder site screening'),
    st.Page('p3_year.py', title='3 · Annual sizing'),
    st.Page('p4_surrogate.py', title='4 · Surrogate design'),
]
st.navigation(pages).run()
