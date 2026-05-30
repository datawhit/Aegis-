"""End-to-end test for `verify_audit_export.py --server-url` (Sprint 8).

Spins up an in-process HTTP server that serves a well-known registry,
generates a signed export receipt offline, and confirms the CLI fetches
the right key and verifies successfully.

No FastAPI, no DB — keeps the test fast and the CLI's offline-only
guarantee honest.
"""

from __future__ import annotations

import http.server
import json
import socket
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.audit.export_signer import (
    build_receipt,
    entries_digest,
    generate_keypair_pem,
    load_private_key,
    sign_receipt,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_well_known_server(port: int, registry_body: dict) -> http.server.HTTPServer:
    payload = json.dumps(registry_body).encode("utf-8")

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/.well-known/aegis-audit-public-key":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_error(404)

        def log_message(self, *_args: object) -> None:  # silence noise
            return

    server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def _write_signed_export(tmp_path: Path, key_id: str, priv_pem: str) -> Path:
    """Build a 1-entry signed export NDJSON file using the offline helpers."""
    entry = {
        "id": "11111111-1111-1111-1111-111111111111",
        "created_at": "2026-05-29T00:00:00+00:00",
        "actor_type": "system",
        "actor_id": None,
        "actor_label": "test",
        "action": "test.signed",
        "resource_type": "test",
        "resource_id": None,
        "payload": {"k": "v"},
        "reasoning_snapshot_id": None,
        "prev_hash": None,
        # entry_hash is recomputed by the verifier; use whatever hash the
        # logger's canonicalisation would produce for the above fields.
        "entry_hash": "deadbeef" * 8,
    }
    receipt = build_receipt(
        range_since=None,
        range_until=datetime.now(UTC),
        count=1,
        head_entry_hash=entry["entry_hash"],
        tip_entry_hash=entry["entry_hash"],
        content_hash=entries_digest([entry["entry_hash"]]),
        exported_by="test@example.com",
        signing_key_id=key_id,
    )
    signed = sign_receipt(receipt, load_private_key(priv_pem))
    out = tmp_path / "export.ndjson"
    with out.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
        fh.write(json.dumps(signed) + "\n")
    return out


def test_verifier_resolves_key_from_server_url(tmp_path: Path) -> None:
    priv_active, pub_active = generate_keypair_pem()
    _priv_retired, pub_retired = generate_keypair_pem()
    key_id = "active-2026-05"
    export = _write_signed_export(tmp_path, key_id, priv_active)

    port = _free_port()
    server = _run_well_known_server(
        port,
        {
            "keys": [
                {"key_id": key_id, "status": "active", "public_pem": pub_active},
                {
                    "key_id": "retired-2026-04",
                    "status": "retired",
                    "public_pem": pub_retired,
                },
            ]
        },
    )
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.scripts.verify_audit_export",
                "--file",
                str(export),
                "--server-url",
                f"http://127.0.0.1:{port}",
                "--skip-entry-hash",  # entry_hash above is intentionally fake
            ],
            capture_output=True,
            text=True,
        )
    finally:
        server.shutdown()
    assert (
        result.returncode == 0
    ), f"verifier failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "OK" in result.stdout


def test_verifier_reports_missing_key_id(tmp_path: Path) -> None:
    priv_active, _pub_active = generate_keypair_pem()
    _priv_other, pub_other = generate_keypair_pem()
    key_id_in_receipt = "active-2026-05"
    export = _write_signed_export(tmp_path, key_id_in_receipt, priv_active)

    port = _free_port()
    # Registry serves a DIFFERENT key_id, so the CLI can't find a match.
    server = _run_well_known_server(
        port,
        {"keys": [{"key_id": "different-key", "status": "active", "public_pem": pub_other}]},
    )
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.scripts.verify_audit_export",
                "--file",
                str(export),
                "--server-url",
                f"http://127.0.0.1:{port}",
                "--skip-entry-hash",
            ],
            capture_output=True,
            text=True,
        )
    finally:
        server.shutdown()
    assert result.returncode == 1
    assert "no key_id=active-2026-05 found" in result.stderr


def test_verifier_mutex_requires_one_key_source(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.scripts.verify_audit_export",
            "--file",
            str(tmp_path / "missing.ndjson"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    # argparse prints "one of the arguments --public-key --server-url is required"
    assert "--public-key" in result.stderr and "--server-url" in result.stderr


_ = pytest  # silence unused import if pytest helpers not directly invoked
