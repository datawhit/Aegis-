"""Aegis Policy DSL — Phase 2.

Goals:
  - **Readable** by a security engineer without reading docs.
  - **Auditable** — every evaluation can be traced operator by operator.
  - **Bounded** — no Turing-complete subset. Loops, file I/O, function calls
    are intentionally absent.
  - **Trivially serializable** — JSON in, JSON out.

A policy stored in the DB has this shape:

```json
{
  "name": "allow-revoke-sessions-for-impossible-travel",
  "priority": 100,
  "effect": "allow",
  "match": {
    "and": [
      {"eq":  {"action_class": "revoke_user_sessions"}},
      {"in":  {"incident_severity": ["medium", "high"]}},
      {"gte": {"ai_confidence": 0.85}},
      {"lte": {"blast_radius": 5}}
    ]
  },
  "constraints": {
    "requires_approval": false,
    "max_blast_radius": 5,
    "min_ai_confidence": 0.85
  }
}
```

`match` decides *if* the policy fires. `constraints` carries metadata that
the IncidentService respects (e.g. `requires_approval` forces human-in-loop
even on ALLOW). The DSL evaluator returns `True`/`False` for `match`; the
caller reads `constraints` separately.

Failure-mode contract (ADR-005):
  - Evaluator raises → caller treats it as `False` (no match), which
    propagates to `ESCALATE`.
  - Multiple policies at the same priority match → caller MUST ESCALATE.
  - No policy matches → caller MUST ESCALATE.
"""
from __future__ import annotations

import re
from typing import Any


class PolicyDSLError(ValueError):
    """Raised when a policy can't be evaluated. Treat as no-match upstream."""


def evaluate_match(expr: Any, ctx: dict[str, Any]) -> bool:
    """Evaluate a `match` expression against an evaluation context.

    `expr` is one of:
      - {"and": [<expr>, ...]}
      - {"or":  [<expr>, ...]}
      - {"not": <expr>}
      - {"eq":  {<field>: <value>}}
      - {"in":  {<field>: [<value>, ...]}}
      - {"gte": {<field>: <number>}}
      - {"lte": {<field>: <number>}}
      - {"matches": {<field>: "<regex>"}}
      - {} or {"any": true}    → match anything (use as a fall-through)

    `ctx` is the evaluation context provided by the caller — typically the
    flattened `PolicyEvalRequest` fields.

    Unknown operators or missing fields raise `PolicyDSLError`. Callers
    are expected to catch and treat-as-no-match.
    """
    if not isinstance(expr, dict):
        raise PolicyDSLError(f"expression must be an object, got {type(expr).__name__}")

    if expr == {} or expr.get("any") is True:
        return True

    if len(expr) != 1:
        raise PolicyDSLError(
            f"expression must have exactly one operator, got {sorted(expr.keys())}"
        )

    (op, arg) = next(iter(expr.items()))

    if op == "and":
        _require_list(op, arg)
        return all(evaluate_match(sub, ctx) for sub in arg)
    if op == "or":
        _require_list(op, arg)
        return any(evaluate_match(sub, ctx) for sub in arg)
    if op == "not":
        return not evaluate_match(arg, ctx)

    if op in {"eq", "in", "gte", "lte", "matches"}:
        if not isinstance(arg, dict) or len(arg) != 1:
            raise PolicyDSLError(
                f"`{op}` expects {{<field>: <value>}}, got {arg!r}"
            )
        (field, target) = next(iter(arg.items()))
        if field not in ctx:
            raise PolicyDSLError(f"field {field!r} not in evaluation context")
        return _apply_leaf(op, ctx[field], target)

    raise PolicyDSLError(f"unknown operator: {op!r}")


def _apply_leaf(op: str, value: Any, target: Any) -> bool:
    match op:
        case "eq":
            return value == target
        case "in":
            if not isinstance(target, list):
                raise PolicyDSLError("`in` target must be a list")
            return value in target
        case "gte":
            return _as_number(value) >= _as_number(target)
        case "lte":
            return _as_number(value) <= _as_number(target)
        case "matches":
            if not isinstance(target, str):
                raise PolicyDSLError("`matches` target must be a regex string")
            if not isinstance(value, str):
                return False
            try:
                return re.search(target, value) is not None
            except re.error as exc:
                raise PolicyDSLError(f"invalid regex: {exc}") from exc
        case _:  # pragma: no cover — `evaluate_match` filters these
            raise PolicyDSLError(f"unhandled operator {op!r}")


def _require_list(op: str, arg: Any) -> None:
    if not isinstance(arg, list):
        raise PolicyDSLError(f"`{op}` expects a list of sub-expressions")


def _as_number(value: Any) -> float:
    if isinstance(value, bool):
        # bool is a subclass of int in Python; treating True as 1 here would
        # mask schema errors. Refuse.
        raise PolicyDSLError("cannot compare boolean as number")
    if isinstance(value, (int, float)):
        return float(value)
    raise PolicyDSLError(f"expected number, got {type(value).__name__}: {value!r}")


def context_from_request(request: dict[str, Any]) -> dict[str, Any]:
    """Flatten a PolicyEvalRequest into a DSL evaluation context.

    Kept as a helper so the field names available to policies are
    documented in one place — adding a new policyable field means adding
    it here AND in the engine's evaluate(), nowhere else.
    """
    return {
        "action_class": request["action_class"],
        "blast_radius": request["blast_radius"],
        "ai_confidence": request.get("ai_confidence") or 0.0,
        "incident_severity": request["incident_severity"],
        "has_rollback_plan": request["has_rollback_plan"],
    }
