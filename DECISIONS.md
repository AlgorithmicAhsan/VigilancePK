# Vigilance-PK — Decision Log

Every important choice we make, and **why it's the better option**.
New choices get added at the bottom as we go.

**Status meaning:**
- `Accepted` = agreed, maybe not coded yet
- `Implemented` = already in the code
- `Superseded` = replaced by a later choice

---

## Index
| # | Choice | Status |
|---|--------|--------|
| [ADR-000](#adr-000--deploy-on-free-tiers) | Deploy on free tiers | Accepted |
| [ADR-001](#adr-001--lite-means-lean-everywhere) | "Lite" means lean everywhere | Accepted |
| [ADR-002](#adr-002--one-clean-shape-for-search-results) | One clean shape for search results | Implemented |
| [ADR-003](#adr-003--one-setting-for-the-chat-model) | One setting for the chat model | Implemented |
| [ADR-004](#adr-004--make-the-classifier-explain-itself) | Make the classifier explain itself | Implemented |
| [ADR-005](#adr-005--use-gemini-for-embeddings) | Use Gemini for embeddings | Accepted |
| [ADR-006](#adr-006--use-qdrant-cloud-for-storage) | Use Qdrant Cloud for storage | Superseded by ADR-017 |
| [ADR-007](#adr-007--tag-embeddings-by-their-job) | Tag embeddings by their job | Accepted |
| [ADR-008](#adr-008--a-clean-dependency-list) | A clean dependency list | Accepted |
| [ADR-009](#adr-009--three-layers-of-testing) | Three layers of testing | Accepted |
| [ADR-010](#adr-010--escape-everything-that-comes-from-a-feed) | Escape everything that comes from a feed | Implemented |
| [ADR-011](#adr-011--one-place-to-point-the-ui-at-the-api) | One place to point the UI at the API | Implemented |
| [ADR-012](#adr-012--errors-get-real-status-codes) | Errors get real status codes | Implemented |
| [ADR-013](#adr-013--the-ui-never-invents-a-status) | The UI never invents a status | Implemented |
| [ADR-014](#adr-014--whole-word-matching-in-the-scout-filter) | Whole-word matching in the scout filter | Implemented |
| [ADR-015](#adr-015--never-guess-a-publication-date) | Never guess a publication date | Implemented |
| [ADR-016](#adr-016--drop-ollama-gemini-only) | Drop Ollama, Gemini only | Implemented |
| [ADR-017](#adr-017--neon-postgres--pgvector-for-storage) | Neon Postgres + pgvector for storage | Accepted |

---

## ADR-000 — Deploy on free tiers
**Status:** Accepted

- Frontend goes on **Vercel**, backend on **Railway/Render**, all free.
- Free tiers are tight: ~512 MB RAM, small app size, disk that wipes on restart, slow cold starts.
- **Choice:** treat these limits as rules we design around from the start.

**Why it's better:**
- Stops the "works on my laptop, won't start on the host" problem.
- Every later choice is judged by "does it fit and survive on a free box?"

**Cost we accept:** a little extra delay from calling outside services. Worth it.

---

## ADR-001 — "Lite" means lean everywhere
**Status:** Accepted

- The frontend was never the heavy part — it's one small HTML file.
- The real weight is the backend: ~2.5 GB of unused libraries, plus broken and unsafe code.
- **Choice:** "lite" = lean, correct, secure, and tested — not just a small UI.

**Why it's better:**
- Shrinking the tiny frontend saves almost nothing.
- The big wins are in the backend size and in not shipping broken code.

**Cost we accept:** more work than a simple UI swap, but it's the work that actually helps.

---

## ADR-002 — One clean shape for search results
**Status:** Implemented · Files: `src/vault.py`, `src/api.py`

- The old search returned ChromaDB's raw format (a dict of lists).
- The chat code checked if it was a *list* — it never was — so **every search result was thrown away**.
- The AI was answering from memory, with no sources, even though the UI promised grounded answers.
- **Choice:** search now always returns a simple list of `{document, metadata, distance}`.

**Why it's better:**
- The RAG feature actually works now — real sources, real citations.
- The rest of the code no longer cares which database we use. This makes the Qdrant switch (ADR-006) painless.
- Empty results return an empty list instead of crashing.

**Cost we accept:** none worth mentioning.

---

## ADR-003 — One setting for the chat model
**Status:** Implemented · Files: `src/api.py`

- The chat code picked a path based on one variable but then used a different hardcoded model.
- So the Ollama path was dead, and changing the model did nothing.
- **Choice:** one setting (`chat_model`) controls everything.

**Why it's better:**
- One knob. Switching between cloud (Gemini) and local (Ollama) is a one-line change that actually works.

**Cost we accept:** none.

---

## ADR-004 — Make the classifier explain itself
**Status:** Implemented · Files: `src/jurist.py`

- The code saved a `reasoning` field, but the prompt never asked for one — so it was always blank.
- **Choice:** the prompt now asks for a one-line reason for each classification.

**Why it's better:**
- For a human-rights tool, knowing *why* something was tagged matters as much as the tag.
- Helps with review and debugging.

**Cost we accept:** a few extra words per result. Trivial.

---

## ADR-005 — Use Gemini for embeddings
**Status:** Accepted · Files (planned): `src/vault.py`, `requirements.txt`, `.env*`

- Embeddings were made locally by a model that pulls in Torch (~2 GB) and takes 3–10 s to load.
- That doesn't fit a 512 MB free box, and the slow load hurts every restart.
- **Choice:** make embeddings with the **Gemini API** (same key we already use). Drop Torch.

**Why it's better:**
- Removes the single biggest library — the backend can finally fit a free box.
- No slow model load on startup.
- Frees ~400 MB of memory.
- Better Urdu ↔ English matching, which is the whole point of the project.

**Cost we accept:**
- ~100–250 ms per call over the network (unnoticeable at our traffic).
- A small per-use cost (covered by the free quota).
- We looked at `fastembed` (local, no Torch, free) but it's weaker on cross-language quality. Kept as a backup.

---

## ADR-006 — Use Qdrant Cloud for storage
**Status:** Superseded by [ADR-017](#adr-017--neon-postgres--pgvector-for-storage) · Files (planned): `src/vault.py`, `src/api.py`, `requirements.txt`, `.env*`

- ChromaDB saved to local disk. On Render's free tier, **that disk wipes on every restart** — so the database would vanish.
- **Choice:** store vectors in a free **Qdrant Cloud** cluster instead.

**Why it's better:**
- The data survives restarts and redeploys — the deal-breaker that local storage fails.
- Takes the database load off our tiny app box.

**Cost we accept:**
- ~20–80 ms per search over the network (fine).
- One more service and two settings (`QDRANT_URL`, `QDRANT_API_KEY`).
- Thanks to ADR-002, only the `Vault` internals change.
- Backup option: Railway's paid-ish persistent volume + Chroma, if we ever want it.

---

## ADR-007 — Tag embeddings by their job
**Status:** Accepted · Files (planned): `src/vault.py`

- Gemini lets you label an embedding as a "document" or a "query."
- **Choice:** label stored articles as documents, and searches as queries.

**Why it's better:**
- The model tunes each one for its role, so searches match articles better.
- A free quality boost the old local model couldn't do.

**Cost we accept:** none, just use the right label on each side.

---

## ADR-008 — A clean dependency list
**Status:** Accepted · Files (planned): `requirements.txt`, `requirements-dev.txt`

- The current list is a raw export of ~186 packages — TensorFlow, Torch, Keras, Streamlit, OpenAI — **none of which the app uses**.
- **Choice:** keep only the ~15 packages we actually import. Put test/dev tools in a separate file.

**Why it's better:**
- Biggest single size cut — gigabytes gone.
- Smaller list = fewer security holes and faster installs.

**Cost we accept:** if we miss one, it shows up instantly as an error in CI. Easy to fix.

---

## ADR-009 — Three layers of testing
**Status:** Accepted · Files (planned): `tests/`, `postman/`, `.github/workflows/`

Testing splits into three jobs that cost very different amounts, so we keep them separate:

1. **Unit tests (`pytest`)** — fast logic checks, no internet, no key. Run on every push.
2. **API tests (`TestClient` + Postman)** — check the endpoints and the streaming chat reply. Postman also runs after deploy to smoke-test the live site.
3. **RAG quality (`DeepEval`)** — scores answer quality using Gemini as judge. Costs money and varies, so it runs nightly or on demand, not every push.

**Why it's better:**
- The cheap, fast checks guard every change.
- The expensive AI-judged check only runs when it's worth it.

**Cost we accept:**
- A bit more setup, and the quality check needs a key in CI.
- We write the API tests *after* the Phase-2 switch so we don't redo them. Unit tests can come first.

---

## ADR-010 — Escape everything that comes from a feed
**Status:** Implemented · Files: `lite-web/index.html`

- The feed cards, the source chips and the chat bubble all built HTML with `innerHTML` using raw text from third-party RSS.
- RSS summaries routinely carry HTML. A hostile or compromised feed could run script in an analyst's browser.
- Source links went straight into `href`, so a `javascript:` link in a feed would fire on click.
- **Choice:** two helpers — `esc()` for anything put into HTML, `safeUrl()` for anything used as a URL (http/https only, everything else dropped).

**Why it's better:**
- Our readers are human rights defenders. Their browser is the last place we can afford to run someone else's code.
- The safe pattern was already in the file (`innerText` for streamed replies) — now it is applied everywhere.

**Cost we accept:** every new template has to remember `esc()`. Cheap next to the risk.

---

## ADR-011 — One place to point the UI at the API
**Status:** Implemented · Files: `lite-web/index.html`, `.env.example`

- `http://localhost:8000` was hardcoded in five separate fetch calls.
- ADR-000 puts the dashboard on Vercel over HTTPS, which cannot call `http://localhost` at all.
- **Choice:** a single `API_BASE` constant at the top of the script, plus `ALLOWED_ORIGINS` on the backend.

**Why it's better:**
- Deploying becomes a one-line edit instead of a find-and-replace.
- The CORS list and the UI target are now two settings that obviously belong together.

**Cost we accept:** still a manual edit, since the page has no build step. Fine for one line.

---

## ADR-012 — Errors get real status codes
**Status:** Implemented · Files: `src/api.py`

- `/feed` and `/stats` caught every exception and returned `{"error": ...}` with HTTP **200**.
- The UI checked `data.length`, got `undefined`, and drew "VAULT_EMPTY // RUN_SYNC". A crashed backend looked exactly like an empty database.
- The raw exception text was handed to any caller.
- **Choice:** raise `HTTPException(500)` with a short message; log the detail server-side.

**Why it's better:**
- "Broken" and "empty" are different things and now look different.
- Internal paths and stack details stay on the server.

**Cost we accept:** the UI has to check `res.ok`. It does.

---

## ADR-013 — The UI never invents a status
**Status:** Implemented · Files: `lite-web/index.html`, `src/api.py`

- The health panel printed `LATENCY: 14ms` and `LOCATION: ISLAMABAD_NEXUS` as fixed strings.
- The config panel printed `API_KEY: VERIFIED` whether or not a key existed.
- The header badge always read `System_Online`, even with the backend down.
- **Choice:** latency is measured, the key state comes from a new `gemini_key_configured` field on `/stats`, and the badge reflects a real reachability check.

**Why it's better:**
- A tool that fakes its own telemetry cannot be trusted about the intelligence either.
- "API_Offline" in red is far more useful than a green light that means nothing.

**Cost we accept:** one extra `/stats` call on page load.

---

## ADR-014 — Whole-word matching in the scout filter
**Status:** Implemented · Files: `src/scout.py`

- The exclusion list was matched as plain substrings against title and summary.
- `"score"` matched *"Scores of protesters killed"*. `"match"` matched *"matched"*. Those articles were silently dropped before ever reaching the Jurist.
- **Choice:** one compiled regex with `\b` word boundaries. Same keywords, same intent.

**Why it's better:**
- We were discarding exactly the reports this project exists to collect, with no log line to show it.
- Verified: four real human-rights headlines now survive; the sports headline is still dropped.

**Cost we accept:** none. Note the list still drops `weather` / `earthquake` stories, which can carry displacement and IDP angles — worth revisiting separately.

---

## ADR-015 — Never guess a publication date
**Status:** Implemented · Files: `src/scout.py`

- When a feed date failed to parse, the code substituted `datetime.now()`.
- `/feed` sorts by that field, so every undated article was promoted to the top as if it had just broken.
- Parsed dates were timezone-aware while the fallback was naive, so the two could not be string-sorted against each other correctly.
- **Choice:** leave the date empty when it cannot be parsed, log it, and coerce every real date to UTC.

**Why it's better:**
- An empty date sorts to the bottom, which is honest. A fake date sorts to the top, which is a lie about recency.
- One timezone means the cheap string sort in `/feed` is actually correct.

**Cost we accept:** undated articles are easy to miss at the bottom of the feed. Better than trusting a made-up timestamp.

---

## ADR-016 — Drop Ollama, Gemini only
**Status:** Implemented · Files: `src/api.py`, `src/jurist.py`, `requirements.txt`, `.env.example`, `README.md`

- Every model call had two code paths: Gemini and Ollama.
- A local model cannot run on a 512 MB free box (ADR-000). It only works if a home PC stays on as the server.
- Small local models (qwen2.5:1.5b) are weak on Urdu and on a 20-category taxonomy.
- The Ollama chat path also blocked the server: a sync streaming loop inside an async handler.
- **Choice:** Gemini only. Removed the `ollama` package and both Ollama paths. Both model settings now default to a Gemini model.
- Also removed the Qwen `<think>` stripping. It only mattered for local reasoning models.

**Why it's better:**
- One code path to test and fix instead of two.
- One less package, and no hidden dependency on a local server.
- Gemini is the strongest of our options on Urdu, which is half the corpus.

**Cost we accept:**
- No offline mode for now. Model calls are kept small and in one place, so a local or Groq option can come back later.
- Fully dependent on Gemini quota. Batched classification (planned) keeps us well under it.

---

## ADR-017 — Neon Postgres + pgvector for storage
**Status:** Accepted · Files (planned): `src/vault.py`, `src/api.py`, `requirements.txt`, `.env*`

- ChromaDB lives on local disk, which free hosts wipe on restart.
- JSON files have the same problem, plus no search and risky concurrent writes.
- Qdrant (ADR-006) only stores vectors. We would still need somewhere for the article records, sorting and filtering.
- `/feed` currently loads the whole collection just to sort by date.
- **Choice:** one Postgres database on **Neon's free tier**, with the `pgvector` extension for search.
- JSON stays only as an export/backup format.

**Why it's better:**
- One store for articles and vectors. Feed = `ORDER BY published DESC LIMIT 15`.
- Filters by category, severity and date (the triage UI) are plain SQL.
- Data survives restarts and redeploys.
- Neon sleeps when idle and wakes in about a second. Supabase pauses free projects after a week of no use.

**Cost we accept:**
- A short cold start on the first query after Neon has been idle.
- 0.5 GB free storage. Roughly 100k articles at 768-dimension vectors, far beyond current volume.
- One more secret (`DATABASE_URL`) to manage.

---

<!--
ADD NEW CHOICES BELOW. Keep it simple — short bullets, plain words.
Template:
## ADR-NNN — <short title>
**Status:** Accepted|Implemented|Superseded · Files: <paths>
- <context in a few bullets>
- **Choice:** <what we picked>
**Why it's better:** <short bullets>
**Cost we accept:** <what we gave up>
Then add a row to the Index table at the top.
-->
