import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest
from core import ai, bjb

def _fake(spec):
    raw = {"readable": True, "general_comment": "ok", "tasks": [{"task_id": t["id"], "transcription": "x",
           "steps": [{"n": 1, "text": "a", "correct": False, "comment": "c"}],
           "descriptors": [{"id": d["id"], "points": 1, "confidence": "low", "evidence": "e"} for d in t["descriptors"]],
           "errors": [{"code": "E2", "step": 1, "explanation": "z"}], "student_feedback": "fb"} for t in spec["tasks"]]}
    return ai.normalize_check(raw, spec)

def run(at):
    at.run(timeout=30)
    assert not at.exception, [e.value for e in at.exception]
    return at

def test_flow():
    ai.is_configured = lambda: True
    ai.class_analysis = lambda s: {"summary": "S", "difficulties": ["d"], "causes": ["c"], "correction_plan": ["p"]}
    at = run(AppTest.from_file(str(ROOT / "app.py"), default_timeout=30))
    # validation: name instead of code
    at.text_input[0].input("Айгерім"); at.checkbox[0].check(); at.button[0].click(); run(at)
    assert any("аты-жөнін" in w.value for w in at.warning)
    spec = bjb.load_builtin()["5_jai_bolshekter"]
    from PIL import Image; import io
    buf = io.BytesIO(); Image.new("RGB", (50, 50), "white").save(buf, "PNG")
    at.session_state["pending"] = {"id": "t1", "student_code": "5А-1", "bjb_id": spec["id"], "images": [buf.getvalue()],
                                   "result": _fake(spec), "ai_seconds": 10.0, "shown_at": time.time() - 30, "practice": {}}
    run(at)
    assert any("сенімсіз" in w.value for w in at.warning)
    assert len(at.multiselect) == 3
    confirm = [b for b in at.button if "Растау" in b.label][0]
    confirm.click(); run(at)
    res = at.session_state["results"]
    assert len(res) == 1 and res[0]["total"] == 10 and res[0]["review_seconds"] >= 30
    for page in ["views/results.py", "views/efficiency.py", "views/bjb_editor.py", "views/about.py"]:
        at.switch_page(page); run(at)
    at.switch_page("views/results.py"); run(at)
    [b for b in at.button if "Талдау" in b.label][0].click(); run(at)
    assert any("S" in m.value for m in at.markdown)
