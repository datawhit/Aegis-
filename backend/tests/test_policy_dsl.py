"""Policy DSL evaluator — covers each operator and the failure-mode contract."""
from __future__ import annotations

import pytest

from app.core.policy.dsl import (
    PolicyDSLError,
    context_from_request,
    evaluate_match,
)


@pytest.fixture
def ctx() -> dict:
    return context_from_request(
        {
            "action_class": "revoke_user_sessions",
            "blast_radius": 3,
            "ai_confidence": 0.91,
            "incident_severity": "high",
            "has_rollback_plan": True,
        }
    )


def test_eq(ctx: dict) -> None:
    assert evaluate_match({"eq": {"action_class": "revoke_user_sessions"}}, ctx) is True
    assert evaluate_match({"eq": {"action_class": "disable_user"}}, ctx) is False


def test_in(ctx: dict) -> None:
    assert evaluate_match({"in": {"incident_severity": ["high", "critical"]}}, ctx)
    assert not evaluate_match({"in": {"incident_severity": ["low"]}}, ctx)


def test_gte_lte(ctx: dict) -> None:
    assert evaluate_match({"gte": {"ai_confidence": 0.85}}, ctx)
    assert not evaluate_match({"gte": {"ai_confidence": 0.99}}, ctx)
    assert evaluate_match({"lte": {"blast_radius": 5}}, ctx)
    assert not evaluate_match({"lte": {"blast_radius": 1}}, ctx)


def test_and_or_not(ctx: dict) -> None:
    expr = {
        "and": [
            {"eq": {"action_class": "revoke_user_sessions"}},
            {"or": [{"eq": {"incident_severity": "low"}}, {"gte": {"ai_confidence": 0.9}}]},
        ]
    }
    assert evaluate_match(expr, ctx)
    assert evaluate_match({"not": {"eq": {"action_class": "disable_user"}}}, ctx)


def test_matches_regex(ctx: dict) -> None:
    assert evaluate_match({"matches": {"action_class": "^revoke_"}}, ctx)


def test_any_matches_everything(ctx: dict) -> None:
    assert evaluate_match({"any": True}, ctx)
    assert evaluate_match({}, ctx)


def test_unknown_field_raises(ctx: dict) -> None:
    with pytest.raises(PolicyDSLError):
        evaluate_match({"eq": {"unknown_field": "x"}}, ctx)


def test_unknown_operator_raises(ctx: dict) -> None:
    with pytest.raises(PolicyDSLError):
        evaluate_match({"between": {"blast_radius": [1, 5]}}, ctx)


def test_malformed_expression_raises(ctx: dict) -> None:
    with pytest.raises(PolicyDSLError):
        evaluate_match({"eq": {"action_class": "x", "blast_radius": 1}}, ctx)


def test_bool_not_numeric(ctx: dict) -> None:
    with pytest.raises(PolicyDSLError):
        evaluate_match({"gte": {"has_rollback_plan": 0.5}}, ctx)
