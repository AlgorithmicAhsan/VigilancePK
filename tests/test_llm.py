import threading

import pytest
from google.genai import errors

from src import llm


def rate_limit(daily=False, delay="20s"):
    quota = "GenerateRequestsPerDayPerProjectPerModel-FreeTier" if daily else "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
    return errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": quota}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}]}})


class FakeClient:
    def __init__(self, key):
        self.key = key


@pytest.fixture
def keys(monkeypatch):
    """Three keys; each test decides which ones fail."""
    monkeypatch.setenv("GOOGLE_API_KEY", "k1")
    monkeypatch.setenv("GOOGLE_API_KEYS", "k2, k3,k1")  # spaces and a repeat are tolerated
    monkeypatch.setattr(llm, "_pool", None)
    monkeypatch.setattr(llm, "_make_client", FakeClient)
    # A fake clock: sleeping advances it exactly, so cooldowns are
    # deterministic (the real Windows clock only ticks every ~15 ms).
    clock = [1000.0]
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(llm.time, "sleep", fake_sleep)
    return sleeps


def test_keys_are_primary_first_and_deduplicated(keys):
    assert llm._configured_keys() == ["k1", "k2", "k3"]


def test_primary_key_is_used_when_free(keys):
    assert llm.with_fallback(lambda c: c.key) == "k1"


def test_rate_limit_switches_to_next_key(keys):
    def call(c):
        if c.key == "k1":
            raise rate_limit()
        return c.key
    assert llm.with_fallback(call) == "k2"
    # k1 is cooling down, so the next call goes straight to k2.
    assert llm.with_fallback(lambda c: c.key) == "k2"
    assert keys == []  # never slept while another key was free


def test_daily_limits_on_every_key_stop_without_waiting(keys):
    def call(c):
        raise rate_limit(daily=True)
    with pytest.raises(llm.QuotaExhausted):
        llm.with_fallback(call)
    assert keys == []


def test_short_limits_on_every_key_wait_then_retry(keys):
    attempts = []

    def call(c):
        attempts.append(c.key)
        if len(attempts) <= 3:
            raise rate_limit(delay="0.01s")
        return c.key
    assert llm.with_fallback(call) == "k1"
    assert attempts[:3] == ["k1", "k2", "k3"] and len(keys) == 1


def test_other_errors_are_not_swallowed(keys):
    def call(c):
        raise errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "bad"}})
    with pytest.raises(errors.ClientError):
        llm.with_fallback(call)


def test_quota_info_reads_google_details():
    assert llm.quota_info(rate_limit(delay="33s")) == (False, 33.0)
    daily, delay = llm.quota_info(rate_limit(daily=True, delay="5s"))
    assert daily and delay == llm.DAILY_COOLDOWN


def test_concurrent_first_use_creates_one_client_per_key(keys, monkeypatch):
    """Regression: batches starting together each made a client, and the
    spares' cleanup closed the shared connection."""
    created = []
    monkeypatch.setattr(llm, "_make_client", lambda key: created.append(key) or FakeClient(key))
    gate = threading.Barrier(8)
    results = []

    def use():
        gate.wait()
        results.append(llm.client())

    threads = [threading.Thread(target=use) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert created == ["k1"]
    assert all(r is results[0] for r in results)


def refused():
    return errors.ClientError(403, {"error": {"code": 403, "status": "PERMISSION_DENIED",
                                              "message": "Your project has been denied access."}})


def test_refused_key_is_skipped_not_fatal(keys):
    def call(c):
        if c.key in ("k1", "k2"):
            raise refused()
        return c.key
    assert llm.with_fallback(call) == "k3"
    assert llm.with_fallback(lambda c: c.key) == "k3"  # stays skipped


def test_give_up_message_names_each_keys_problem(keys):
    def call(c):
        raise refused() if c.key == "k2" else rate_limit(daily=True)
    with pytest.raises(llm.QuotaExhausted) as info:
        llm.with_fallback(call)
    message = str(info.value)
    assert "key 1: hit its daily limit" in message and "key 2: was refused" in message
