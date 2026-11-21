"""Сынып нәтижелері, қателер картасы және БЖБ талдауы."""
import streamlit as st

from core import ai, state, stats

ss = st.session_state
spec = state.current_spec()
records = state.records_for(spec["id"])

st.title("📊 Сынып нәтижелері")
st.caption(f"{spec.get('grade', '')}-сынып · {spec['title']}")

if not records:
    st.info("Әзірге расталған жұмыс жоқ. «Жұмысты тексеру» бетінде жұмыстарды тексеріп, растаңыз.")
    st.stop()

mean = sum(r["percent"] for r in records) / len(records)
levels = {name: sum(r["level"] == name for r in records) for _, name in stats.LEVELS}
c = st.columns(5)
c[0].metric("Жұмыстар", len(records))
c[1].metric("Орташа нәтиже", f"{mean:.0f}%")
c[2].metric("Жоғары (≥85%)", levels["Жоғары"])
c[3].metric("Орта (50–84%)", levels["Орта"])
c[4].metric("Төмен (<50%)", levels["Төмен"])

tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Қателер картасы", "📌 Дескрипторлар", "👥 Оқушылар", "📝 БЖБ талдауы"])

with tab1:
    err = stats.error_table(records)
    if err.empty:
        st.success("Расталған қателер жоқ.")
    else:
        st.markdown("**Қай қате қанша оқушыда кездесті** — түзету жұмысын осыдан бастаңыз.")
        st.bar_chart(err.set_index("Қате түрі")["Оқушы саны"], horizontal=True, color="#d9534f")
        st.dataframe(err, hide_index=True, use_container_width=True)

with tab2:
    dt = stats.descriptor_table(records)
    st.markdown("**Әр дескрипторды орындау пайызы.** 50%-дан төмен — сынып меңгермеген оқу мақсаты.")
    st.dataframe(
        dt, hide_index=True, use_container_width=True,
        column_config={"Орындау %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%")},
    )
    weak = dt[dt["Орындау %"] < 50]
    if not weak.empty:
        st.warning("Меңгерілмеген: " + "; ".join(f"{r['Дескриптор №']} {r['Дескриптор']}" for _, r in weak.iterrows()))

with tab3:
    st.dataframe(stats.students_table(records), hide_index=True, use_container_width=True)
    st.markdown("**Оқушыларға кері байланыс**")
    for r in records:
        with st.expander(f"{r['student_code']} — {r['total']}/{r['max_total']}"):
            for tid, text in r["feedback"].items():
                if text:
                    st.markdown(f"**{tid}-тапсырма:** {text}")
    if st.button("🗑️ Соңғы нәтижені өшіру"):
        last = records[-1]
        ss.results = [x for x in ss.results if x["id"] != last["id"]]
        st.rerun()

with tab4:
    st.markdown("ЖИ-ге **тек жинақталған анонимді статистика** жіберіледі (оқушы кодтары жіберілмейді). "
                "Мәтінді әдістемелік бірлестікке тапсырмас бұрын тексеріп, өңдеңіз.")
    if st.button("✍️ Талдау мәтінін құрастыру", type="primary", disabled=not ai.is_configured()):
        with st.spinner("Талдау жазылуда…"):
            try:
                ss.analysis[spec["id"]] = ai.class_analysis(stats.aggregated_for_ai(records, spec))
            except ai.AIError as exc:
                st.error(str(exc))
    a = ss.analysis.get(spec["id"])
    if a:
        st.markdown(f"**Қорытынды.** {a['summary']}")
        for title, key in (("Қиындық туғызған тапсырмалар", "difficulties"), ("Ықтимал себептері", "causes"),
                           ("Түзету жұмысының жоспары", "correction_plan")):
            if a[key]:
                st.markdown(f"**{title}:**\n" + "\n".join(f"- {x}" for x in a[key]))

st.divider()
st.download_button("⬇️ Excel-ге жүктеу (барлық кестелер + талдау)",
                   stats.to_excel(records, ss.analysis.get(spec["id"])),
                   file_name=f"BJB_taldau_{spec['id']}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
