import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import ai, bjb, importer

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"')


def make_docx(body, head=""):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"{head}<w:document {NS}><w:body>{body}</w:body></w:document>")
    return buf.getvalue()


FRAC = "<m:oMath><m:f><m:num><m:r><m:t>1</m:t></m:r></m:num><m:den><m:r><m:t>3</m:t></m:r></m:den></m:f></m:oMath>"
RAW = {"variants": [
    {"title": "БЖБ", "grade": "5", "warnings": [], "tasks": [
        {"id": "1", "condition": "1/2+1/3", "answer": "5/6", "solution": "s", "declared_points": 2,
         "descriptors": [{"id": "1.1", "text": "a", "points": 1}, {"id": "1.1", "text": "b", "points": 99}]},
        {"id": "2", "condition": "x", "answer": "", "declared_points": None, "descriptors": []}]},
    {"title": "БЖБ", "tasks": [{"id": "1", "condition": "y", "answer": "1",
                                "descriptors": [{"text": "d", "points": "bad", "proposed": True}]}]},
    "junk"]}


def test_docx_text_fractions_and_tables():
    body = (f"<w:p><w:r><w:t>2</w:t></w:r>{FRAC}</w:p>"
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc></w:tr></w:tbl>")
    assert importer.docx_to_text(make_docx(body)) == "2 1/3\nA | B"


def test_bad_files():
    for name, data in (("a.docx", b"nope"), ("a.pdf", b"nope"), ("a.doc", b"x"),
                       ("a.docx", make_docx("")), ("a.docx", make_docx("", "<!DOCTYPE x>"))):
        with pytest.raises(importer.ImportFileError):
            importer.extract(name, data)


def test_normalize():
    v = importer.normalize(RAW)
    assert [x["title"] for x in v] == ["БЖБ (1-нұсқа)", "БЖБ (2-нұсқа)"]
    assert list(v[0]["table"]["Дескриптор №"]) == ["1.1", "1.1-2", "2.1"]
    assert list(v[0]["table"]["Ұпай"]) == [1, 10, 1]
    text = " ".join(v[0]["warnings"])
    assert "2 балл" in text and "дескриптор табылмады" in text and "жауабы" in text
    assert "ЖИ ұсынды" in " ".join(v[1]["warnings"])
    with pytest.raises(importer.ImportFileError):
        importer.normalize({"variants": []})


def test_table_with_blank_row_and_long_titles():
    table = importer.normalize(RAW)[1]["table"]
    table = pd.concat([table, pd.DataFrame([{c: None for c in bjb.TABLE_COLUMNS}])], ignore_index=True)
    long = "Ұ" * 80
    a, b = bjb.from_table(long + " 1", "5", table), bjb.from_table(long + " 2", "5", table)
    assert a["id"] != b["id"] and bjb.max_total(a) == 1


def test_ui(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(ai, "is_configured", lambda: True)
    seen = {}
    good = {"variants": [{"title": f"БЖБ, {n}-нұсқа", "grade": "5", "tasks": [
        {"id": "1", "condition": f"c{n}", "answer": "1", "solution": "sol", "declared_points": 1,
         "descriptors": [{"id": "1.1", "text": "d", "points": 1}]}]} for n in (1, 2)]}

    def fake(contents, system, temperature=0.1):
        seen["contents"] = contents
        return good
    monkeypatch.setattr(ai, "_generate_json", fake)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.switch_page("views/bjb_editor.py").run()
    up = [u for u in at.get("file_uploader") if u.label == "БЖБ файлы"][0]
    up.set_value(("t.docx", make_docx("<w:p><w:r><w:t>тапсырма</w:t></w:r></w:p>"),
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document")).run()
    [b for b in at.button if "Файлды оқу" in b.label][0].click().run()
    assert not at.exception and "тапсырма" in seen["contents"][0]
    assert len(at.radio) == 1
    [b for b in at.button if "Тексердім" in b.label][0].click().run()
    assert not at.exception
    assert any("сақталды" in s.value for s in at.success)
    spec = at.session_state["bjbs"][at.session_state["current_bjb"]]
    assert spec["title"] == "БЖБ, 1-нұсқа" and spec["tasks"][0]["reference_solution"] == "sol"
    assert "1-нұсқа" in at.sidebar.selectbox[0].value


def para(t):
    return f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>"


def tbl(rows):
    return "<w:tbl>" + "".join("<w:tr>" + "".join(f"<w:tc>{para(c)}</w:tc>" for c in r) + "</w:tr>" for r in rows) + "</w:tbl>"


def student_sheet(n):
    return (para("БӨЛІМ БОЙЫНША ЖИЫНТЫҚ БАҒАЛАУ") + para(f"Математика | 5-сынып | {n}-нұсқа") + para("Бөлім: Бөлшек")
            + para("1-тапсырма. Есепте. (2 балл)") + para(f"а) {n}/5 + 1/5 = ____") + para("Сәттілік!"))


TEACHER = para("МҰҒАЛІМГЕ АРНАЛҒАН БАҒАЛАУ ПАРАҒЫ")


def test_parse_single_variant_without_ai():
    doc = make_docx(student_sheet(1) + TEACHER
                    + tbl([["Тапсырма", "Дұрыс жауап"], ["1а", "2/5"], ["1ә", "9"]])
                    + tbl([["№", "Дескриптор", "Балл"], ["1", "қосады", "1"]]))
    v, = importer.extract_without_ai("a.docx", doc)
    assert v["title"] == "БЖБ: Бөлшек, 1-нұсқа" and v["grade"] == "5"
    row = v["table"].iloc[0]
    assert row["Дұрыс жауап"] == "а) 2/5" and row["Тапсырма шарты"] == "Есепте. а) 1/5 + 1/5"
    text = " ".join(v["warnings"])
    assert "1ә" in text and "2 балл" in text


def test_parse_two_variants_without_ai():
    doc = make_docx(student_sheet(1) + student_sheet(2) + TEACHER
                    + tbl([["Тапсырма", "№", "Дескриптор. Білім алушы", "1-нұсқа", "2-нұсқа", "Балл"],
                           ["1", "1.1", "қосады", "2/5", "3/5", "1"], ["", "1.2", "жазады", "x", "y", "1"],
                           ["Барлығы", "", "", "", "", "2"]])
                    + para("Үлгі шешімдер") + para("1-нұсқа") + para("1) бір") + para("2-нұсқа") + para("1) екі"))
    a, b = importer.extract_without_ai("a.docx", doc)
    assert b["table"].iloc[0]["Дұрыс жауап"] == "1.1: 3/5; 1.2: y"
    assert (a["table"].iloc[0]["Үлгі шешім"], b["table"].iloc[0]["Үлгі шешім"]) == ("бір", "екі")
    assert not a["warnings"] and len(b["table"]) == 2


def test_unknown_layout_needs_ai():
    assert importer.extract_without_ai("a.docx", make_docx(para("Кез келген мәтін"))) is None
    assert importer.extract_without_ai("a.docx", make_docx(student_sheet(1) + TEACHER)) is None
    assert importer.extract_without_ai("a.pdf", b"%PDF") is None
