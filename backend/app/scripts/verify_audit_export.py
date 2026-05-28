"""Verify a signed audit export (Sprint 4).

Usage:

    python -m app.scripts.verify_audit_export \
        --file audits_export.ndjson \
        --public-key /path/to/public.pem

Exit codes:
    0 — receipt signature valid, content hash matches, chain links intact
    1 — verification failure (mismatch, broken link, missing receipt, etc.)
    2 — usage / IO error

This script has zero dependencies on Aegis runtime state (DB, FastAPI).
It speaks only to the exported file + a public key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from app.core.audit.export_signer import (
    RECEIPT_MARKER_KEY,
    entries_digest,
    verify_receipt,
)
from app.core.audit.logger import _compute_entry_hash


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a signed audit export.")
    parser.add_argument("--file", required=True, type=Path, help="Path to .ndjson export.")
    parser.add_argument(
        "--public-key",
        required=True,
        type=Path,
        help="PEM-encoded Ed25519 public key used to sign exports.",
    )
    parser.add_argument(
        "--skip-entry-hash",
        action="store_true",
        help="Skip per-entry hash recomputation (useful for very large exports).",
    )
    return parser.parse_args()


def _fail(msg: str, exit_code: int = 1) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(exit_code)


def main() -> None:
    args = _parse_args()

    if not args.file.exists():
        _fail(f"export file not found: {args.file}", exit_code=2)
    if not args.public_key.exists():
        _fail(f"public key file not found: {args.public_key}", exit_code=2)

    public_key_pem = args.public_key.read_text(encoding="utf-8")

    entries: list[dict] = []
    receipt: dict | None = None
    with args.file.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                _fail(f"line {line_no}: malformed JSON ({exc})")
            if obj.get(RECEIPT_MARKER_KEY) is True:
                if receipt is not None:
                    _fail(f"line {line_no}: duplicate receipt marker")
                receipt = obj
            else:
                if receipt is not None:
                    _fail(f"line {line_no}: entry appears after receipt")
                entries.append(obj)

    if receipt is None:
        _fail("no receipt line found in export")
        return  # for type checker
    if receipt.get("signature") in (None, ""):
        _fail("receipt is unsigned (signature is null)")

    if not verify_receipt(receipt, public_key_pem):
        _fail("receipt signature does NOT verify against the provided public key")

    expected_count = receipt["range"]["count"]
    if expected_count != len(entries):
        _fail(
            f"entry count mismatch: receipt claims {expected_count}, file has {len(entries)}"
        )

    if entries:
        head_entry_hash = entries[-1]["entry_hash"]
        if head_entry_hash != receipt["head_entry_hash"]:
            receipt_head = receipt["head_entry_hash"]
            _fail(
                f"head_entry_hash mismatch: file={head_entry_hash} receipt={receipt_head}"
            )

    computed_content = entries_digest([e["entry_hash"] for e in entries])
    if computed_content != receipt["content_hash"]:
        _fail(
            f"content_hash mismatch: computed={computed_content} receipt={receipt['content_hash']}"
        )

    # Chain link verification: for i>0, prev_hash must equal entry[i-1].entry_hash
    for i in range(1, len(entries)):
        prev = entries[i - 1]
        cur = entries[i]
        if cur["prev_hash"] != prev["entry_hash"]:
            _fail(
                f"chain link broken at entry index {i}: "
                f"prev_hash={cur['prev_hash']} != prior entry_hash={prev['entry_hash']}"
            )

    # Per-entry recomputation: catches tampering with payload fields even
    # when entry_hash itself has been recomputed by an attacker (because
    # then the chain ahead would diverge from the server's tip too).
    if not args.skip_entry_hash:
        for i, entry in enumerate(entries):
            recomputed = _compute_entry_hash(
                prev_hash=entry["prev_hash"],
                actor_type=entry["actor_type"],
                actor_id=entry["actor_id"],
                actor_label=entry["actor_label"],
                action=entry["action"],
                resource_type=entry["resource_type"],
                resource_id=entry["resource_id"],
                payload=entry["payload"],
                reasoning_snapshot_id=entry["reasoning_snapshot_id"],
            )
            if recomputed != entry["entry_hash"]:
                _fail(
                    f"entry {i} (id={entry['id']}): recomputed hash {recomputed} "
                    f"does not match stored {entry['entry_hash']}"
                )

    # Bonus check: file SHA-256 (so the verifier can be quoted in a report).
    file_digest = hashlib.sha256(args.file.read_bytes()).hexdigest()

    print("OK")
    print(f"  entries        : {len(entries)}")
    print(f"  range.since    : {receipt['range']['since']}")
    print(f"  range.until    : {receipt['range']['until']}")
    print(f"  head_entry     : {receipt.get('head_entry_hash')}")
    print(f"  tip_entry      : {receipt.get('tip_entry_hash')}")
    print(f"  signing_key_id : {receipt.get('signing_key_id')}")
    print(f"  exported_by    : {receipt.get('exported_by')}")
    print(f"  exported_at    : {receipt.get('exported_at')}")
    print(f"  file_sha256    : {file_digest}")


if __name__ == "__main__":  # pragma: no cover
    main()
