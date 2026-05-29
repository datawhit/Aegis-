"""HMAC verifier — happy path + failure modes."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from app.core.ingestion.base import (
    HMACVerificationError,
    verify_hmac,
)

SECRET = "test-secret"
BODY = b'{"alertId":"x"}'


def _sign(body: bytes, ts: int, secret: str = SECRET) -> str:
    message = f"{ts}.".encode() + body
    return "sha256=" + hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def test_valid_signature_passes() -> None:
    ts = int(time.time())
    verify_hmac(
        secret=SECRET,
        raw_body=BODY,
        signature_header=_sign(BODY, ts),
        timestamp_header=str(ts),
    )  # no raise


def test_missing_headers_fail() -> None:
    with pytest.raises(HMACVerificationError):
        verify_hmac(
            secret=SECRET,
            raw_body=BODY,
            signature_header=None,
            timestamp_header=str(int(time.time())),
        )
    with pytest.raises(HMACVerificationError):
        verify_hmac(
            secret=SECRET,
            raw_body=BODY,
            signature_header=_sign(BODY, int(time.time())),
            timestamp_header=None,
        )


def test_outside_replay_window_fails() -> None:
    old_ts = int(time.time()) - 3600  # 1h old
    with pytest.raises(HMACVerificationError):
        verify_hmac(
            secret=SECRET,
            raw_body=BODY,
            signature_header=_sign(BODY, old_ts),
            timestamp_header=str(old_ts),
        )


def test_tampered_body_fails() -> None:
    ts = int(time.time())
    sig = _sign(BODY, ts)
    with pytest.raises(HMACVerificationError):
        verify_hmac(
            secret=SECRET,
            raw_body=BODY + b" tampered",
            signature_header=sig,
            timestamp_header=str(ts),
        )


def test_wrong_secret_fails() -> None:
    ts = int(time.time())
    with pytest.raises(HMACVerificationError):
        verify_hmac(
            secret="different-secret",
            raw_body=BODY,
            signature_header=_sign(BODY, ts, "another"),
            timestamp_header=str(ts),
        )


def test_unsupported_algorithm_fails() -> None:
    ts = int(time.time())
    with pytest.raises(HMACVerificationError):
        verify_hmac(
            secret=SECRET,
            raw_body=BODY,
            signature_header="md5=deadbeef",
            timestamp_header=str(ts),
        )


def test_malformed_timestamp_fails() -> None:
    with pytest.raises(HMACVerificationError):
        verify_hmac(
            secret=SECRET,
            raw_body=BODY,
            signature_header="sha256=00",
            timestamp_header="not-an-int",
        )
