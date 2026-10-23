import pytest

from src.vault import article_id, document_text, vector_literal


def test_vector_literal_is_pgvector_text_form():
    assert vector_literal([0.5, -1, 1e-9]) == "[0.5,-1,1e-09]"


def test_article_id_is_stable_per_link():
    assert article_id("https://dawn.com/a") == article_id("https://dawn.com/a")
    assert article_id("https://dawn.com/a") != article_id("https://dawn.com/b")


def test_document_text_joins_title_and_summary():
    assert document_text({"title": "Headline", "summary": "Body"}) == "Headline\n\nBody"
    assert document_text({"title": "Headline"}) == "Headline"


def _fake_db(monkeypatch, pending):
    """A tiny stand-in for Neon: `pending` rows have no embedding yet."""
    from contextlib import contextmanager

    from src import vault as vault_module
    log = {"inserted": [], "embedded": []}

    class Conn:
        def execute(self, sql, params=None):
            class Result:
                def fetchall(self_inner):
                    return [r for r in pending if r["id"] not in log["embedded"]][:params[0]]
            return Result()

        def cursor(self):
            return self

        def transaction(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def executemany(self, sql, rows):
            if sql.lstrip().startswith("UPDATE"):
                log["embedded"].extend(r[1] for r in rows)
            else:
                log["inserted"].extend(r["link"] for r in rows)

    @contextmanager
    def connection():
        yield Conn()
    monkeypatch.setattr(vault_module.db, "connection", connection)
    return log


def test_store_saves_everything_in_one_batch_without_embedding(monkeypatch):
    from src import llm, vault as vault_module
    log = _fake_db(monkeypatch, pending=[])
    monkeypatch.setattr(llm, "embed", lambda *a: pytest.fail("store must not embed"))
    articles = [{"link": f"https://x/{i}", "title": "t", "severity": "low"} for i in range(5)]
    assert vault_module.Vault().store(articles, "model") == 5
    assert log["inserted"] == [f"https://x/{i}" for i in range(5)]


def test_embed_missing_saves_each_chunk_so_a_failure_keeps_earlier_ones(monkeypatch):
    from src import llm, vault as vault_module
    pending = [{"id": i, "title": "t", "summary": "s"} for i in range(5)]
    log = _fake_db(monkeypatch, pending)
    calls = []

    def embed(texts, task):
        calls.append(len(texts))
        if len(calls) == 3:
            raise RuntimeError("rate limited")
        return [[0.0] * 3 for _ in texts]
    monkeypatch.setattr(llm, "embed", embed)
    monkeypatch.setattr(llm, "EMBED_BATCH", 2)

    with pytest.raises(RuntimeError):
        vault_module.Vault().embed_missing(log=lambda *_: None)
    assert calls == [2, 2, 1]
    assert log["embedded"] == [0, 1, 2, 3]  # the 5th waits for the next sync
