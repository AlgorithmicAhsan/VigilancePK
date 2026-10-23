"""The chatbot's article store: Neon Postgres + pgvector, Gemini embeddings (ADR-033).

Replaces the local ChromaDB collection and the local MiniLM model: no model
to load at startup, no disk that a free host wipes, and cosine distance named
in every query.
"""
import uuid
from contextlib import contextmanager

from src import db, llm

ARTICLE_COLUMNS = ("id, link, source, language, title, summary, published_at, "
                   "categories, tags, severity, reasoning")


def article_id(link: str) -> uuid.UUID:
    """Same link, same id, every time: this is how a story is recognised as seen."""
    return uuid.uuid5(uuid.NAMESPACE_URL, link or "")


def vector_literal(values) -> str:
    """pgvector's text form, '[0.1,0.2,...]', so no extra driver package is needed."""
    return "[" + ",".join(f"{float(v):.7g}" for v in values) + "]"


def document_text(article: dict) -> str:
    """What gets embedded: the headline carries most of the meaning."""
    return f"{article.get('title', '')}\n\n{article.get('summary', '')}".strip()


@contextmanager
def _using(conn=None):
    """The caller's open connection if given, else one from the pool. Reusing
    one connection matters: opening one to Neon costs ~1-2 s from here."""
    if conn is not None:
        yield conn
    else:
        with db.connection() as fresh:
            yield fresh


class Vault:
    def existing_ids(self, ids, conn=None) -> set:
        """Which of these ids are already stored. Asks only about the given
        ids instead of loading every id in the table. Pass an open
        connection to skip opening a new one (a fresh one to Neon costs
        seconds)."""
        ids = list(ids)
        if not ids:
            return set()
        if conn is not None:
            return {r["id"] for r in conn.execute("SELECT id FROM articles WHERE id = ANY(%s)", (ids,)).fetchall()}
        with db.connection() as conn:
            return self.existing_ids(ids, conn)

    def ingest(self, articles: list[dict], classified_by: str, log=print) -> int:
        """Store, then embed. Returns how many were stored."""
        stored = self.store(articles, classified_by)
        self.embed_missing(log)
        return stored

    def store(self, articles: list[dict], classified_by: str, conn=None) -> int:
        """Saves classified stories in one batch, without embeddings yet
        (ADR-036). They appear in the feed straight away, and a failure in
        the slower embedding step can never lose classification work."""
        if not articles:
            return 0
        rows = []
        for art in articles:
            jc = art.get("jurist_classification", {})
            rows.append({
                "id": article_id(art.get("link", "")),
                "link": art.get("link", ""),
                "source": art.get("source", "Unknown"),
                "language": art.get("language", "english"),
                "title": art.get("title", ""),
                "summary": art.get("summary", ""),
                "published_at": art.get("published") or None,
                "categories": jc.get("major_categories", []),
                "tags": jc.get("specific_tags", []),
                "severity": art["severity"],
                "reasoning": jc.get("reasoning", ""),
                "classified_by": art.get("classified_by", classified_by),
            })
        # Its own transaction, committed on the spot even on a shared
        # connection, so the feed shows the stories right away.
        with _using(conn) as c, c.transaction(), c.cursor() as cur:
            # A re-classified story keeps its embedding: the text it was made
            # from hasn't changed.
            cur.executemany("""
                INSERT INTO articles (id, link, source, language, title, summary, published_at,
                                      categories, tags, severity, reasoning, classified_by)
                VALUES (%(id)s, %(link)s, %(source)s, %(language)s, %(title)s, %(summary)s, %(published_at)s,
                        %(categories)s, %(tags)s, %(severity)s, %(reasoning)s, %(classified_by)s)
                ON CONFLICT (id) DO UPDATE SET
                    categories = EXCLUDED.categories, tags = EXCLUDED.tags, severity = EXCLUDED.severity,
                    reasoning = EXCLUDED.reasoning, classified_by = EXCLUDED.classified_by
            """, rows)
        return len(rows)

    def embed_missing(self, log=print, conn=None) -> int:
        """Embeds every stored story that has no embedding yet, 100 per
        request, saving each chunk as it goes. Includes leftovers from an
        earlier sync that hit a limit. Returns how many were embedded."""
        done = 0
        with _using(conn) as c:
            while True:
                rows = c.execute("SELECT id, title, summary FROM articles WHERE embedding IS NULL "
                                 "ORDER BY fetched_at LIMIT %s", (llm.EMBED_BATCH,)).fetchall()
                if not rows:
                    return done
                vectors = llm.embed([document_text(r) for r in rows], "RETRIEVAL_DOCUMENT")
                with c.transaction(), c.cursor() as cur:
                    cur.executemany("UPDATE articles SET embedding = %s::vector WHERE id = %s",
                                    [(vector_literal(v), r["id"]) for r, v in zip(rows, vectors)])
                done += len(rows)
                log(f"[embed] {done} embedded")

    def pending_embeddings(self) -> int:
        with db.connection() as conn:
            return conn.execute("SELECT count(*) AS n FROM articles WHERE embedding IS NULL").fetchone()["n"]

    def latest(self, limit: int = 40) -> list[dict]:
        """Newest first; undated stories sort last (ADR-015)."""
        with db.connection() as conn:
            return conn.execute(f"SELECT {ARTICLE_COLUMNS} FROM articles "
                                "ORDER BY published_at DESC NULLS LAST LIMIT %s", (limit,)).fetchall()

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """The top_k stories closest in meaning to the question, with their
        cosine distance (0 = same meaning, 2 = opposite)."""
        vector = vector_literal(llm.embed([query], "RETRIEVAL_QUERY")[0])
        with db.connection() as conn:
            return conn.execute(f"""
                WITH q AS (SELECT %s::vector AS v)
                SELECT {ARTICLE_COLUMNS}, embedding <=> q.v AS distance
                FROM articles, q WHERE embedding IS NOT NULL   -- not yet embedded = not yet searchable
                ORDER BY embedding <=> q.v LIMIT %s
            """, (vector, top_k)).fetchall()

    def count(self) -> int:
        with db.connection() as conn:
            return conn.execute("SELECT count(*) AS n FROM articles").fetchone()["n"]

    def reset(self) -> None:
        with db.connection() as conn:
            conn.execute("TRUNCATE articles")
