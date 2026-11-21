"""«Қадам» — математикалық жұмыстарды тексеретін ЖИ-көмекші.

Іске қосу:  streamlit run app.py
"""
import streamlit as st

from core import state

st.set_page_config(page_title="Қадам — ЖИ-көмекші", page_icon="✍️", layout="wide")
state.init()

pages = st.navigation([
    st.Page("views/check.py", title="Жұмысты тексеру", icon="✍️", default=True),
    st.Page("views/results.py", title="Сынып нәтижелері", icon="📊"),
    st.Page("views/efficiency.py", title="Тиімділік", icon="⏱️"),
    st.Page("views/bjb_editor.py", title="БЖБ баптау", icon="🧩"),
    st.Page("views/about.py", title="Жоба туралы", icon="ℹ️"),
])
state.sidebar()
pages.run()
