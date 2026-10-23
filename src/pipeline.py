"""One sync run: Scout -> Jurist -> Vault (ADR-034).

Shared by the API's /sync (cron) and `python -m src.manage sync` (a person
watching the logs), so both run exactly the same steps.
"""
import time

from src import db
from src.jurist import Jurist
from src.scout import NewsScraper
from src.vault import Vault, article_id

# A Postgres advisory lock: one sync at a time across every process (the API
# server, a terminal, a cron job), not just within one server.
SYNC_LOCK_KEY = 4_2_0_2_6


class SyncBusy(RuntimeError):
    pass


def run_sync(wipe: bool = False, log=print) -> dict:
    """Runs one sync and returns counts plus seconds per stage."""
    vault = Vault()
    timings = {}
    started = time.perf_counter()

    def lap(name, since):
        timings[name] = round(time.perf_counter() - since, 1)
        log(f"[sync] {name.removesuffix('_s')} took {timings[name]} s")
        return time.perf_counter()

    with db.connection() as lock_conn:
        # One connection for the whole sync (ADR-036): every new connection to
        # Neon costs ~1-2 s from here. Autocommit, so each step's writes are
        # committed as they happen, not held until the sync ends.
        lock_conn.autocommit = True
        if not lock_conn.execute("SELECT pg_try_advisory_lock(%s) AS ok", (SYNC_LOCK_KEY,)).fetchone()["ok"]:
            raise SyncBusy("Another sync is already running.")
        try:
            t = time.perf_counter()
            if wipe:
                log("[sync] wiping stored articles")
                vault.reset()

            # 1. Every feed at once.
            raw_news = NewsScraper().scrape_all()
            t = lap("fetch_s", t)

            # 2. Only stories not stored yet. Failures are never stored, so they
            # come back here and are retried. A story in two feeds counts once.
            by_id = {}
            for art in raw_news:
                by_id.setdefault(article_id(art.get("link", "")), art)
            known = vault.existing_ids(by_id, conn=lock_conn)  # already open: no new connection
            new_articles = [art for aid, art in by_id.items() if aid not in known]
            log(f"[sync] {len(new_articles)} new stories, {len(raw_news) - len(new_articles)} already stored or duplicates")
            t = lap("check_s", t)

            # 3. Classify: batches of 20, three at a time.
            jurist = Jurist()
            classified, failed = jurist.classify_all(new_articles)
            t = lap("classify_s", t)

            # 4. Store in one batch: visible in the feed from here on (ADR-036).
            stored = vault.store(classified, jurist.model, conn=lock_conn)
            t = lap("store_s", t)

            # 5. Embed for search. The free tier allows ~100 texts a minute, so
            # this is the slow step. A limit or error here loses nothing: the
            # stories stay stored and the next sync embeds what's left.
            try:
                embedded = vault.embed_missing(log, conn=lock_conn)
            except Exception as e:
                embedded = None
                log(f"[sync] embedding stopped early ({e}); the next sync will finish it")
            lap("embed_s", t)
        finally:
            lock_conn.execute("SELECT pg_advisory_unlock(%s)", (SYNC_LOCK_KEY,))
            lock_conn.autocommit = False  # hand it back to the pool as it came

    timings["total_s"] = round(time.perf_counter() - started, 1)
    result = {
        "fetched": len(raw_news),
        "new": len(new_articles),
        "classified": len(classified),
        "failed": len(failed),
        "stored": stored,
        "embedded": embedded,
        "timings": timings,
    }
    log(f"[sync] done: {result}")
    return result
