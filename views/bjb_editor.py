"""БЖБ спецификациясын қарау және жаңасын құру."""
import json

import pandas as pd
import streamlit as st

from core import bjb, state

ss = st.session_state
spec = state.current_spec()

st.title("🧩 БЖБ баптау")
st.markdown("ЖИ оқушы жұмысын **сіз енгізген дескрипторлар бойынша** бағалайды. "
            "Дұрыс жауап пен үлгі шешімді толық жазсаңыз, тексеру дәлірек болады.")

tab_view, tab_new, tab_file = st.tabs(["Ағымдағы БЖБ", "➕ Жаңа БЖБ құру", "📁 Файлмен алмасу"])

with tab_view:
    st.subheader(f"{spec.get('grade', '')}-сынып · {spec['title']}")
    if spec.get("learning_objectives"):
        st.markdown("**Оқу мақсаттары:**\n" + "\n".join(f"- {x}" for x in spec["learning_objectives"]))
    for t in spec["tasks"]:
        with st.expander(f"{t['id']}-тапсырма: {t['condition']}"):
            st.markdown(f"**Дұрыс жауап:** {t.get('reference_answer', '—')}")
            if t.get("reference_solution"):
                st.markdown(f"**Үлгі шешім:** {t['reference_solution']}")
            st.dataframe(pd.DataFrame(t["descriptors"]).rename(
                columns={"id": "№", "text": "Дескриптор", "max_points": "Ұпай"}), hide_index=True, use_container_width=True)
    st.metric("Ең жоғары ұпай", bjb.max_total(spec))

with tab_new:
    st.markdown("Әр жолға **бір дескриптор** жазыңыз. Тапсырма шарты мен дұрыс жауапты тапсырманың бірінші жолына ғана жазсаңыз жеткілікті.")
    c1, c2 = st.columns([3, 1])
    title = c1.text_input("БЖБ атауы", placeholder="БЖБ: Ондық бөлшектер")
    grade = c2.text_input("Сынып", placeholder="5")
    template = pd.DataFrame([
        {"Тапсырма №": "1", "Тапсырма шарты": "", "Дұрыс жауап": "", "Дескриптор №": "1.1", "Дескриптор": "", "Ұпай": 1},
        {"Тапсырма №": "1", "Тапсырма шарты": "", "Дұрыс жауап": "", "Дескриптор №": "1.2", "Дескриптор": "", "Ұпай": 1},
    ], columns=bjb.TABLE_COLUMNS)
    table = st.data_editor(template, num_rows="dynamic", use_container_width=True, hide_index=True, key="new_bjb",
                           column_config={"Ұпай": st.column_config.NumberColumn(min_value=1, max_value=10, step=1)})
    if st.button("Сақтау", type="primary"):
        try:
            new = bjb.from_table(title, grade, table)
            ss.bjbs[new["id"]] = new
            ss.current_bjb = new["id"]
            st.success(f"«{new['title']}» сақталды және таңдалды. Ең жоғары ұпай: {bjb.max_total(new)}.")
        except bjb.BJBError as exc:
            st.error(str(exc))

with tab_file:
    st.markdown("БЖБ-ны файл ретінде сақтап, әріптестеріңізбен бөлісуге болады.")
    st.download_button("⬇️ Ағымдағы БЖБ (.json)", json.dumps(spec, ensure_ascii=False, indent=1).encode("utf-8"),
                       file_name=f"{spec['id']}.json", mime="application/json")
    up = st.file_uploader("БЖБ файлын жүктеу (.json)", type=["json"])
    if up is not None and ss.get("_bjb_imported") != up.file_id:
        try:
            new = bjb.validate(json.loads(up.getvalue().decode("utf-8")))
            ss.bjbs[new["id"]] = new
            ss.current_bjb = new["id"]
            ss._bjb_imported = up.file_id
            st.success(f"«{new['title']}» жүктелді.")
        except (bjb.BJBError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            st.error(f"Файл жарамсыз: {exc}")
