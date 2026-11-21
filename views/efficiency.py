"""ЖИ-дің дәлдігі мен үнемделген уақыт: жобаның тиімділігін растайтын дәлелдер."""
import streamlit as st

from core import state, stats

ss = st.session_state
spec = state.current_spec()
records = state.records_for(spec["id"])

st.title("⏱️ Тиімділік және ЖИ дәлдігі")
st.markdown(
    "Бұл бет жобаның нәтижесін **өлшейді**. ЖИ ұсынған әр ұпай мұғалім растаған ұпаймен салыстырылады, "
    "ал тексеру уақыты автоматты түрде жазылады."
)

if not records:
    st.info("Деректер жоқ. Алдымен бірнеше жұмысты тексеріп, растаңыз.")
    st.stop()

ag = stats.agreement(records)
tm = stats.timing(records)

st.subheader("1. ЖИ бағасының дәлдігі")
c = st.columns(4)
c[0].metric("Тексерілген жұмыс", ag["works"])
c[1].metric("Дескрипторлар бойынша сәйкестік", f"{ag['descriptor_agree_pct']}%",
            help="ЖИ ұпайы мұғалім растаған ұпаймен дәл сәйкес келген дескрипторлар үлесі")
c[2].metric("Жалпы ұпайы дәл сәйкес келген жұмыстар", f"{ag['work_exact_pct']}%")
c[3].metric("±1 ұпай ішінде", f"{ag['work_within1_pct']}%")
st.caption(f"Мұғалім түзеткен дескрипторлар: {ag['corrections']} / {ag['descriptor_n']}. "
           f"Жұмыс бойынша орташа ауытқу: {ag['mean_abs_diff']} ұпай.")

if ag["by_confidence"]:
    names = {"high": "🟢 Жоғары", "medium": "🟡 Орташа", "low": "🔴 Төмен"}
    st.markdown("**ЖИ-дің өз сенімділігі ақталды ма?** Сенімділігі жоғары бағалар дәлірек болуы керек.")
    st.table({names[k]: {"Дескриптор саны": v["n"], "Сәйкестік %": v["agree_pct"]} for k, v in ag["by_confidence"].items()})

st.subheader("2. Уақытты үнемдеу")
ss.manual_minutes = st.number_input(
    "Бір жұмысты қолмен тексеруге кететін орташа уақыт (мин) — секундомермен өлшеп енгізіңіз",
    min_value=0.0, max_value=60.0, step=0.5, value=float(ss.manual_minutes))
with_ai_min = tm["mean_total"] / 60
c = st.columns(3)
c[0].metric("ЖИ талдауы (орташа)", f"{tm['mean_ai']:.0f} сек")
c[1].metric("Мұғалімнің қарап растауы (орташа)", f"{tm['mean_review']/60:.1f} мин")
c[2].metric("«Қадаммен» барлығы", f"{with_ai_min:.1f} мин")
if ss.manual_minutes > 0:
    saved = ss.manual_minutes - with_ai_min
    pct = 100 * saved / ss.manual_minutes
    st.success(f"Бір жұмысқа үнемделген уақыт: **{saved:.1f} мин ({pct:.0f}%)**. "
               f"30 оқушылық сыныпта: **{saved*30:.0f} мин**.")
    st.caption("Ескерту: ЖИ талдап жатқанда мұғалім келесі жұмыстың суретін дайындай алады, "
               "сондықтан нақты үнемдеу бұдан да көп болуы мүмкін.")

st.subheader("3. Әдістеме")
st.markdown("""
1. Бір сыныптың 15–20 жұмысын алдымен **қолмен** тексеріп, уақытты секундомермен өлшеңіз. Ұпайларды жазып қойыңыз.
2. Сол жұмыстарды «Қадам» арқылы тексеріңіз. Растау кезінде ұпайды **өз бағаңызға** сәйкес қойыңыз.
3. Бұл бет сәйкестік пен уақытты автоматты түрде есептейді. Кестені Excel-ге жүктеп, жоба паспортына қосыңыз.
""")
st.download_button("⬇️ Нәтижелерді Excel-ге жүктеу", stats.to_excel(records),
                   file_name=f"Qadam_tiimdilik_{spec['id']}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
