"""Расталған нәтижелер бойынша статистика: сынып талдауы және ЖИ дәлдігі."""
from __future__ import annotations

import io
from collections import Counter

import pandas as pd

from .taxonomy import ERROR_TYPES

LEVELS = [(85, "Жоғары"), (50, "Орта"), (0, "Төмен")]


def level_for(percent: float) -> str:
    for threshold, name in LEVELS:
        if percent >= threshold:
            return name
    return "Төмен"


def build_record(*, record_id: str, student_code: str, spec: dict, ai_result: dict,
                 teacher_points: dict[str, int], teacher_errors: dict[str, list[str]],
                 feedback: dict[str, str], ai_seconds: float, review_seconds: float,
                 checked_at: str) -> dict:
    descriptors = []
    for task in ai_result["tasks"]:
        for d in task["descriptors"]:
            tp = int(teacher_points.get(d["id"], d["points"]))
            descriptors.append({
                "task_id": task["task_id"], "id": d["id"], "text": d["text"],
                "max_points": d["max_points"], "ai_points": d["points"],
                "teacher_points": max(0, min(tp, d["max_points"])), "confidence": d["confidence"],
            })
    ai_errors = [{"task_id": t["task_id"], "code": e["code"]} for t in ai_result["tasks"] for e in t["errors"]]
    final_errors = [{"task_id": tid, "code": c} for tid, codes in teacher_errors.items() for c in codes]
    total = sum(d["teacher_points"] for d in descriptors)
    max_total = sum(d["max_points"] for d in descriptors)
    percent = round(100 * total / max_total, 1) if max_total else 0.0
    return {
        "id": record_id, "student_code": student_code, "bjb_id": spec["id"], "bjb_title": spec["title"],
        "checked_at": checked_at, "ai_seconds": round(ai_seconds, 1), "review_seconds": round(review_seconds, 1),
        "descriptors": descriptors, "ai_errors": ai_errors, "errors": final_errors,
        "total": total, "ai_total": sum(d["ai_points"] for d in descriptors), "max_total": max_total,
        "percent": percent, "level": level_for(percent), "feedback": feedback,
    }


def students_table(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Оқушы коды": r["student_code"], "Ұпай": r["total"], "Макс.": r["max_total"],
        "%": r["percent"], "Деңгей": r["level"],
        "Қателер": ", ".join(sorted({e["code"] for e in r["errors"]})) or "—",
    } for r in records])


def descriptor_table(records: list[dict]) -> pd.DataFrame:
    agg: dict[str, dict] = {}
    for r in records:
        for d in r["descriptors"]:
            a = agg.setdefault(d["id"], {"Дескриптор №": d["id"], "Дескриптор": d["text"], "_got": 0, "_max": 0, "Орындады": 0, "Оқушы саны": 0})
            a["_got"] += d["teacher_points"]
            a["_max"] += d["max_points"]
            a["Оқушы саны"] += 1
            a["Орындады"] += int(d["teacher_points"] == d["max_points"])
    rows = []
    for a in agg.values():
        a["Орындау %"] = round(100 * a["_got"] / a["_max"], 1) if a["_max"] else 0.0
        rows.append({k: v for k, v in a.items() if not k.startswith("_")})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Дескриптор №", key=lambda s: s.map(_sort_key)).reset_index(drop=True)
    return df


def _sort_key(x: str):
    return tuple(int(p) if p.isdigit() else p for p in str(x).replace("-", ".").split("."))


def error_table(records: list[dict]) -> pd.DataFrame:
    counter = Counter(e["code"] for r in records for e in r["errors"])
    students = Counter(code for r in records for code in {e["code"] for e in r["errors"]})
    rows = [{"Код": c, "Қате түрі": ERROR_TYPES.get(c, (c,))[0], "Саны": n, "Оқушы саны": students[c]}
            for c, n in counter.most_common()]
    return pd.DataFrame(rows, columns=["Код", "Қате түрі", "Саны", "Оқушы саны"])


def agreement(records: list[dict]) -> dict:
    """ЖИ ұсынған ұпайлар мен мұғалім растаған ұпайлардың сәйкестігі."""
    pairs = [(d["ai_points"], d["teacher_points"], d["confidence"]) for r in records for d in r["descriptors"]]
    if not pairs:
        return {}
    same = sum(a == t for a, t, _ in pairs)
    by_conf = {}
    for level in ("high", "medium", "low"):
        sub = [(a, t) for a, t, c in pairs if c == level]
        if sub:
            by_conf[level] = {"n": len(sub), "agree_pct": round(100 * sum(a == t for a, t in sub) / len(sub), 1)}
    work_exact = sum(r["ai_total"] == r["total"] for r in records)
    work_within1 = sum(abs(r["ai_total"] - r["total"]) <= 1 for r in records)
    return {
        "descriptor_n": len(pairs),
        "descriptor_agree_pct": round(100 * same / len(pairs), 1),
        "corrections": len(pairs) - same,
        "works": len(records),
        "work_exact_pct": round(100 * work_exact / len(records), 1),
        "work_within1_pct": round(100 * work_within1 / len(records), 1),
        "mean_abs_diff": round(sum(abs(r["ai_total"] - r["total"]) for r in records) / len(records), 2),
        "by_confidence": by_conf,
    }


def timing(records: list[dict]) -> dict:
    if not records:
        return {}
    ai = [r["ai_seconds"] for r in records]
    rev = [r["review_seconds"] for r in records]
    total = [a + b for a, b in zip(ai, rev)]
    return {"mean_ai": sum(ai) / len(ai), "mean_review": sum(rev) / len(rev), "mean_total": sum(total) / len(total)}


def aggregated_for_ai(records: list[dict], spec: dict) -> dict:
    """ЖИ-ге жіберілетін анонимді жинақ: оқушы кодтары ЖОҚ."""
    levels = Counter(r["level"] for r in records)
    return {
        "bjb": spec["title"], "grade": spec.get("grade"), "students": len(records),
        "mean_percent": round(sum(r["percent"] for r in records) / len(records), 1),
        "levels": dict(levels),
        "descriptors": descriptor_table(records)[["Дескриптор №", "Дескриптор", "Орындау %"]].to_dict("records"),
        "errors": error_table(records)[["Қате түрі", "Оқушы саны"]].to_dict("records"),
    }


def to_excel(records: list[dict], analysis: dict | None = None) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        students_table(records).to_excel(xw, sheet_name="Оқушылар", index=False)
        descriptor_table(records).to_excel(xw, sheet_name="Дескрипторлар", index=False)
        error_table(records).to_excel(xw, sheet_name="Қателер", index=False)
        pd.DataFrame([{
            "Оқушы коды": r["student_code"], "ЖИ ұпайы": r["ai_total"], "Мұғалім ұпайы": r["total"],
            "ЖИ уақыты, сек": r["ai_seconds"], "Мұғалімнің қарау уақыты, сек": r["review_seconds"],
            "Тексерілген уақыт": r["checked_at"],
        } for r in records]).to_excel(xw, sheet_name="ЖИ дәлдігі", index=False)
        if analysis:
            rows = [("Қорытынды", analysis["summary"])]
            rows += [("Қиындықтар", x) for x in analysis["difficulties"]]
            rows += [("Себептері", x) for x in analysis["causes"]]
            rows += [("Түзету жоспары", x) for x in analysis["correction_plan"]]
            pd.DataFrame(rows, columns=["Бөлім", "Мазмұны"]).to_excel(xw, sheet_name="Талдау", index=False)
    return out.getvalue()
