import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import verify, bjb, stats, ai
from core.privacy import validate_student_code

def test_verify():
    assert verify.check("5/6-1/4", "7/12")
    assert verify.check("(2+1/3)+(1+3/4)", "4 1/12")
    assert verify.check("2,5*8/5", "4")
    assert verify.check("0.6/1.5", "2/5")
    assert not verify.check("5/6-1/4", "1/2")
    assert not verify.check("__import__('os')", "1")
    assert not verify.check("1/0", "1")

def test_privacy():
    assert validate_student_code("5А-12")[0]
    assert validate_student_code("11-3")[0]
    assert not validate_student_code("Айгерім Н.")[0]
    assert not validate_student_code("")[0]

def test_builtin_and_normalize():
    specs = bjb.load_builtin()
    assert set(specs) == {"5_jai_bolshekter", "6_proportsiya"}
    spec = specs["5_jai_bolshekter"]
    assert bjb.max_total(spec) == 10
    raw = {"tasks": [{"task_id": "1", "descriptors": [{"id": "1.1", "points": 5, "confidence": "high"},
                                                      {"id": "1.3", "points": 1, "confidence": "weird"}],
                      "errors": [{"code": "E1", "step": 1}, {"code": "ZZ"}]}]}
    n = ai.normalize_check(raw, spec)
    d = {x["id"]: x for t in n["tasks"] for x in t["descriptors"]}
    assert d["1.1"]["points"] == 1            # clamped
    assert d["1.3"]["confidence"] == "low"    # invalid -> low
    assert d["2.1"]["confidence"] == "low" and d["2.1"]["points"] == 0  # missing
    assert [e["code"] for e in n["tasks"][0]["errors"]] == ["E1", "E99"]
    assert len(n["tasks"]) == 3

def test_table_roundtrip():
    spec = bjb.load_builtin()["6_proportsiya"]
    again = bjb.from_table("Тест", "6", bjb.to_table(spec))
    assert bjb.max_total(again) == bjb.max_total(spec)

def test_stats():
    spec = bjb.load_builtin()["5_jai_bolshekter"]
    raw = {"tasks": [{"task_id": t["id"], "descriptors": [{"id": d["id"], "points": 1, "confidence": "high"} for d in t["descriptors"]],
                      "errors": []} for t in spec["tasks"]]}
    res = ai.normalize_check(raw, spec)
    r1 = stats.build_record(record_id="a", student_code="5А-1", spec=spec, ai_result=res, teacher_points={"1.2": 0},
                            teacher_errors={"1": ["E3"]}, feedback={}, ai_seconds=12, review_seconds=60, checked_at="x")
    assert r1["total"] == 9 and r1["ai_total"] == 10
    ag = stats.agreement([r1])
    assert ag["corrections"] == 1 and ag["descriptor_agree_pct"] == 90.0
    assert stats.error_table([r1]).iloc[0]["Код"] == "E3"
    assert "students" in stats.aggregated_for_ai([r1], spec)
    assert len(stats.to_excel([r1], {"summary": "s", "difficulties": ["d"], "causes": [], "correction_plan": []})) > 1000
