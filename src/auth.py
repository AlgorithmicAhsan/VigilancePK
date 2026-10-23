"""Dashboard accounts (ADR-029).

Passwords are hashed with scrypt from the standard library: slow by design,
salted per user, no extra dependency.
"""
import base64
import hashlib
import hmac
import json
import os
import threading
import time

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
MIN_PASSWORD_LENGTH = 10

TOKEN_HOURS = 12
# Lockout after repeated wrong passwords for one username (ADR-031).
MAX_FAILURES, LOCKOUT_SECONDS = 5, 15 * 60


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# A hash nobody's password matches. Checking against it when the username
# doesn't exist makes a wrong username take as long as a wrong password, so
# response times don't reveal which usernames are real.
_DUMMY_HASH = None


def dummy_check(password: str) -> None:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(os.urandom(16).hex())
    verify_password(password, _DUMMY_HASH)


# --- Session tokens --------------------------------------------------------
# A signed, expiring token: base64(payload) + "." + HMAC-SHA256 signature.
# Stateless, so no sessions table. The user row is still re-read on every
# request, so disabling an account or changing a role takes effect at once.

def _secret() -> bytes:
    secret = os.getenv("SESSION_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("SESSION_SECRET is missing or shorter than 32 characters.")
    return secret.encode()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(user_id: int, now: float | None = None) -> tuple[str, int]:
    expires = int((now or time.time()) + TOKEN_HOURS * 3600)
    payload = _b64url(json.dumps({"uid": user_id, "exp": expires}, separators=(",", ":")).encode())
    signature = _b64url(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}", expires


def verify_token(token: str, now: float | None = None) -> int | None:
    """Returns the user id, or None if the token is forged, malformed or expired."""
    try:
        payload, signature = token.split(".")
        expected = _b64url(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_unb64url(payload))
        if data["exp"] < (now or time.time()):
            return None
        return int(data["uid"])
    except (ValueError, KeyError, TypeError):
        return None


# --- Login lockout ---------------------------------------------------------

class LoginLimiter:
    """Counts failed logins per username in memory. After MAX_FAILURES the
    username is locked for LOCKOUT_SECONDS. A restart clears it, which is
    acceptable for a single small server."""

    def __init__(self, max_failures=MAX_FAILURES, lockout=LOCKOUT_SECONDS):
        self.max_failures, self.lockout = max_failures, lockout
        self._failures = {}
        self._lock = threading.Lock()

    def locked_for(self, username: str, now: float | None = None) -> int:
        """Seconds until the username may try again (0 = not locked)."""
        now = now or time.time()
        with self._lock:
            count, first = self._failures.get(username.lower(), (0, now))
            if now - first > self.lockout:
                self._failures.pop(username.lower(), None)
                return 0
            return int(self.lockout - (now - first)) if count >= self.max_failures else 0

    def failed(self, username: str, now: float | None = None) -> None:
        now = now or time.time()
        with self._lock:
            count, first = self._failures.get(username.lower(), (0, now))
            if now - first > self.lockout:
                count, first = 0, now
            self._failures[username.lower()] = (count + 1, first)

    def succeeded(self, username: str) -> None:
        with self._lock:
            self._failures.pop(username.lower(), None)
