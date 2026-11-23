"""Үлгі пішіндегі Word БЖБ-сын ЖИ-сіз оқу (ережелер бойынша).

Танылатын пішін:
  - «Математика | 5-сынып | 1-нұсқа» жолы, «Бөлім: ...» жолы;
  - «1-тапсырма. ... (2 балл)» тақырыптары;
  - «Дескриптор» және «Балл» бағандары бар кесте;
  - міндетті емес: «Тапсырма | Дұрыс жауап» кестесі, «Үлгі шешімдер» бөлімі.
Пішін сәйкес келмесе None қайтарады — онда файлды ЖИ оқиды.
"""
from __future__ import annotations

import re

VARIANT = re.compile(r"(\d+)\s*-\s*нұсқа", re.I)
TASK = re.compile(r"^(\d+)\s*-\s*тапсырма\.?\s*(.*?)\s*\((\d+)\s*балл\)\s*$", re.I)
KEY = re.compile(r"^(\d+)\s*([а-яәіңғүұқөһ])?$", re.I)
SOLUTION = re.compile(r"^(\d+)\)\s*(.+)$")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.split("|")]


def _clean(line: str) -> str:
    line = re.sub(r"_{2,}", "", line).strip()
    return "" if re.fullmatch(r"(Жауабы|Шешуі)\s*:?", line) else line.rstrip(" =").strip()


def parse(text: str) -> dict | None:
    lines = [x.strip() for x in text.split("\n")]
    cut = next((i for i, x in enumerate(lines) if x.upper().startswith("МҰҒАЛІМГЕ")), None)
    if cut is None:
        return None
    student, teacher = lines[:cut], lines[cut:]

    # 1. Оқушы парағы: нұсқалар мен тапсырмалар
    variants: list[dict] = []
    grade = section = ""
    cur = task = None
    for line in student:
        g = re.search(r"(\d+)\s*-\s*сынып", line, re.I)
        v = VARIANT.search(line)
        if g and v and not TASK.match(line):
            grade = g.group(1)
            cur = {"n": int(v.group(1)), "grade": grade, "section": "", "tasks": []}
            variants.append(cur)
            task = None
            continue
        if cur is None:
            continue
        if line.lower().startswith("бөлім:"):
            section = line.split(":", 1)[1].strip()
            cur["section"] = section
            continue
        m = TASK.match(line)
        if m:
            task = {"id": m.group(1), "head": m.group(2), "declared": int(m.group(3)), "body": []}
            cur["tasks"].append(task)
        elif line.startswith("Сәттілік"):
            task = None
        elif task is not None and not line.upper().startswith("БӨЛІМ БОЙЫНША"):
            c = _clean(line)
            if c:
                task["body"].append(c)
    if not variants or any(not v["tasks"] for v in variants):
        return None
    if len({v["n"] for v in variants}) != len(variants):
        return None

    # 2. Мұғалім парағы: дескриптор кестесі, жауап кілті, үлгі шешімдер
    descs: dict[str, list[dict]] = {}
    key: dict[str, list[tuple[str, str]]] = {}
    sols: dict[tuple[int, str], str] = {}
    mode, head, last, sol_variant, in_sol = None, [], "", variants[0]["n"], False
    for line in teacher:
        cells = _cells(line)
        low = [c.lower() for c in cells]
        if len(cells) >= 3 and any(c.startswith("дескриптор") for c in low) and "балл" in low:
            mode, head, last = "desc", low, ""
            continue
        if len(cells) == 2 and low[0] == "тапсырма" and "жауап" in low[1]:
            mode = "key"
            continue
        if line.lower().startswith("үлгі шешім"):
            mode, in_sol = None, True
            continue
        if mode and len(cells) != (len(head) if mode == "desc" else 2):
            mode = None
        if mode == "desc":
            di = next(i for i, c in enumerate(head) if c.startswith("дескриптор"))
            pi = head.index("балл")
            if low[0] == "барлығы" or not cells[di]:
                continue
            if not cells[pi].isdigit():
                return None
            if "тапсырма" in head and "№" in head:          # біріктірілген пішін
                last = cells[head.index("тапсырма")] or last
                did, tid = cells[head.index("№")], last
            else:                                            # №, Дескриптор, Балл
                tid = cells[0]
                did = f"{tid}.1"
            answers = {int(m.group(1)): cells[i] for i, c in enumerate(head) if (m := VARIANT.fullmatch(c))}
            descs.setdefault(tid, []).append(
                {"id": did, "text": cells[di], "points": int(cells[pi]), "answers": answers})
        elif mode == "key":
            m = KEY.match(cells[0])
            if m:
                key.setdefault(m.group(1), []).append(((m.group(2) or "").lower(), cells[1]))
        elif in_sol:
            v = VARIANT.fullmatch(line)
            m = SOLUTION.match(line)
            if v:
                sol_variant = int(v.group(1))
            elif m:
                sols[(sol_variant, m.group(1))] = m.group(2)
    if not descs:
        return None
    if len(variants) > 1 and key:
        return None     # жауап кілтінің қай нұсқаға тиесілі екені белгісіз

    # 3. Біріктіру
    out = []
    for v in variants:
        warnings, tasks = [], []
        for t in v["tasks"]:
            ds = descs.get(t["id"])
            if not ds:
                return None
            condition = " ".join([t["head"]] + t["body"])
            if ds[0]["answers"]:
                if v["n"] not in ds[0]["answers"]:
                    return None
                answer = "; ".join(f"{d['id']}: {d['answers'].get(v['n'], '')}" for d in ds)
            else:
                parts = []
                for letter, value in key.get(t["id"], []):
                    if letter and letter + ")" not in condition:
                        warnings.append(f"Жауап кілтінде {t['id']}{letter} бар, бірақ оқушы парағында ондай тапсырма жоқ. Ол алынбады.")
                        continue
                    parts.append(f"{letter}) {value}" if letter else value)
                answer = "; ".join(parts)
            tasks.append({"id": t["id"], "condition": condition, "answer": answer,
                          "solution": sols.get((v["n"], t["id"]), ""), "declared_points": t["declared"],
                          "descriptors": [{"id": d["id"], "text": d["text"], "points": d["points"]} for d in ds]})
        extra = set(descs) - {t["id"] for t in v["tasks"]}
        if extra:
            return None
        out.append({"title": f"БЖБ: {v['section'] or 'математика'}, {v['n']}-нұсқа", "grade": v["grade"],
                    "warnings": warnings, "tasks": tasks})
    return {"variants": out}
