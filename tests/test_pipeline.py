"""The sync's own logic with every outside service faked."""
from contextlib import contextmanager

import pytest

from src import pipeline
from src.vault import article_id


class FakeConn:
    def __init__(self, lock_free):
        self.lock_free = lock_free
        self.unlocked = False
        self.autocommit = False

    def execute(self, sql, params=None):
        conn = self

        class Result:
            def fetchone(self):
                return {"ok": conn.lock_free}
        if "unlock" in sql:
            conn.unlocked = True
        return Result()


@pytest.fixture
def fakes(monkeypatch):
    state = {"conn": FakeConn(lock_free=True), "classified_input": None, "stored": None}

    @contextmanager
    def connection():
        yield state["conn"]

    stories = [
        {"link": "https://x/1", "title": "one"},
        {"link": "https://x/2", "title": "two"},
        {"link": "https://x/1", "title": "one again, from another feed"},
        {"link": "https://x/3", "title": "three"},
    ]
    monkeypatch.setattr(pipeline.db, "connection", connection)
    monkeypatch.setattr(pipeline.NewsScraper, "scrape_all", lambda self: stories)
    monkeypatch.setattr(pipeline.Vault, "existing_ids", lambda self, ids, conn=None: {article_id("https://x/2")})

    def classify_all(self, articles):
        state["classified_input"] = [a["link"] for a in articles]
        return articles[:-1], articles[-1:]
    monkeypatch.setattr(pipeline.Jurist, "classify_all", classify_all)

    def store(self, articles, model, conn=None):
        state["stored"] = [a["link"] for a in articles]
        return len(articles)
    monkeypatch.setattr(pipeline.Vault, "store", store)
    monkeypatch.setattr(pipeline.Vault, "embed_missing", lambda self, log, conn=None: state["embed"]())
    state["embed"] = lambda: 1
    return state


def test_sync_skips_known_and_duplicate_stories(fakes):
    result = pipeline.run_sync(log=lambda *_: None)
    assert fakes["classified_input"] == ["https://x/1", "https://x/3"]  # x/2 known, x/1 once
    assert fakes["stored"] == ["https://x/1"]  # the failure is not stored
    assert result["fetched"] == 4 and result["new"] == 2 and result["failed"] == 1 and result["stored"] == 1
    assert result["embedded"] == 1
    assert fakes["conn"].autocommit is False  # returned to the pool as it came
    assert set(result["timings"]) == {"fetch_s", "check_s", "classify_s", "store_s", "embed_s", "total_s"}
    assert fakes["conn"].unlocked


def test_embedding_failure_does_not_fail_the_sync(fakes):
    def boom():
        raise RuntimeError("quota")
    fakes["embed"] = boom
    result = pipeline.run_sync(log=lambda *_: None)
    assert result["stored"] == 1 and result["embedded"] is None
    assert fakes["conn"].unlocked


def test_sync_refuses_to_overlap(fakes):
    fakes["conn"].lock_free = False
    with pytest.raises(pipeline.SyncBusy):
        pipeline.run_sync(log=lambda *_: None)
    assert fakes["classified_input"] is None
