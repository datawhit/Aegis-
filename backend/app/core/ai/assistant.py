"""Aegis Assistant — read-only RAG-via-tool-use chat (Sprint 10).

Architecture:

  user message
    → AssistantService.chat()
      → Claude (with the tool set defined below)
        → may call zero or more tools (database reads)
        → returns a final text answer
    → AssistantResponse(answer=..., sources=[...])

The assistant is STRICTLY READ-ONLY (OQ-35 settled). Every tool reads
from the existing tables — no writes, no policy/approval mutation. The
LLM can't propose actions; it can only summarise + explain what Aegis
has already done.

Cited sources are surfaced as a list of structured references the UI
turns into clickable links (incident, action, policy). The model isn't
asked to format URLs — the backend captures them from the tool-call
record.

Model defaults to `claude-sonnet-4-6` (matches Triage, ADR-007). Falls
back to a helpful error when AEGIS_ANTHROPIC_API_KEY is empty so local
dev without a key sees a friendly 503 rather than an unhandled crash.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging import get_logger
from app.models.audit_log import AuditLog
from app.models.incident import Incident, IncidentStatus
from app.models.policy import Policy
from app.models.remediation_action import (
    RemediationAction,
    RemediationStatus,
)

log = get_logger("assistant")

_DEFAULT_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1024
_MAX_TOOL_ROUNDS = 4  # cap recursion: model -> tool -> model -> tool -> model

SYSTEM_PROMPT = """\
You are Aegis Assistant — the conversational surface of an autonomous \
security operator. Your job is to answer the operator's questions about \
what Aegis did, why, and what risk it reduced, drawing on the read-only \
tools provided.

Rules:
- Always ground your answer in tool results. Do not invent counts, IDs, \
or policy names.
- If a tool returns no data, say so plainly — do not speculate.
- Be concise: short paragraphs, plain language, no marketing.
- You CANNOT propose actions, approve, deny, or rollback. You can only \
read, summarise, and explain. If asked to act, say so and suggest the \
human go to the Review Queue.
- When you cite specific actions, incidents, or policies, mention them \
by their human-readable name (the backend will turn them into links).
"""


# ─────────────────────────────────────────────────────────────────────
# Public response shapes
# ─────────────────────────────────────────────────────────────────────


@dataclass
class AssistantSource:
    kind: str  # "incident" | "action" | "policy"
    id: str
    label: str


@dataclass
class AssistantResponse:
    answer: str
    sources: list[AssistantSource] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    model: str = _DEFAULT_MODEL


class AssistantError(RuntimeError):
    """Raised when the assistant can't satisfy a request."""


class AssistantNotConfigured(AssistantError):
    """The Anthropic API key is missing — assistant is disabled."""


# ─────────────────────────────────────────────────────────────────────
# Tool definitions — described to the model + executed against the DB
# ─────────────────────────────────────────────────────────────────────

TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "get_overview",
        "description": (
            "Returns the operator overview: overnight summary "
            "(issues_evaluated, resolved_autonomously, stabilized, "
            "escalated, analyst_hours_saved), the Aegis Trust Score, "
            "and the current Risk Snapshot. Call this for questions "
            "like 'what did you do overnight?', 'how is trust?', "
            "'how much risk did we reduce?'."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_recent_actions",
        "description": (
            "Returns up to 20 recent Aegis actions, optionally filtered "
            "by outcome (resolved | stabilized | escalated). Use this "
            "when the question is about what specific actions Aegis "
            "took, or to enumerate escalations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "outcome": {
                    "type": "string",
                    "enum": ["all", "resolved", "stabilized", "escalated"],
                    "description": "Filter by outcome label. Defaults to 'all'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "How many to return (1-20). Defaults to 10.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_action_detail",
        "description": (
            "Returns detail for a single Aegis action: the remediation "
            "action's class, status, blast radius, AI confidence, and "
            "the policy that governed the decision. Use when asked "
            "'why did you revoke this session?' or similar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action_id": {
                    "type": "string",
                    "description": "UUID of the remediation_action row.",
                }
            },
            "required": ["action_id"],
        },
    },
    {
        "name": "get_top_policies",
        "description": (
            "Returns the top N policies by activity (audit-chain "
            "`policy.evaluated` count) in the last 24h. Use for "
            "'which policies generated the most actions?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "How many policies to return (1-10). Defaults to 5.",
                }
            },
            "required": [],
        },
    },
]


# ─────────────────────────────────────────────────────────────────────
# Tool implementations
# ─────────────────────────────────────────────────────────────────────


async def _tool_get_overview(session: AsyncSession, _args: dict[str, Any]) -> dict[str, Any]:
    from app.api.v1.overview import (
        _overnight_summary,
        _requires_attention,
        _risk_snapshot,
        _trust_score,
    )

    now = datetime.now(UTC)
    overnight = await _overnight_summary(
        session, last_24h=now - timedelta(hours=24), last_48h=now - timedelta(hours=48)
    )
    trust = await _trust_score(
        session,
        last_24h=now - timedelta(hours=24),
        last_7d=now - timedelta(days=7),
        last_30d=now - timedelta(days=30),
    )
    risk = await _risk_snapshot(
        session, last_24h=now - timedelta(hours=24), last_48h=now - timedelta(hours=48)
    )
    attention = await _requires_attention(session)
    return {
        "overnight_summary": overnight.model_dump(),
        "trust_score": trust.model_dump(),
        "risk_snapshot": risk.model_dump(),
        "requires_attention": attention.model_dump(),
    }


async def _tool_get_recent_actions(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    outcome = args.get("outcome", "all")
    limit = max(1, min(int(args.get("limit", 10)), 20))

    stmt = (
        select(RemediationAction, Incident)
        .join(Incident, Incident.id == RemediationAction.incident_id)
        .order_by(RemediationAction.created_at.desc())
        .limit(limit * 4)
    )
    rows = (await session.execute(stmt)).all()
    items = []
    for action, incident in rows:
        action_class = (
            action.action_class.value
            if hasattr(action.action_class, "value")
            else str(action.action_class)
        )
        status = action.status.value if hasattr(action.status, "value") else str(action.status)
        if status == RemediationStatus.EXECUTED.value:
            label = "stabilized" if action.action_class.is_stabilization else "resolved"
        elif status == RemediationStatus.POLICY_ESCALATED.value:
            label = "escalated"
        else:
            continue
        if outcome != "all" and outcome != label:
            continue
        items.append(
            {
                "action_id": str(action.id),
                "incident_id": str(incident.id),
                "incident_title": incident.title,
                "incident_severity": (
                    incident.severity.value
                    if hasattr(incident.severity, "value")
                    else str(incident.severity)
                ),
                "action_class": action_class,
                "outcome": label,
                "ai_confidence": action.ai_confidence,
                "created_at": action.created_at.isoformat(),
            }
        )
        if len(items) >= limit:
            break
    return {"items": items, "count": len(items), "outcome_filter": outcome}


async def _tool_get_action_detail(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    raw = args.get("action_id")
    try:
        action_id = uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return {"error": f"action_id={raw!r} is not a valid UUID"}

    action = (
        await session.execute(select(RemediationAction).where(RemediationAction.id == action_id))
    ).scalar_one_or_none()
    if action is None:
        return {"error": f"no remediation action with id {raw}"}

    incident = (
        await session.execute(select(Incident).where(Incident.id == action.incident_id))
    ).scalar_one_or_none()

    policy_id_row = (
        await session.execute(
            select(AuditLog.payload["winning_policy_id"].astext)
            .where(
                AuditLog.action == "policy.evaluated",
                AuditLog.resource_type == "remediation_action",
                AuditLog.resource_id == action_id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    policy_name = None
    if policy_id_row:
        try:
            policy = (
                await session.execute(select(Policy).where(Policy.id == uuid.UUID(policy_id_row)))
            ).scalar_one_or_none()
            policy_name = policy.name if policy else None
        except ValueError:
            pass

    action_class = (
        action.action_class.value
        if hasattr(action.action_class, "value")
        else str(action.action_class)
    )
    return {
        "action_id": str(action.id),
        "action_class": action_class,
        "is_stabilization": action.action_class.is_stabilization,
        "is_reversible": action.action_class.is_reversible,
        "status": (action.status.value if hasattr(action.status, "value") else str(action.status)),
        "blast_radius": action.blast_radius,
        "ai_confidence": action.ai_confidence,
        "policy_id": policy_id_row,
        "policy_name": policy_name,
        "incident_id": str(incident.id) if incident else None,
        "incident_title": incident.title if incident else None,
    }


async def _tool_get_top_policies(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    from sqlalchemy import func

    limit = max(1, min(int(args.get("limit", 5)), 10))
    last_24h = datetime.now(UTC) - timedelta(hours=24)
    winning_id_expr = AuditLog.payload["winning_policy_id"].astext
    counts_rows = (
        await session.execute(
            select(winning_id_expr.label("policy_id"), func.count(AuditLog.id).label("n"))
            .where(
                AuditLog.action == "policy.evaluated",
                AuditLog.created_at >= last_24h,
                winning_id_expr.isnot(None),
            )
            .group_by(winning_id_expr)
            .order_by(func.count(AuditLog.id).desc())
            .limit(limit)
        )
    ).all()
    if not counts_rows:
        return {"items": []}

    resolved_ids = []
    for pid, _n in counts_rows:
        try:
            resolved_ids.append(uuid.UUID(str(pid)))
        except ValueError:
            continue
    names_by_id = {
        str(pid): name
        for pid, name in (
            await session.execute(select(Policy.id, Policy.name).where(Policy.id.in_(resolved_ids)))
        ).all()
    }
    return {
        "items": [
            {
                "policy_id": str(pid),
                "name": names_by_id.get(str(pid), "(unknown policy)"),
                "actions_count": int(n),
            }
            for pid, n in counts_rows
        ]
    }


_TOOL_DISPATCH = {
    "get_overview": _tool_get_overview,
    "get_recent_actions": _tool_get_recent_actions,
    "get_action_detail": _tool_get_action_detail,
    "get_top_policies": _tool_get_top_policies,
}


def _sources_from_tool_calls(
    tool_results: list[tuple[str, dict[str, Any]]],
) -> list[AssistantSource]:
    """Walk the tool-result payloads and extract structured references the
    UI can render as clickable links."""
    sources: list[AssistantSource] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, id_: str, label: str) -> None:
        key = (kind, id_)
        if key not in seen:
            seen.add(key)
            sources.append(AssistantSource(kind=kind, id=id_, label=label))

    for name, result in tool_results:
        if name == "get_recent_actions":
            for item in result.get("items", []):
                _add(
                    "action",
                    item["action_id"],
                    f"{item['action_class']} on {item['incident_title']}",
                )
        elif name == "get_action_detail" and "action_id" in result:
            _add("action", result["action_id"], result.get("action_class", "action"))
            if result.get("incident_id"):
                _add(
                    "incident",
                    result["incident_id"],
                    result.get("incident_title", "incident"),
                )
            if result.get("policy_id"):
                _add("policy", result["policy_id"], result.get("policy_name", "policy"))
        elif name == "get_top_policies":
            for item in result.get("items", []):
                _add("policy", item["policy_id"], item["name"])
    return sources


# ─────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────


class AssistantService:
    def __init__(self, *, model: str = _DEFAULT_MODEL) -> None:
        self._model = model
        if not settings.anthropic_api_key:
            self._client: anthropic.AsyncAnthropic | None = None
        else:
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def chat(self, session: AsyncSession, message: str) -> AssistantResponse:
        if self._client is None:
            raise AssistantNotConfigured(
                "Anthropic API key is not configured. Set AEGIS_ANTHROPIC_API_KEY."
            )

        messages: list[dict[str, Any]] = [{"role": "user", "content": message}]
        tool_results_log: list[tuple[str, dict[str, Any]]] = []

        for round_idx in range(_MAX_TOOL_ROUNDS):
            # SDK types want strict TypedDicts for `tools` and `messages`;
            # we build plain dicts and the SDK accepts them at runtime.
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFS,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            )
            stop_reason = response.stop_reason

            # Append the assistant's reply (text and/or tool_use blocks).
            messages.append({"role": "assistant", "content": response.content})

            if stop_reason != "tool_use":
                # Final answer — extract text and return.
                text_blocks: list[str] = []
                for block in response.content:
                    if block.type == "text":
                        text_blocks.append(block.text)
                final_answer = "\n\n".join(text_blocks).strip() or (
                    "(Assistant returned no text. Try rephrasing the question.)"
                )
                log.info(
                    "assistant.chat.completed",
                    rounds=round_idx + 1,
                    tool_calls=[name for name, _ in tool_results_log],
                )
                return AssistantResponse(
                    answer=final_answer,
                    sources=_sources_from_tool_calls(tool_results_log),
                    tool_calls=[name for name, _ in tool_results_log],
                    model=self._model,
                )

            # Execute every tool_use block in this response.
            tool_results_for_msg: list[dict[str, Any]] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tool_name = block.name
                raw_args = block.input
                tool_args: dict[str, Any] = dict(raw_args) if isinstance(raw_args, dict) else {}
                impl = _TOOL_DISPATCH.get(tool_name)
                if impl is None:
                    result_payload: dict[str, Any] = {"error": f"unknown tool: {tool_name}"}
                else:
                    try:
                        result_payload = await impl(session, tool_args)
                    except Exception as exc:  # pragma: no cover — defensive
                        log.exception("assistant.tool.error", tool=tool_name, error=str(exc))
                        result_payload = {"error": f"tool failed: {exc!s}"}
                tool_results_log.append((tool_name, result_payload))
                tool_results_for_msg.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result_payload, default=str),
                    }
                )
            messages.append({"role": "user", "content": tool_results_for_msg})

        # Hit the round cap — return whatever the last assistant text was.
        log.warning("assistant.chat.tool_loop_cap", cap=_MAX_TOOL_ROUNDS)
        last_text = ""
        for m in reversed(messages):
            if m["role"] != "assistant":
                continue
            content = m["content"]
            if not isinstance(content, list):
                continue
            for block in content:
                if getattr(block, "type", None) == "text":
                    last_text = getattr(block, "text", "")
                    break
            break
        return AssistantResponse(
            answer=last_text or "(I reached the tool-call limit without a final answer.)",
            sources=_sources_from_tool_calls(tool_results_log),
            tool_calls=[name for name, _ in tool_results_log],
            model=self._model,
        )


_singleton: AssistantService | None = None


def get_assistant_service() -> AssistantService:
    global _singleton
    if _singleton is None:
        _singleton = AssistantService()
    return _singleton


# Re-export the tool dispatch table so tests can drive tools without an
# LLM round trip.
__all__ = [
    "AssistantError",
    "AssistantNotConfigured",
    "AssistantResponse",
    "AssistantService",
    "AssistantSource",
    "TOOL_DEFS",
    "_TOOL_DISPATCH",
    "get_assistant_service",
]


# Silence "imported but unused" for IncidentStatus (kept for future tool).
_ = IncidentStatus
