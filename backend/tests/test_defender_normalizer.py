"""Defender connector — normalization spot-checks against the fixture."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.ingestion.defender import DefenderConnector

FIXTURE = Path(__file__).parent / "fixtures" / "defender_alert.json"


@pytest.fixture
def raw_event() -> dict:
    return json.loads(FIXTURE.read_text())


def test_extracts_canonical_ids(raw_event: dict) -> None:
    n = DefenderConnector().normalize(raw_event)
    assert n.source == "defender"
    assert n.source_event_id == "da637814123456789012_1234567890"


def test_correlation_key_rides_on_defender_incident_id(raw_event: dict) -> None:
    n = DefenderConnector().normalize(raw_event)
    assert n.correlation_key == "defender:incident:3142"


def test_severity_hint_maps_to_our_scale(raw_event: dict) -> None:
    n = DefenderConnector().normalize(raw_event)
    assert n.severity_hint == "high"


def test_affected_entities_extracted(raw_event: dict) -> None:
    n = DefenderConnector().normalize(raw_event)
    assert "kara.lin@aegis-demo.test" in n.affected_entities.get("users", [])
    assert "203.0.113.42" in n.affected_entities.get("ips", [])
    assert "https://exfil-rule.example/forward" in n.affected_entities.get("urls", [])


def test_correlation_key_falls_back_when_no_incident_id() -> None:
    n = DefenderConnector().normalize(
        {
            "alertId": "x1",
            "category": "CredentialAccess",
            "severity": "Medium",
            "evidence": [
                {
                    "@odata.type": "#microsoft.graph.security.userEvidence",
                    "userPrincipalName": "alice@example.test",
                }
            ],
        }
    )
    assert n.correlation_key is not None
    assert n.correlation_key != ""
    # Hash, not the literal user — confirms we're not leaking PII into a key.
    assert "alice" not in n.correlation_key
    assert "@" not in n.correlation_key


def test_severity_default_when_missing() -> None:
    n = DefenderConnector().normalize({"alertId": "x2"})
    assert n.severity_hint == "medium"


def test_excerpt_keeps_useful_fields_only(raw_event: dict) -> None:
    n = DefenderConnector().normalize(raw_event)
    keys = set(n.raw_event_excerpt.keys())
    assert "alertId" in keys
    assert "category" in keys
    assert "severity" in keys
    # Evidence is heavy — must NOT be in the excerpt.
    assert "evidence" not in keys
