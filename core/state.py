"""Сессия күйі: таңдалған БЖБ, расталған нәтижелер, жұмыс файлын сақтау/жүктеу."""
from __future__ import annotations

import json

import streamlit as st

from . import bjb


def init() -> None:
    ss = st.session_state
    if "bjbs" not in ss:
        ss.bjbs = bjb.load_builtin()
    ss.setdefault("current_bjb", next(iter(ss.bjbs)))
    ss.setdefault("results", [])
    ss.setdefault("pending", None)
    ss.setdefault("analysis", {})
    ss.setdefault("manual_minutes", 0.0)


def current_spec() -> dict:
    return st.session_state.bjbs[st.session_state.current_bjb]


def records_for(bjb_id: str) -> list[dict]:
    return [r for r in st.session_state.results if r["bjb_id"] == bjb_id]


def export_session() -> bytes:
    ss = st.session_state
    builtin = set(bjb.load_builtin())
    data = {
        "version": 1,
        "custom_bjbs": [s for k, s in ss.bjbs.items() if k not in builtin],
        "results": ss.results,
        "manual_minutes": ss.manual_minutes,
    }
    return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")


def import_session(raw: bytes) -> int:
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or "results" not in data:
        raise ValueError("Бұл «Қадам» жұмыс файлы емес.")
    ss = st.session_state
    for spec in data.get("custom_bjbs", []):
        ss.bjbs[spec["id"]] = bjb.validate(spec)
    known = {r["id"] for r in ss.results}
    added = [r for r in data["results"] if r.get("id") not in known and r.get("bjb_id") in ss.bjbs]
    ss.results.extend(added)
    ss.manual_minutes = float(data.get("manual_minutes", ss.manual_minutes) or 0)
    return len(added)


def sidebar() -> None:
    ss = st.session_state
    with st.sidebar:
        st.markdown("### 📋 БЖБ")
        labels = {f"{s.get('grade', '')}-сынып · {s['title']}": k for k, s in ss.bjbs.items()}
        names = list(labels)
        current = next((n for n, k in labels.items() if k == ss.current_bjb), names[0])
        chosen = st.selectbox("Тексерілетін БЖБ", names, index=names.index(current),
                              label_visibility="collapsed")
        ss.current_bjb = labels[chosen]
        n = len(records_for(ss.current_bjb))
        st.caption(f"Расталған жұмыстар: **{n}**")
        st.divider()
        st.markdown("### 💾 Жұмыс файлы")
        st.caption("Беттің жаңартылуы деректерді өшіреді. Жұмыс соңында файлды сақтап, келесіде жүктеңіз.")
        st.download_button("Сақтау (.json)", export_session(), file_name="qadam_jumys.json",
                           mime="application/json", use_container_width=True)
        up = st.file_uploader("Жүктеу", type=["json"], key="session_upload", label_visibility="collapsed")
        if up is not None and ss.get("_imported") != up.file_id:
            try:
                added = import_session(up.getvalue())
                ss._imported = up.file_id
                st.success(f"{added} нәтиже жүктелді.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Файлды оқу мүмкін болмады: {exc}")
