"""БЖБ спецификациясын қарау және жаңасын құру."""
import json

import pandas as pd
import streamlit as st

from core import ai, bjb, importer, state

ss = st.session_state
spec = state.current_spec()

st.title("🧩 БЖБ баптау")
st.markdown("ЖИ оқушы жұмысын **сіз енгізген дескрипторлар бойынша** бағалайды. "
            "Дұрыс жауап пен үлгі шешімді толық жазсаңыз, тексеру дәлірек болады.")

if ss.get("_bjb_msg"):
    st.success(ss.pop("_bjb_msg"))

tab_view, tab_doc, tab_new, tab_file = st.tabs(
    ["Ағымдағы БЖБ", "📄 Word / PDF жүктеу", "➕ Жаңа БЖБ құру", "📁 Файлмен алмасу"])

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

with tab_doc:
    st.markdown("БЖБ файлын (.docx немесе .pdf) жүктеңіз. Үлгі пішіндегі Word файлын бағдарлама **ЖИ-сіз бірден** оқиды, "
                "басқа Word пен PDF-ті ЖИ бөліктерге ажыратады. "
                "**Сақтамас бұрын кестені өзіңіз тексеріп, түзетіңіз.**")
    doc = st.file_uploader("БЖБ файлы", type=["docx", "pdf"], key="bjb_doc")
    force_ai = st.checkbox("Word файлын да ЖИ-мен оқу")
    st.caption("ЖИ қолданылса, файл Google Gemini-ге жіберіледі. Файлда адамдардың аты-жөні болмасын.")
    if st.button("📖 Файлды оқу", type="primary", disabled=doc is None):
        ss.pop("_bjb_draft", None)
        with st.spinner("Файл оқылып жатыр… (ЖИ серверлері жүктелгенде бірнеше минутқа созылуы мүмкін)"):
            try:
                found = None if force_ai else importer.extract_without_ai(doc.name, doc.getvalue())
                used_ai = found is None
                if used_ai:
                    found = importer.extract(doc.name, doc.getvalue())
                ss["_bjb_draft"] = {"file_id": doc.file_id, "variants": found, "used_ai": used_ai,
                                    "run": ss.get("_bjb_run", 0) + 1}
                ss["_bjb_run"] = ss["_bjb_draft"]["run"]
            except (importer.ImportFileError, ai.AIError) as exc:
                st.error(str(exc))
    draft = ss.get("_bjb_draft")
    if draft and doc is not None and draft["file_id"] == doc.file_id:
        variants = draft["variants"]
        st.info("Файлды ЖИ оқыды. Әр жолын тексеріңіз." if draft["used_ai"]
                else "Файлды бағдарлама ЖИ-сіз оқыды. Әр жолын тексеріңіз.")
        n = 0
        if len(variants) > 1:
            n = st.radio("Файлда бірнеше нұсқа бар. Қайсысын тексересіз?", range(len(variants)),
                         format_func=lambda k: variants[k]["title"], key=f"var_{doc.file_id}_{draft['run']}")
        v = variants[n]
        key = f"{doc.file_id}_{draft['run']}_{n}"
        for msg in v["warnings"]:
            st.warning(msg)
        d1, d2 = st.columns([3, 1])
        d_title = d1.text_input("БЖБ атауы", v["title"], key=f"t_{key}")
        d_grade = d2.text_input("Сынып", v["grade"], key=f"g_{key}")
        d_table = st.data_editor(v["table"], num_rows="dynamic", use_container_width=True, hide_index=True,
                                 key=f"e_{key}",
                                 column_config={"Ұпай": st.column_config.NumberColumn(min_value=1, max_value=10, step=1)})
        st.caption(f"Балл қосындысы: **{int(pd.to_numeric(d_table['Ұпай'], errors='coerce').fillna(0).sum())}**")
        if st.button("✅ Тексердім, сақтау", key=f"s_{key}"):
            try:
                new = bjb.from_table(d_title, d_grade, d_table)
                ss.bjbs[new["id"]] = new
                ss.current_bjb = new["id"]
                ss["_bjb_msg"] = f"«{new['title']}» сақталды және таңдалды. Ең жоғары ұпай: {bjb.max_total(new)}."
                st.rerun()
            except bjb.BJBError as exc:
                st.error(str(exc))

with tab_new:
    st.markdown("Әр жолға **бір дескриптор** жазыңыз. Тапсырма шарты мен дұрыс жауапты тапсырманың бірінші жолына ғана жазсаңыз жеткілікті.")
    c1, c2 = st.columns([3, 1])
    title = c1.text_input("БЖБ атауы", placeholder="БЖБ: Ондық бөлшектер")
    grade = c2.text_input("Сынып", placeholder="5")
    template = pd.DataFrame([
        {"Тапсырма №": "1", "Тапсырма шарты": "", "Дұрыс жауап": "", "Үлгі шешім": "", "Дескриптор №": "1.1", "Дескриптор": "", "Ұпай": 1},
        {"Тапсырма №": "1", "Тапсырма шарты": "", "Дұрыс жауап": "", "Үлгі шешім": "", "Дескриптор №": "1.2", "Дескриптор": "", "Ұпай": 1},
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
