import json

import pytest

from src import jurist as jurist_module
from src.jurist import GENERAL, Jurist, build_prompt, parse_batch


def _articles(n):
    return [{"title": f"Title {i}", "summary": f"Summary {i}"} for i in range(n)]


def _item(idx, cats=("Health",), tags=(), severity="low", reasoning=""):
    return {"id": idx, "major_categories": list(cats), "specific_tags": list(tags),
            "severity": severity, "reasoning": reasoning}


def _reply(*items):
    return json.dumps(list(items))


def test_build_prompt_lists_every_article_with_its_id():
    prompt = build_prompt(_articles(3))
    for i in range(3):
        assert f"[id={i}]" in prompt and f"Title {i}" in prompt


def test_build_prompt_caps_long_summaries():
    long = [{"title": "t", "summary": "x" * 5000}]
    assert "x" * (jurist_module.SUMMARY_CHARS + 1) not in build_prompt(long)


def test_parse_batch_keeps_valid_labels():
    raw = _reply(_item(0, ["Law Enforcement"], ["Police", "Custodial torture"], "high", "Police torture in custody."))
    result = parse_batch(raw, 1)[0]
    assert result["major_categories"] == ["Law Enforcement"]
    assert result["specific_tags"] == ["Police", "Custodial torture"]
    assert result["severity"] == "high"


def test_parse_batch_drops_invented_names():
    raw = _reply(_item(0, ["Human Rights", "Civil Rights"], ["Made up tag", "Digital Rights"]))
    result = parse_batch(raw, 1)[0]
    assert result["major_categories"] == ["Civil Rights"]
    assert result["specific_tags"] == ["Digital Rights"]


def test_parse_batch_recovers_category_from_tags():
    assert parse_batch(_reply(_item(0, ["Wrong"], ["Polio"])), 1)[0]["major_categories"] == ["Health"]


def test_parse_batch_falls_back_to_general():
    assert parse_batch(_reply(_item(0, [], [])), 1)[0]["major_categories"] == [GENERAL]


@pytest.mark.parametrize("level", ["critical", "high", "medium", "low", "CRITICAL"])
def test_parse_batch_accepts_every_severity_level(level):
    assert parse_batch(_reply(_item(0, severity=level)), 1)[0]["severity"] == level.lower()


@pytest.mark.parametrize("bad", ["severe", "", None, 3])
def test_parse_batch_never_guesses_a_severity(bad):
    # An unrated article is a failure (retried next sync), never a default.
    assert parse_batch(_reply(_item(0, severity=bad)), 1) == {}


def test_parse_batch_ignores_bad_and_duplicate_ids():
    raw = _reply(
        _item(0, reasoning="first"),
        _item(0, ["Economy"], reasoning="dupe"),
        _item(7, reasoning="out of range"),
        _item("1", reasoning="string id"),
    )
    result = parse_batch(raw, 2)
    assert list(result) == [0]
    assert result[0]["reasoning"] == "first"


def test_parse_batch_strips_markdown_fence():
    raw = "```json\n" + _reply(_item(0)) + "\n```"
    assert 0 in parse_batch(raw, 1)


def test_parse_batch_rejects_non_list():
    with pytest.raises(ValueError):
        parse_batch('{"id": 0}', 1)


def test_severity_rubric_is_sent_to_the_model():
    for rule in ("critical", "Accidents", "TIMING", "SCOPE"):
        assert rule in jurist_module.SYSTEM_INSTRUCTION


def test_classify_batch_splits_successes_and_missing(monkeypatch):
    # Model answers for article 0 only; article 1 must come back as a failure.
    reply = _reply(_item(0, ["Crimes & Violations"], ["Extrajudicial killing"], "critical", "Two killed."))
    monkeypatch.setattr(jurist_module.llm, "generate_json", lambda *a, **k: reply)

    classified, failed = Jurist(model="test").classify_batch(_articles(2))

    assert [a["title"] for a in classified] == ["Title 0"]
    assert classified[0]["category"] == "Crimes & Violations"
    assert classified[0]["tags"] == "Extrajudicial killing"
    assert classified[0]["severity"] == "critical"
    assert [a["title"] for a in failed] == ["Title 1"]
    assert "classification_error" in failed[0]


def test_classify_batch_marks_whole_batch_failed_on_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("429 quota exceeded")
    monkeypatch.setattr(jurist_module.llm, "generate_json", boom)

    classified, failed = Jurist(model="test").classify_batch(_articles(3))

    assert classified == []
    assert len(failed) == 3
    assert all("429" in a["classification_error"] for a in failed)


def test_classify_all_sends_one_request_per_batch(monkeypatch):
    calls = []

    def fake(prompt, *a, **k):
        calls.append(prompt)
        return _reply(*(_item(i) for i in range(prompt.count("[id="))))

    monkeypatch.setattr(jurist_module.llm, "generate_json", fake)

    classified, failed = Jurist(model="test", batch_size=20).classify_all(_articles(45))

    assert len(calls) == 3  # 20 + 20 + 5
    assert len(classified) == 45 and failed == []


def test_concurrent_batches_keep_input_order(monkeypatch):
    import time

    def slow_first(prompt, *a, **k):
        if "Title 0" in prompt:
            time.sleep(0.05)  # first batch finishes last
        return _reply(*(_item(i) for i in range(prompt.count("[id="))))

    monkeypatch.setattr(jurist_module.llm, "generate_json", slow_first)
    classified, _ = Jurist(model="test", batch_size=2).classify_all(_articles(6), concurrency=3)
    assert [a["title"] for a in classified] == [f"Title {i}" for i in range(6)]
    assert all(a["classified_by"] == "test" for a in classified)
