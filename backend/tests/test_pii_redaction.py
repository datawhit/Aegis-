"""PII redactor — assert real PII is replaced and the lookup is invertible."""

from __future__ import annotations

from app.core.redaction import PIIRedactor


def test_emails_are_redacted() -> None:
    r = PIIRedactor(salt="test")
    out = r.redact({"normalized": {"affected_entities": {"users": ["alice@example.com"]}}})
    token = out.payload["normalized"]["affected_entities"]["users"][0]
    assert token.startswith("<user:")
    assert "alice" not in str(out.payload)
    assert out.lookup[token] == "alice@example.com"


def test_ipv4_is_redacted() -> None:
    r = PIIRedactor(salt="test")
    out = r.redact({"ip": "203.0.113.42"})
    assert out.payload["ip"].startswith("<ip:")
    assert "203.0.113.42" not in str(out.payload)


def test_same_value_collapses_to_same_token() -> None:
    r = PIIRedactor(salt="test")
    out = r.redact(
        {
            "primary": "alice@example.com",
            "echo": ["alice@example.com"],
            "elsewhere": "alice@example.com appeared again",
        }
    )
    primary_token = out.payload["primary"]
    echo_token = out.payload["echo"][0]
    assert primary_token == echo_token
    # And the echoed inline occurrence within a longer string.
    assert primary_token in out.payload["elsewhere"]


def test_different_salts_yield_different_tokens() -> None:
    r1 = PIIRedactor(salt="s1")
    r2 = PIIRedactor(salt="s2")
    t1 = r1.redact({"x": "alice@example.com"}).payload["x"]
    t2 = r2.redact({"x": "alice@example.com"}).payload["x"]
    assert t1 != t2  # tokens are salted; cross-snapshot correlation impossible


def test_lookup_table_size_matches_unique_pii() -> None:
    r = PIIRedactor(salt="test")
    out = r.redact(
        {
            "a": "alice@example.com",
            "b": "alice@example.com",
            "c": "bob@example.com",
            "d": "203.0.113.42",
        }
    )
    # Two unique emails + one IP = 3 entries
    assert len(out.lookup) == 3


def test_file_hashes_redacted() -> None:
    sha256 = "a" * 64
    r = PIIRedactor(salt="test")
    out = r.redact({"hash": sha256})
    assert out.payload["hash"].startswith("<file:")
