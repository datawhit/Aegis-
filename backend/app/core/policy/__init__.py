"""Policy evaluation engine.

Phase 2: `JSONPolicyEngine` is the default. The Phase 0 `StubPolicyEngine`
remains as a fallback used only when no policies are seeded (tests, fresh
installs) — it returns ESCALATE for everything and enforces the ADR-005
invariants.

The selector picks based on settings; tests can construct the engine
directly with `JSONPolicyEngine()`.
"""

from app.config import settings
from app.core.policy.dsl import (
    PolicyDSLError,
    context_from_request,
    evaluate_match,
)
from app.core.policy.engine import (
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyEvalRequest,
    StubPolicyEngine,
)
from app.core.policy.json_engine import JSONPolicyEngine

__all__ = [
    "JSONPolicyEngine",
    "PolicyDSLError",
    "PolicyDecision",
    "PolicyEffect",
    "PolicyEngine",
    "PolicyEvalRequest",
    "StubPolicyEngine",
    "context_from_request",
    "evaluate_match",
    "get_policy_engine",
]


def get_policy_engine() -> PolicyEngine:
    """DI entrypoint. JSON engine in Phase 2+; stub honored if explicitly
    forced via env for emergency lockdown."""
    if settings.policy_engine_force_stub:
        return StubPolicyEngine()
    return JSONPolicyEngine()
