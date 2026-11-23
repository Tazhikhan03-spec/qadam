"""Gemini арқылы жұмыс: шешімді тексеру, жаттығу құрастыру, сынып талдауы.

ЖИ-ге сурет, БЖБ спецификациясы (немесе БЖБ файлы) және талдау кезінде жинақталған
статистика жіберіледі. Оқушы коды жіберілмейді; суретте аты-жөн болмауын мұғалім тексереді.
"""
from __future__ import annotations

import io
import json
import os
import re
import time

from . import verify
from .taxonomy import ERROR_TYPES, taxonomy_for_prompt

DEFAULT_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-flash-latest"]
_WORKING_MODEL: str | None = None
ROUND_PAUSES = (0, 5, 15, 25, 25)   # серверлер бос болмаса, барлық модельді қайта сынау
TOTAL_SECONDS = 180                 # жаңа сұрау басталатын уақыт шегі (соңғысы + REQUEST_SECONDS)
REQUEST_SECONDS = 90
CONFIDENCE = ("high", "medium", "low")


class AIError(Exception):
    """Мұғалімге түсінікті тілде көрсетілетін қате."""


# --------------------------------------------------------------------------- #
# Баптаулар
# --------------------------------------------------------------------------- #
def _secret(name: str) -> str | None:
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name)


def is_configured() -> bool:
    return bool(_secret("GEMINI_API_KEY"))


_FLASH_RE = re.compile(r"^(?:models/)?gemini-(\d+(?:\.\d+)?)-flash(-lite)?$")
_DISCOVERED: list[str] | None = None


def _discover_flash(client) -> list[str]:
    """Аккаунтқа қолжетімді «gemini-N-flash» модельдерін табады: алдымен ең жаңа
    толық модельдер, соңында жеңіл (lite) модельдер — Google ескі модельдерді
    өшірсе немесе бір модель бос болмаса да қосымша жұмысын жалғастырады."""
    global _DISCOVERED
    if _DISCOVERED is not None:
        return _DISCOVERED
    found = []
    try:
        for m in client.models.list():
            match = _FLASH_RE.match(m.name)
            if match:
                found.append((match.group(2) is None, float(match.group(1)), m.name.removeprefix("models/")))
    except Exception:  # noqa: BLE001
        return []
    _DISCOVERED = [name for *_, name in sorted(found, reverse=True)]
    return _DISCOVERED


def _models(client=None) -> list[str]:
    custom = _secret("GEMINI_MODEL")
    names = [custom] if custom else []
    if client is not None:
        names += _discover_flash(client)
    names += DEFAULT_MODELS
    return list(dict.fromkeys(n for n in names if n))


def _client():
    key = _secret("GEMINI_API_KEY")
    if not key:
        raise AIError("ЖИ кілті бапталмаған. Әкімші GEMINI_API_KEY кілтін Secrets бөліміне қосуы керек.")
    from google import genai
    from google.genai import types
    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=REQUEST_SECONDS * 1000))


def _parse_json(text: str):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def _generate_json(contents: list, system: str, temperature: float = 0.1) -> dict:
    from google.genai import errors, types

    client = _client()
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json",
    )
    global _WORKING_MODEL
    last_error = None
    busy = quota = False
    deadline = time.monotonic() + TOTAL_SECONDS
    models = list(dict.fromkeys(([_WORKING_MODEL] if _WORKING_MODEL else []) + _models(client)))
    skip: set[str] = set()      # бұл сұрауда енді сыналмайтын модельдер (жоқ, лимиті біткен, ұзақ күттірген)
    bad_json = 0
    for pause in ROUND_PAUSES:
        if pause and time.monotonic() + pause < deadline:
            time.sleep(pause)
        for model in models:
            if model in skip:
                continue
            if time.monotonic() >= deadline:
                break
            try:
                resp = client.models.generate_content(model=model, contents=contents, config=config)
                data = _parse_json(resp.text)
                _WORKING_MODEL = model
                return data
            except errors.APIError as exc:
                last_error = exc
                if exc.code in (401, 403):
                    raise AIError("ЖИ кілті жарамсыз немесе бұл аймақта қолжетімсіз.") from exc
                if exc.code == 404:
                    skip.add(model)
                elif exc.code == 429:
                    quota = True
                    if "PerDay" in str(exc):    # күндік лимит; минуттық лимитті келесі айналымда қайталаймыз
                        skip.add(model)
                elif exc.code >= 500:
                    busy = True
                    if exc.code == 504:
                        skip.add(model)
                else:
                    raise AIError(f"ЖИ қызметі қате қайтарды ({exc.code}). Қайталап көріңіз.") from exc
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                bad_json += 1
                if bad_json >= 3:
                    raise AIError("ЖИ жауабын оқу мүмкін болмады. Қайталап көріңіз.") from exc
            except Exception as exc:  # noqa: BLE001 — желі қатесі, уақыт шегі т.б.
                last_error = exc
                busy = True
                skip.add(model)
        if time.monotonic() >= deadline or all(m in skip for m in models):
            break
    if busy:
        raise AIError("Google ЖИ серверлері қазір қатты жүктелген. 1–2 минуттан кейін қайталап көріңіз.")
    if quota:
        raise AIError("ЖИ-дің тегін сұраныс лимиті таусылды. Бірнеше минуттан кейін қайталап көріңіз, болмаса ертең.")
    if bad_json:
        raise AIError("ЖИ жауабын оқу мүмкін болмады. Қайталап көріңіз.")
    raise AIError(f"Қолжетімді ЖИ моделі табылмады: {last_error}")


# --------------------------------------------------------------------------- #
# Суреттерді дайындау
# --------------------------------------------------------------------------- #
def prepare_image(data: bytes, max_side: int = 2000) -> bytes:
    """Телефон суретін бұрады (EXIF), кішірейтеді, JPEG-ке айналдырады.

    Метадеректер (геолокация, құрылғы т.б.) осы кезде жойылады.
    """
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=88)
    return out.getvalue()


# --------------------------------------------------------------------------- #
# 1. Оқушы жұмысын тексеру
# --------------------------------------------------------------------------- #
CHECK_SYSTEM = """You are "Qadam", an assistant that helps a mathematics teacher in Kazakhstan check
students' handwritten summative assessment work (БЖБ / ТЖБ). The teacher always makes the final decision.

Rules:
1. TRANSCRIBE first. Read the photo(s) and write down exactly what the student wrote for each task,
   step by step, WITHOUT correcting anything. Use plain notation: fractions as a/b, mixed numbers as "2 1/3".
2. If a part of the work is unreadable, say so in the transcription with "[оқылмайды]" and lower confidence.
   Never invent what the student "probably" wrote.
3. Check each step against the task and the reference solution. Any mathematically valid method is acceptable,
   not only the reference one.
4. Grade STRICTLY by descriptors. A descriptor is met only if there is visible evidence in the student's work.
   Points for a descriptor are an integer from 0 to its max_points.
5. For each mistake give: the step number where it first appears, an error code from the taxonomy below,
   and a short explanation. Use only codes from the taxonomy. Do not report an error that does not exist.
6. Confidence: "high" — handwriting clear and the judgement is unambiguous; "medium" — some doubt;
   "low" — handwriting hard to read or judgement uncertain. Be honest; low confidence sends the item to the teacher.
7. Feedback to the student: 1–2 supportive sentences in Kazakh that name exactly where the mistake is and what
   rule to recall. Do not just give the correct answer.
8. ALL human-readable text fields must be in Kazakh. Return ONLY JSON.

Error taxonomy:
{taxonomy}

JSON format:
{{
  "readable": true,
  "tasks": [
    {{
      "task_id": "1",
      "transcription": "what the student wrote",
      "steps": [{{"n": 1, "text": "step as written", "correct": true, "comment": "short note"}}],
      "descriptors": [{{"id": "1.1", "points": 1, "evidence": "where in the work this is visible", "confidence": "high"}}],
      "errors": [{{"code": "E1", "step": 2, "explanation": "..."}}],
      "student_feedback": "..."
    }}
  ],
  "general_comment": "1-2 sentences for the teacher"
}}
"""


def _bjb_for_prompt(spec: dict) -> str:
    clean = {
        "title": spec["title"],
        "grade": spec.get("grade"),
        "tasks": [
            {
                "id": t["id"],
                "condition": t["condition"],
                "reference_answer": t.get("reference_answer", ""),
                "reference_solution": t.get("reference_solution", ""),
                "descriptors": [{"id": d["id"], "text": d["text"], "max_points": d["max_points"]} for d in t["descriptors"]],
            }
            for t in spec["tasks"]
        ],
    }
    return json.dumps(clean, ensure_ascii=False, indent=1)


def check_work(spec: dict, images: list[bytes]) -> tuple[dict, float]:
    """Оқушы жұмысын тексереді. (қалыпқа келтірілген нәтиже, ЖИ уақыты сек) қайтарады."""
    from google.genai import types

    if not images:
        raise AIError("Кемінде бір сурет жүктеңіз.")
    parts = [types.Part.from_bytes(data=prepare_image(img), mime_type="image/jpeg") for img in images]
    parts.append(
        "Summative assessment specification (tasks, reference answers, descriptors):\n"
        + _bjb_for_prompt(spec)
        + f"\n\nThe photo(s) above contain one student's work ({len(images)} page(s)). Check it."
    )
    started = time.perf_counter()
    raw = _generate_json(parts, CHECK_SYSTEM.format(taxonomy=taxonomy_for_prompt()))
    elapsed = time.perf_counter() - started
    return normalize_check(raw, spec), elapsed


def normalize_check(raw: dict, spec: dict) -> dict:
    """ЖИ жауабын тексереді: жоқ дескрипторларды толтырады, ұпайды шектейді,
    белгісіз қате кодтарын E99-ға ауыстырады. ЖИ қате пішім қайтарса да
    интерфейс бұзылмайды."""
    raw = raw if isinstance(raw, dict) else {}
    by_task = {}
    for item in raw.get("tasks") or []:
        if isinstance(item, dict):
            by_task[str(item.get("task_id", "")).strip()] = item

    tasks = []
    for t in spec["tasks"]:
        src = by_task.get(str(t["id"]), {})
        src_desc = {}
        for d in src.get("descriptors") or []:
            if isinstance(d, dict):
                src_desc[str(d.get("id", "")).strip()] = d
        descriptors = []
        for d in t["descriptors"]:
            s = src_desc.get(d["id"])
            if s is None:
                descriptors.append({"id": d["id"], "text": d["text"], "max_points": d["max_points"],
                                    "points": 0, "evidence": "ЖИ бағаламады — мұғалім тексерсін", "confidence": "low"})
                continue
            try:
                pts = int(round(float(s.get("points", 0))))
            except (TypeError, ValueError):
                pts = 0
            conf = s.get("confidence") if s.get("confidence") in CONFIDENCE else "low"
            descriptors.append({"id": d["id"], "text": d["text"], "max_points": d["max_points"],
                                "points": max(0, min(pts, d["max_points"])),
                                "evidence": str(s.get("evidence", "")), "confidence": conf})
        errors = []
        for e in src.get("errors") or []:
            if not isinstance(e, dict):
                continue
            code = str(e.get("code", "")).strip().upper()
            errors.append({"code": code if code in ERROR_TYPES else "E99",
                           "step": e.get("step"), "explanation": str(e.get("explanation", ""))})
        steps = []
        for s in src.get("steps") or []:
            if isinstance(s, dict):
                steps.append({"n": s.get("n"), "text": str(s.get("text", "")),
                              "correct": bool(s.get("correct", True)), "comment": str(s.get("comment", ""))})
        tasks.append({
            "task_id": t["id"],
            "condition": t["condition"],
            "transcription": str(src.get("transcription", "")) or "[ЖИ бұл тапсырманы таппады]",
            "steps": steps,
            "descriptors": descriptors,
            "errors": errors,
            "student_feedback": str(src.get("student_feedback", "")),
        })
    return {
        "readable": bool(raw.get("readable", True)),
        "tasks": tasks,
        "general_comment": str(raw.get("general_comment", "")),
    }


# --------------------------------------------------------------------------- #
# 2. Қатеге сәйкес жаттығулар
# --------------------------------------------------------------------------- #
PRACTICE_SYSTEM = """You create short practice exercises in Kazakh for a student who made specific mistakes
in a mathematics task. Exercises must target exactly those mistakes, be at the same grade level,
and be similar to (but not the same as) the original task.

For EVERY exercise also give "check_expression": a pure arithmetic expression using only integers,
decimals with a dot, + - * / and parentheses, whose value equals the correct answer
(mixed numbers written as (2+1/3)). Give "answer" as text for the student and "answer_value" as a single
number in the form a/b, an integer, or a decimal. Return ONLY JSON:
{"exercises": [{"problem": "...", "answer": "...", "answer_value": "7/12", "check_expression": "5/6-1/4", "hint": "short hint"}]}
"""


def generate_practice(task: dict, errors: list[dict], n: int = 3) -> list[dict]:
    """Жаттығуларды құрастырады және әрқайсысының жауабын Python-мен тексереді."""
    err_text = "\n".join(
        f"- {e['code']} ({ERROR_TYPES.get(e['code'], ('',))[0]}): {e.get('explanation', '')}" for e in errors
    ) or "- (no specific errors; give consolidation exercises)"
    prompt = (f"Original task: {task['condition']}\nStudent's mistakes:\n{err_text}\n"
              f"Create {n + 1} exercises.")
    raw = _generate_json([prompt], PRACTICE_SYSTEM, temperature=0.6)
    verified = []
    for ex in (raw.get("exercises") or []) if isinstance(raw, dict) else []:
        if not isinstance(ex, dict):
            continue
        ok = verify.check(str(ex.get("check_expression", "")), str(ex.get("answer_value", "")))
        if ok:
            verified.append({"problem": str(ex.get("problem", "")), "answer": str(ex.get("answer", "")),
                             "hint": str(ex.get("hint", ""))})
        if len(verified) == n:
            break
    return verified


# --------------------------------------------------------------------------- #
# 3. Сынып бойынша талдау мәтіні
# --------------------------------------------------------------------------- #
ANALYSIS_SYSTEM = """You are a methodologist helping a mathematics teacher in Kazakhstan write the analysis
of summative assessment (БЖБ талдауы) for the school's methodical association. You receive ONLY aggregated,
anonymous statistics. Write in Kazakh, in an official but clear style. Do not invent numbers: use only the
numbers given. Return ONLY JSON:
{"summary": "2-3 sentences", "difficulties": ["..."], "causes": ["..."], "correction_plan": ["concrete actions"]}
"""


def class_analysis(stats: dict) -> dict:
    raw = _generate_json([json.dumps(stats, ensure_ascii=False)], ANALYSIS_SYSTEM, temperature=0.3)
    if not isinstance(raw, dict):
        raise AIError("ЖИ талдау мәтінін құрастыра алмады.")
    return {
        "summary": str(raw.get("summary", "")),
        "difficulties": [str(x) for x in raw.get("difficulties") or []],
        "causes": [str(x) for x in raw.get("causes") or []],
        "correction_plan": [str(x) for x in raw.get("correction_plan") or []],
    }
