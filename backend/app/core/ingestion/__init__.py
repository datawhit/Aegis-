"""Ingestion connectors — webhook signature verification + source-specific normalization."""

from app.core.ingestion.base import (
    Connector,
    ConnectorRegistry,
    HMACVerificationError,
    NormalizedAlert,
    verify_hmac,
)
from app.core.ingestion.defender import DefenderConnector

__all__ = [
    "Connector",
    "ConnectorRegistry",
    "DefenderConnector",
    "HMACVerificationError",
    "NormalizedAlert",
    "verify_hmac",
    "get_connector_registry",
]


def get_connector_registry() -> ConnectorRegistry:
    """Build the default registry. Connectors register themselves here so the
    ingest endpoint can dispatch by `source` path-param without a switch
    statement."""
    registry = ConnectorRegistry()
    registry.register(DefenderConnector())
    return registry
