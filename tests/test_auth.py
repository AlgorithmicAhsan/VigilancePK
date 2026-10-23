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
