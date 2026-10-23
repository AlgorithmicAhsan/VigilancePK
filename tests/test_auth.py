import pytest

from src.auth import hash_password, verify_password


def test_hash_round_trip():
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong horse battery", stored)


def test_same_password_gets_different_salts():
    assert hash_password("correct horse battery") != hash_password("correct horse battery")


def test_short_passwords_are_refused():
    with pytest.raises(ValueError):
        hash_password("short")


@pytest.mark.parametrize("stored", ["", "plain", "md5$x$y", "scrypt$a$b$c$d$e"])
def test_malformed_hashes_never_verify(stored):
    assert verify_password("anything at all", stored) is False


# --- tokens and lockout ---------------------------------------------------

from src.auth import LoginLimiter, create_token, verify_token

SECRET = "x" * 40


@pytest.fixture(autouse=False)
def secret(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", SECRET)


def test_token_round_trip(secret):
    token, expires = create_token(7, now=1_000_000)
    assert verify_token(token, now=1_000_001) == 7
    assert expires == 1_000_000 + 12 * 3600


def test_expired_token_is_rejected(secret):
    token, expires = create_token(7, now=1_000_000)
    assert verify_token(token, now=expires + 1) is None


def test_tampered_token_is_rejected(secret):
    token, _ = create_token(7)
    payload, signature = token.split(".")
    forged = create_token(8)[0].split(".")[0] + "." + signature
    assert verify_token(forged) is None
    assert verify_token(payload + "." + signature[:-2] + "AA") is None


def test_token_from_another_secret_is_rejected(secret, monkeypatch):
    token, _ = create_token(7)
    monkeypatch.setenv("SESSION_SECRET", "y" * 40)
    assert verify_token(token) is None


@pytest.mark.parametrize("junk", ["", "abc", "a.b.c", "....", "ZZZ.YYY"])
def test_junk_tokens_are_rejected(secret, junk):
    assert verify_token(junk) is None


def test_short_secret_is_refused(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "short")
    with pytest.raises(RuntimeError):
        create_token(1)


def test_limiter_locks_after_max_failures_then_expires():
    limiter = LoginLimiter(max_failures=3, lockout=600)
    for _ in range(2):
        limiter.failed("Ahsan", now=1000)
    assert limiter.locked_for("ahsan", now=1001) == 0
    limiter.failed("AHSAN", now=1002)
    assert limiter.locked_for("ahsan", now=1003) > 0
    assert limiter.locked_for("ahsan", now=1000 + 601) == 0


def test_limiter_success_clears_failures():
    limiter = LoginLimiter(max_failures=2, lockout=600)
    limiter.failed("a", now=10)
    limiter.succeeded("a")
    limiter.failed("a", now=11)
    assert limiter.locked_for("a", now=12) == 0
