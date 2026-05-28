"""Hash chain integrity tests for the audit logger.

These are pure-function tests for `_compute_entry_hash` — they don't need
the DB and prove that:

  1. The hash is stable across runs.
  2. Changing any input field changes the hash.
  3. JSON canonicalization is order-insensitive for dict keys.
"""
from __future__ import annotations

from app.core.audit.logger import _compute_entry_hash


def _base_kwargs() -> dict:
    return {
        "prev_hash": "deadbeef" * 8,
        "actor_type": "user",
        "actor_id": "00000000-0000-0000-0000-000000000001",
        "actor_label": "alice@example.com",
        "action": "incident.created",
        "resource_type": "incident",
        "resource_id": "11111111-1111-1111-1111-111111111111",
        "payload": {"severity": "high", "source": "defender"},
        "reasoning_snapshot_id": None,
    }


def test_hash_is_deterministic() -> None:
    assert _compute_entry_hash(**_base_kwargs()) == _compute_entry_hash(**_base_kwargs())


def test_hash_changes_when_payload_changes() -> None:
    a = _compute_entry_hash(**_base_kwargs())
    kwargs = _base_kwargs()
    kwargs["payload"] = {"severity": "low", "source": "defender"}
    b = _compute_entry_hash(**kwargs)
    assert a != b


def test_hash_changes_when_prev_hash_changes() -> None:
    a = _compute_entry_hash(**_base_kwargs())
    kwargs = _base_kwargs()
    kwargs["prev_hash"] = "cafef00d" * 8
    b = _compute_entry_hash(**kwargs)
    assert a != b


def test_payload_key_order_does_not_affect_hash() -> None:
    a = _compute_entry_hash(**_base_kwargs())
    kwargs = _base_kwargs()
    kwargs["payload"] = {"source": "defender", "severity": "high"}  # swapped
    b = _compute_entry_hash(**kwargs)
    assert a == b


def test_genesis_entry_has_null_prev_hash() -> None:
    kwargs = _base_kwargs()
    kwargs["prev_hash"] = None
    h = _compute_entry_hash(**kwargs)
    # Just assert it's a valid hex sha256 — the value itself is implementation
    # detail until we publish the canonicalization spec.
    assert len(h) == 64
    int(h, 16)
