"""Негізгі бет: оқушы жұмысын суреттен тексеру → мұғалімнің растауы."""
import time
import uuid
from datetime import datetime

import pandas as pd
import streamlit as st

from core import ai, state, stats
from core.privacy import validate_student_code
from core.taxonomy import ERROR_TYPES, error_label

CONF_ICON = {"high": "🟢 жоғары", "medium": "🟡 орташа", "low": "🔴 төмен"}

ss = st.session_state
spec = state.current_spec()

st.title("✍️ Жұмысты тексеру")
st.caption(f"**{spec.get('grade', '')}-сынып · {spec['title']}** — "
           f"{len(spec['tasks'])} тапсырма, ең жоғары ұпай {sum(d['max_points'] for t in spec['tasks'] for d in t['descriptors'])}")

if not ai.is_configured():
    st.error("ЖИ кілті бапталмаған. «Жоба туралы» бетіндегі нұсқаулықты қараңыз.")

# --------------------------------------------------------------------------- #
# 1-қадам: жұмысты жүктеу
# --------------------------------------------------------------------------- #
if ss.pending is None:
    with st.container(border=True):
        st.markdown("#### 1. Оқушы жұмысын жүктеңіз")
        c1, c2 = st.columns([1, 2])
        with c1:
            code = st.text_input("Оқушы коды", placeholder="5А-12",
                                 help="Аты-жөні емес, тек код. Кодтар тізімі мұғалімде ғана сақталады.")
        with c2:
            files = st.file_uploader("Жұмыстың суреті (бірнеше бет болса, бәрін таңдаңыз)",
                                     type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)
        if files:
            st.image([f.getvalue() for f in files], width=160)
        consent = st.checkbox("Суретте оқушының аты-жөні, беті немесе басқа дербес деректері жоқ екенін растаймын.")
        go = st.button("🔍 Тексеру", type="primary", disabled=not ai.is_configured())

    if go:
        ok, msg = validate_student_code(code)
        if not ok:
            st.warning(msg)
        elif not files:
            st.warning("Кемінде бір сурет жүктеңіз.")
        elif not consent:
            st.warning("Дербес деректер жоқ екенін растаңыз.")
        elif any(r["student_code"] == code.strip() for r in state.records_for(spec["id"])):
            st.warning(f"{code} коды бұл БЖБ бойынша тексерілген. Басқа код енгізіңіз.")
        else:
            with st.spinner("ЖИ жұмысты оқып, қадамдап талдап жатыр… (Google серверлері жүктелген кезде бірнеше минутқа созылуы мүмкін)"):
                try:
                    result, ai_seconds = ai.check_work(spec, [f.getvalue() for f in files])
                except ai.AIError as exc:
                    st.error(str(exc))
                    st.stop()
            ss.pending = {
                "id": uuid.uuid4().hex[:10], "student_code": code.strip(), "bjb_id": spec["id"],
                "images": [f.getvalue() for f in files], "result": result,
                "ai_seconds": ai_seconds, "shown_at": time.time(), "practice": {},
            }
            st.rerun()
    st.stop()

# --------------------------------------------------------------------------- #
# 2-қадам: ЖИ нәтижесі + мұғалімнің растауы
# --------------------------------------------------------------------------- #
p = ss.pending
if p["bjb_id"] != spec["id"]:
    st.info("Сол жақта басқа БЖБ таңдалды. Алдымен ағымдағы жұмысты растаңыз немесе бас тартыңыз.")
    spec = ss.bjbs[p["bjb_id"]]
res = p["result"]

st.markdown(f"#### 2. ЖИ нәтижесін тексеріп, растаңыз — оқушы **{p['student_code']}**")
low = sum(d["confidence"] == "low" for t in res["tasks"] for d in t["descriptors"])
if not res["readable"]:
    st.error("ЖИ жұмысты толық оқи алмады. Барлық ұпайды мұқият тексеріңіз немесе анығырақ суретке түсіріңіз.")
elif low:
    st.warning(f"🔴 {low} дескриптор бойынша ЖИ сенімсіз — оларды міндетті түрде тексеріңіз.")
if res["general_comment"]:
    st.info(res["general_comment"])

img_col, res_col = st.columns([2, 3], gap="large")
with img_col:
    st.image(p["images"], use_container_width=True)

teacher_points: dict[str, int] = {}
teacher_errors: dict[str, list[str]] = {}
feedback: dict[str, str] = {}
codes = list(ERROR_TYPES)

with res_col:
    for task in res["tasks"]:
        tid = task["task_id"]
        got = sum(d["points"] for d in task["descriptors"])
        mx = sum(d["max_points"] for d in task["descriptors"])
        task_low = any(d["confidence"] == "low" for d in task["descriptors"])
        with st.expander(f"{'🔴 ' if task_low else ''}{tid}-тапсырма · ЖИ: {got}/{mx}", expanded=True):
            st.caption(task["condition"])
            st.markdown("**Оқушы жазғаны (ЖИ оқуы):**")
            st.code(task["transcription"], language=None, wrap_lines=True)
            if task["steps"]:
                for s in task["steps"]:
                    icon = "✅" if s["correct"] else "❌"
                    note = f" — _{s['comment']}_" if s["comment"] and not s["correct"] else ""
                    st.markdown(f"{icon} **{s['n']}-қадам:** `{s['text']}`{note}")
            for e in task["errors"]:
                step = f" ({e['step']}-қадам)" if e.get("step") else ""
                st.markdown(f"⚠️ **{error_label(e['code'])}**{step}: {e['explanation']}")

            df = pd.DataFrame([{
                "№": d["id"], "Дескриптор": d["text"], "Макс.": d["max_points"],
                "ЖИ": d["points"], "Мұғалім": d["points"],
                "Сенімділік": CONF_ICON[d["confidence"]], "Дәлел": d["evidence"],
            } for d in task["descriptors"]])
            edited = st.data_editor(
                df, key=f"de_{p['id']}_{tid}", hide_index=True, use_container_width=True,
                disabled=["№", "Дескриптор", "Макс.", "ЖИ", "Сенімділік", "Дәлел"],
                column_config={
                    "Мұғалім": st.column_config.NumberColumn("Мұғалім ✏️", min_value=0, step=1,
                                                             help="Соңғы ұпайды мұғалім қояды"),
                    "Дескриптор": st.column_config.TextColumn(width="medium"),
                    "Дәлел": st.column_config.TextColumn(width="medium"),
                },
            )
            for _, row in edited.iterrows():
                val = row["Мұғалім"]
                teacher_points[row["№"]] = int(val) if pd.notna(val) else 0

            teacher_errors[tid] = st.multiselect(
                "Қателер (қажет болса түзетіңіз)", codes, default=[e["code"] for e in task["errors"]],
                format_func=error_label, key=f"err_{p['id']}_{tid}")
            feedback[tid] = st.text_area("Оқушыға кері байланыс", task["student_feedback"],
                                         key=f"fb_{p['id']}_{tid}", height=80)

            if teacher_errors[tid]:
                if st.button("🎯 Осы қатеге ұқсас жаттығулар", key=f"pr_{p['id']}_{tid}"):
                    with st.spinner("Жаттығулар құрастырылып, жауаптары тексерілуде…"):
                        try:
                            errs = [{"code": c, "explanation": next((e["explanation"] for e in task["errors"] if e["code"] == c), "")}
                                    for c in teacher_errors[tid]]
                            p["practice"][tid] = ai.generate_practice(task, errs)
                        except ai.AIError as exc:
                            st.error(str(exc))
                for i, ex in enumerate(p["practice"].get(tid, []), 1):
                    st.markdown(f"**{i}.** {ex['problem']}  \n💡 _{ex['hint']}_  \n✔️ Жауабы: `{ex['answer']}`")
                if tid in p["practice"]:
                    if p["practice"][tid]:
                        st.caption("✔️ Әр жаттығудың жауабы бағдарламамен дәл есептеліп тексерілді.")
                    else:
                        st.caption("Тексеруден өткен жаттығу болмады — қайта басыңыз.")

total = sum(teacher_points.values())
max_total = sum(d["max_points"] for t in res["tasks"] for d in t["descriptors"])
ai_total = sum(d["points"] for t in res["tasks"] for d in t["descriptors"])
st.divider()
m1, m2, m3 = st.columns(3)
m1.metric("ЖИ ұсынған ұпай", f"{ai_total}/{max_total}")
m2.metric("Соңғы ұпай (мұғалім)", f"{total}/{max_total}", delta=total - ai_total or None)
m3.metric("Деңгей", stats.level_for(100 * total / max_total if max_total else 0))

b1, b2, _ = st.columns([1, 1, 2])
if b1.button("✅ Растау және сақтау", type="primary", use_container_width=True):
    record = stats.build_record(
        record_id=p["id"], student_code=p["student_code"], spec=spec, ai_result=res,
        teacher_points=teacher_points, teacher_errors=teacher_errors, feedback=feedback,
        ai_seconds=p["ai_seconds"], review_seconds=time.time() - p["shown_at"],
        checked_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    ss.results.append(record)
    ss.pending = None
    st.toast(f"{record['student_code']}: {record['total']}/{record['max_total']} сақталды")
    st.rerun()
if b2.button("✖️ Бас тарту", use_container_width=True):
    ss.pending = None
    st.rerun()
