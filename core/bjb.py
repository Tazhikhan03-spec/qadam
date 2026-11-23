"""БЖБ (тапсырмалар + дескрипторлар) спецификацияларымен жұмыс."""
from __future__ import annotations

import json
import re
import zlib
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "bjb"


class BJBError(ValueError):
    pass


def load_builtin() -> dict[str, dict]:
    result = {}
    for path in sorted(DATA_DIR.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        validate(spec)
        result[spec["id"]] = spec
    return result


def validate(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise BJBError("БЖБ файлы JSON-объект болуы керек.")
    for key in ("id", "title", "tasks"):
        if not spec.get(key):
            raise BJBError(f"БЖБ-да «{key}» өрісі жоқ.")
    if not isinstance(spec["tasks"], list):
        raise BJBError("«tasks» тізім болуы керек.")
    seen = set()
    for task in spec["tasks"]:
        if not task.get("id") or not task.get("condition"):
            raise BJBError("Әр тапсырмада «id» және «condition» болуы керек.")
        if not task.get("descriptors"):
            raise BJBError(f"{task['id']}-тапсырмада дескриптор жоқ.")
        for d in task["descriptors"]:
            if not d.get("id") or not d.get("text"):
                raise BJBError(f"{task['id']}-тапсырманың дескрипторы толық емес.")
            if d["id"] in seen:
                raise BJBError(f"Дескриптор нөмірі қайталанады: {d['id']}")
            seen.add(d["id"])
            try:
                d["max_points"] = int(d.get("max_points", 1))
            except (TypeError, ValueError) as exc:
                raise BJBError(f"{d['id']}: ұпай бүтін сан болуы керек.") from exc
            if not 0 < d["max_points"] <= 10:
                raise BJBError(f"{d['id']}: ұпай 1 мен 10 аралығында болуы керек.")
    return spec


def max_total(spec: dict) -> int:
    return sum(d["max_points"] for t in spec["tasks"] for d in t["descriptors"])


def all_descriptors(spec: dict) -> list[dict]:
    return [dict(d, task_id=t["id"]) for t in spec["tasks"] for d in t["descriptors"]]


TABLE_COLUMNS = ["Тапсырма №", "Тапсырма шарты", "Дұрыс жауап", "Үлгі шешім", "Дескриптор №", "Дескриптор", "Ұпай"]


def to_table(spec: dict) -> pd.DataFrame:
    rows = []
    for t in spec["tasks"]:
        for i, d in enumerate(t["descriptors"]):
            rows.append({
                "Тапсырма №": t["id"],
                "Тапсырма шарты": t["condition"] if i == 0 else "",
                "Дұрыс жауап": t.get("reference_answer", "") if i == 0 else "",
                "Үлгі шешім": t.get("reference_solution", "") if i == 0 else "",
                "Дескриптор №": d["id"],
                "Дескриптор": d["text"],
                "Ұпай": d["max_points"],
            })
    return pd.DataFrame(rows, columns=TABLE_COLUMNS)


def slugify(text: str) -> str:
    slug = re.sub(r"[^0-9A-Za-zА-Яа-яӘәІіҢңҒғҮүҰұҚқӨөҺһ]+", "_", text).strip("_").lower()
    return slug[:60] or "bjb"


def from_table(title: str, grade: str, df: pd.DataFrame) -> dict:
    """Мұғалім толтырған кестеден БЖБ спецификациясын құрастырады."""
    df = df.fillna("")
    tasks: dict[str, dict] = {}
    for _, row in df.iterrows():
        tid = str(row["Тапсырма №"]).strip()
        if not tid:
            continue
        task = tasks.setdefault(tid, {"id": tid, "condition": "", "reference_answer": "",
                                     "reference_solution": "", "descriptors": []})
        if str(row["Тапсырма шарты"]).strip():
            task["condition"] = str(row["Тапсырма шарты"]).strip()
        if str(row["Дұрыс жауап"]).strip():
            task["reference_answer"] = str(row["Дұрыс жауап"]).strip()
        if str(row.get("Үлгі шешім", "")).strip():
            task["reference_solution"] = str(row["Үлгі шешім"]).strip()
        did = str(row["Дескриптор №"]).strip()
        dtext = str(row["Дескриптор"]).strip()
        if did and dtext:
            try:
                pts = int(float(row["Ұпай"] or 1))
            except (TypeError, ValueError):
                pts = 1
            task["descriptors"].append({"id": did, "text": dtext, "max_points": pts})
    spec = {
        "id": f"custom_{slugify(title)[:40]}_{zlib.crc32(title.strip().encode()):08x}",
        "title": title.strip() or "Жаңа БЖБ",
        "grade": str(grade).strip(),
        "subject": "Математика",
        "learning_objectives": [],
        "tasks": list(tasks.values()),
    }
    return validate(spec)
