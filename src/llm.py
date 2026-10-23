"""Every Gemini call goes through this module (ADR-016, ADR-023).

Keeping the client, model names, retries and safety settings in one place
means swapping provider or model later is a change to this file only.
"""
import asyncio
import os
import re
import threading
import time
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()

CHAT_MODEL = os.getenv("CHAT_MODEL", "models/gemini-2.5-flash")
# Flash-Lite: classification is a constrained labelling task, and Lite has
# the most generous free-tier limits.
CLASSIFY_MODEL = os.getenv("CLASSIFY_MODEL", "models/gemini-3.1-flash-lite")

# Embeddings (ADR-033). The dimension is fixed by the articles table's
# vector(768) column, so it is a constant, not a setting.
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
EMBED_DIMS = 768
EMBED_BATCH = 100  # the API's per-request maximum

# The SDK retries transient server errors with backoff. Rate limits (429) are
# NOT retried here: retrying an exhausted key just burns time. They are
# handled below by moving to the next key (ADR-035).
RETRY = types.HttpRetryOptions(
    attempts=5,
    initial_delay=2.0,
    max_delay=30.0,
    exp_base=2.0,
    jitter=1.0,
    http_status_codes=[408, 500, 502, 503, 504],
)

# The corpus is, by design, reports of violence and abuse. Default filters
# block legitimate analysis and classification, so they are switched off.
SAFETY_OFF = [
    types.SafetySetting(category=category, threshold=types.HarmBlockThreshold.BLOCK_NONE)
    for category in (
        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    )
]

# --- API keys and rate-limit fallback (ADR-035) ------------------------------
# GOOGLE_API_KEY is the primary key. GOOGLE_API_KEYS (comma-separated) adds
# fallbacks, tried in order. Keys only add capacity when they belong to
# different Google Cloud projects: limits are per project, not per key.

MAX_WAIT_SECONDS = 65   # longest we sleep when every key is on a short cooldown
DAILY_COOLDOWN = 3600   # a key that hit a per-day limit is skipped for an hour
MINUTE_COOLDOWN = 30    # used when Google gives no retry delay
MAX_SWITCHES = 12       # safety stop for one call
REFUSED_COOLDOWN = 24 * 3600  # a key Google refuses is skipped for the rest of the run


class QuotaExhausted(RuntimeError):
    """Every key has hit its limit and none frees up soon."""


def _configured_keys() -> list[str]:
    keys = [os.getenv("GOOGLE_API_KEY", "")] + os.getenv("GOOGLE_API_KEYS", "").split(",")
    seen, out = set(), []
    for key in (k.strip() for k in keys):
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def quota_info(err: errors.ClientError) -> tuple[bool, float]:
    """(is it a per-day limit, seconds to wait) from Google's 429 details."""
    text = str(err.details)
    daily = "PerDay" in text
    match = re.search(r"retryDelay'?\s*:\s*'(\d+(?:\.\d+)?)s'", text)
    delay = float(match.group(1)) if match else MINUTE_COOLDOWN
    return daily, max(delay, DAILY_COOLDOWN) if daily else delay


class KeyPool:
    """One client per key, created on first use. The primary key is always
    preferred while it is available; a key that hits a limit cools down."""

    def __init__(self, keys, make_client):
        self.keys = keys
        self._make = make_client
        self._clients = [None] * len(keys)
        self._ready_at = [0.0] * len(keys)
        self.reasons = [""] * len(keys)  # why each key is sidelined, for messages
        self._lock = threading.Lock()

    def pick(self):
        """(index, client, 0) for the first usable key, or (None, None, wait)."""
        with self._lock:
            now = time.monotonic()
            for i, ready in enumerate(self._ready_at):
                if ready <= now:
                    # One client per key, made under the lock: spares made by
                    # racing threads used to close the shared connection.
                    if self._clients[i] is None:
                        self._clients[i] = self._make(self.keys[i])
                    return i, self._clients[i], 0.0
            return None, None, min(self._ready_at) - now

    def cool_down(self, index: int, seconds: float, reason: str = "") -> None:
        with self._lock:
            self._ready_at[index] = max(self._ready_at[index], time.monotonic() + seconds)
            self.reasons[index] = reason

    def free_key_other_than(self, index: int):
        now = time.monotonic()
        return next((i for i in range(len(self.keys)) if i != index and self._ready_at[i] <= now), None)


def _make_client(key: str) -> genai.Client:
    return genai.Client(api_key=key, http_options=types.HttpOptions(retry_options=RETRY))


_pool = None
_pool_lock = threading.Lock()


def key_configured() -> bool:
    return bool(_configured_keys())


def pool() -> KeyPool:
    """Built on first use, so importing this module never needs a key."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                keys = _configured_keys()
                if not keys:
                    raise RuntimeError("GOOGLE_API_KEY is not set.")
                _pool = KeyPool(keys, _make_client)
    return _pool


def client() -> genai.Client:
    """The client for the first key that isn't cooling down."""
    _, c, wait = pool().pick()
    if c is None:
        raise QuotaExhausted(f"Every Gemini key is rate-limited for another {wait:.0f} s.")
    return c


def key_refused(err: errors.ClientError) -> bool:
    """Google rejects the key or its project itself (not this request):
    invalid key, project denied access, API not enabled."""
    return err.code in (401, 403) or (err.code == 400 and "API_KEY_INVALID" in str(err.details))


def _sideline(p: KeyPool, index: int, err: errors.ClientError) -> None:
    """Takes a key out of rotation after a rate limit or a refusal, and says so."""
    if err.code == 429:
        daily, delay = quota_info(err)
        what = f"hit its {'daily' if daily else 'per-minute'} limit"
    else:
        delay = REFUSED_COOLDOWN
        what = f"was refused by Google ({err.code} {err.status}: {err.message}); skipping it for this run"
    p.cool_down(index, delay, what)
    nxt = p.free_key_other_than(index)
    then = f"switching to key {nxt + 1}" if nxt is not None else "no other key free"
    print(f"[llm] key {index + 1} of {len(p.keys)} {what}; {then}")


def _wait_or_give_up(p: KeyPool, wait: float, switches: int) -> None:
    if wait > MAX_WAIT_SECONDS or switches >= MAX_SWITCHES:
        detail = "; ".join(f"key {i + 1}: {r}" for i, r in enumerate(p.reasons) if r)
        raise QuotaExhausted(f"No Gemini key can take requests right now ({detail}). "
                             "Try again later or move to the paid tier.")
    print(f"[llm] every key is rate-limited; waiting {wait:.0f} s")


def with_fallback(call):
    """Runs call(client), moving to the next key on a rate limit."""
    p = pool()
    for switches in range(MAX_SWITCHES + 1):
        index, c, wait = p.pick()
        if c is None:
            _wait_or_give_up(p, wait, switches)
            time.sleep(wait)
            continue
        try:
            return call(c)
        except errors.ClientError as err:
            if err.code != 429 and not key_refused(err):
                raise
            _sideline(p, index, err)
    raise QuotaExhausted("Gave up after repeated rate limits.")


async def with_fallback_async(call):
    """Async twin of with_fallback, for the streaming chat."""
    p = pool()
    for switches in range(MAX_SWITCHES + 1):
        index, c, wait = p.pick()
        if c is None:
            _wait_or_give_up(p, wait, switches)
            await asyncio.sleep(wait)
            continue
        try:
            return await call(c)
        except errors.ClientError as err:
            if err.code != 429 and not key_refused(err):
                raise
            _sideline(p, index, err)
    raise QuotaExhausted("Gave up after repeated rate limits.")


# --- Calls -----------------------------------------------------------------------

def generate_json(prompt: str, system: str, model: str = CLASSIFY_MODEL, schema=None) -> str:
    """One blocking call that must return JSON. Returns the raw text."""
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.1,
        response_mime_type="application/json",
        response_schema=schema,
        safety_settings=SAFETY_OFF,
    )
    response = with_fallback(lambda c: c.models.generate_content(model=model, contents=prompt, config=config))
    return response.text or ""


async def stream_chat(query: str, system: str, model: str = CHAT_MODEL):
    """Yields the answer as text chunks. The key is chosen when the stream
    opens; a limit hit mid-answer is reported, not retried."""
    config = types.GenerateContentConfig(system_instruction=system, temperature=0.3, safety_settings=SAFETY_OFF)
    stream = await with_fallback_async(
        lambda c: c.aio.models.generate_content_stream(model=model, contents=query, config=config))
    async for chunk in stream:
        if chunk.text:
            yield chunk.text


def embed(texts: list[str], task: str) -> list[list[float]]:
    """Embeds texts in requests of up to 100. task: RETRIEVAL_DOCUMENT for
    stored articles, RETRIEVAL_QUERY for questions (ADR-007): Gemini tunes
    each side for its role."""
    config = types.EmbedContentConfig(task_type=task, output_dimensionality=EMBED_DIMS)
    vectors = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start:start + EMBED_BATCH]
        response = with_fallback(lambda c: c.models.embed_content(model=EMBED_MODEL, contents=batch, config=config))
        vectors += [e.values for e in response.embeddings]
    if len(vectors) != len(texts):
        raise RuntimeError(f"Expected {len(texts)} embeddings, got {len(vectors)}.")
    return vectors
