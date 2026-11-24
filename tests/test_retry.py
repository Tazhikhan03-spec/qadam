import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from google.genai import errors
from core import ai


def setup(monkeypatch, replies):
    calls = []

    def generate_content(model, contents, config):
        calls.append(model)
        r = replies(model, len(calls))
        if isinstance(r, int):
            raise errors.APIError(r, {"error": {"message": "x", "status": "X"}})
        return SimpleNamespace(text=r)
    monkeypatch.setattr(ai, "_client", lambda: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(ai, "_models", lambda c=None: ["a", "b"])
    monkeypatch.setattr(ai, "_WORKING_MODEL", None)
    monkeypatch.setattr(ai.time, "sleep", lambda s: None)
    return calls


def test_second_round_succeeds(monkeypatch):
    calls = setup(monkeypatch, lambda m, n: 503 if n < 4 else '{"ok": 1}')
    assert ai._generate_json(["x"], "s") == {"ok": 1}
    assert calls == ["a", "b", "a", "b"]


def test_404_not_retried_and_busy_message(monkeypatch):
    calls = setup(monkeypatch, lambda m, n: 404 if m == "a" else 503)
    with pytest.raises(ai.AIError, match="жүктелген"):
        ai._generate_json(["x"], "s")
    assert calls.count("a") == 1 and calls.count("b") == len(ai.ROUND_PAUSES)


def test_quota_and_bad_key(monkeypatch):
    setup(monkeypatch, lambda m, n: 429)
    with pytest.raises(ai.AIError, match="лимиті"):
        ai._generate_json(["x"], "s")
    setup(monkeypatch, lambda m, n: 403)
    with pytest.raises(ai.AIError, match="кілті"):
        ai._generate_json(["x"], "s")


def test_minute_quota_is_retried(monkeypatch):
    calls = setup(monkeypatch, lambda m, n: 429 if n < 3 else '{"ok": 1}')
    assert ai._generate_json(["x"], "s") == {"ok": 1}
    assert calls == ["a", "b", "a"]


def test_bad_json(monkeypatch):
    setup(monkeypatch, lambda m, n: "not json")
    with pytest.raises(ai.AIError, match="оқу мүмкін"):
        ai._generate_json(["x"], "s")


def test_light_model_is_flagged_and_not_sticky(monkeypatch):
    calls = setup(monkeypatch, lambda m, n: 503 if m == "a" else '{"ok": 1}')
    monkeypatch.setattr(ai, "_models", lambda c=None: ["a", "b-lite"])
    meta = {}
    ai._generate_json(["x"], "s", meta=meta)
    ai._generate_json(["x"], "s")
    assert meta["model"] == "b-lite" and calls == ["a", "b-lite", "a", "b-lite"]
    res = {"tasks": [{"descriptors": [{"confidence": "high"}]}]}
    assert ai.mark_light(res, "b-lite")["tasks"][0]["descriptors"][0]["confidence"] == "low"
    res = {"tasks": [{"descriptors": [{"confidence": "high"}]}]}
    assert ai.mark_light(res, "b")["tasks"][0]["descriptors"][0]["confidence"] == "high"
