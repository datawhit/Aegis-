"""Operator-first Overview endpoint (Sprint 9).

Aggregates the data that backs the "what did Aegis do" landing page.
The shape mirrors the Overview UI's panels:

- overnight_summary: the KPI strip
- trust_score: the Aegis Trust Score panel
- requires_attention: the "what still needs me" row
- top_policies_24h: the "Top Active Policies" sidebar
- risk_snapshot: a single scalar today; trend chart lands in the Risk
  Analytics sprint

Action feed lives in its own endpoint (`/actions/feed`) because the UI
tabs through it independently and we want pagination there.

Trust-score and risk-score formulas are intentionally simple starter
heuristics. They produce a stable, intuitively-correct number from real
state — but the "right" formula needs customer data to calibrate.
Tracked as D-52.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, SessionDep
from app.models.approval import Approval, ApprovalState
from app.models.audit_log import AuditLog
from app.models.incident import Incident, IncidentStatus
from app.models.policy import Policy
from app.models.remediation_action import (
    RemediationAction,
    RemediationActionClass,
    RemediationStatus,
)

router = APIRouter()

# Sprint 10: stabilization set lives on the enum (`is_stabilization`).
# Materialised here as the raw string values for SQL `.in_()` clauses.
_STABILIZATION_ACTION_CLASSES = frozenset(
    c.value for c in RemediationActionClass if c.is_stabilization
)


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------


class OvernightSummary(BaseModel):
    issues_evaluated: int
    resolved_autonomously: int
    stabilized: int
    escalated: int
    analyst_hours_saved: float
    mean_response_time_seconds: float | None
    deltas: dict[str, float]  # vs yesterday %, e.g. {"resolved": 22.0}


class TrustScore(BaseModel):
    score: int  # 0-100
    label: str  # "Excellent" | "Good" | "Fair" | "Poor"
    rollbacks_24h: int
    policy_adherence_pct_7d: float
    rollback_rate_pct_30d: float


class RiskSnapshot(BaseModel):
    score: int  # 0-100 (lower is better)
    label: str  # "Low" | "Medium" | "High" | "Critical"
    delta_pct: float | None  # vs yesterday; null if unknown


class RequiresAttention(BaseModel):
    critical_escalations: int
    pending_reviews: int
    stabilized_systems: int


class TopPolicy(BaseModel):
    policy_id: str | None
    name: str
    actions_count: int


class OverviewResponse(BaseModel):
    generated_at: datetime
    overnight_summary: OvernightSummary
    trust_score: TrustScore
    risk_snapshot: RiskSnapshot
    requires_attention: RequiresAttention
    top_policies_24h: list[TopPolicy]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    session: SessionDep,
    _user: CurrentUserDep,
) -> OverviewResponse:
    now = datetime.now(UTC)
    last_24h = now - timedelta(hours=24)
    last_48h = now - timedelta(hours=48)
    last_7d = now - timedelta(days=7)
    last_30d = now - timedelta(days=30)

    overnight = await _overnight_summary(session, last_24h=last_24h, last_48h=last_48h)
    trust = await _trust_score(session, last_24h=last_24h, last_7d=last_7d, last_30d=last_30d)
    risk = await _risk_snapshot(session, last_24h=last_24h, last_48h=last_48h)
    attention = await _requires_attention(session)
    top_policies = await _top_policies_24h(session, last_24h=last_24h)

    return OverviewResponse(
        generated_at=now,
        overnight_summary=overnight,
        trust_score=trust,
        risk_snapshot=risk,
        requires_attention=attention,
        top_policies_24h=top_policies,
    )


# ---------------------------------------------------------------------------
# Aggregations — each is small + isolated so the formulas are auditable.
# ---------------------------------------------------------------------------


async def _count_actions(
    session: AsyncSession,
    *,
    since: datetime,
    statuses: set[RemediationStatus] | None = None,
    stabilization: bool | None = None,
) -> int:
    stmt = (
        select(func.count())
        .select_from(RemediationAction)
        .where(RemediationAction.created_at >= since)
    )
    if statuses is not None:
        stmt = stmt.where(RemediationAction.status.in_([s.value for s in statuses]))
    if stabilization is True:
        stmt = stmt.where(RemediationAction.action_class.in_(_STABILIZATION_ACTION_CLASSES))
    elif stabilization is False:
        stmt = stmt.where(RemediationAction.action_class.notin_(_STABILIZATION_ACTION_CLASSES))
    return int((await session.execute(stmt)).scalar_one())


async def _overnight_summary(
    session: AsyncSession, *, last_24h: datetime, last_48h: datetime
) -> OvernightSummary:
    resolved = await _count_actions(
        session,
        since=last_24h,
        statuses={RemediationStatus.EXECUTED},
        stabilization=False,
    )
    stabilized = await _count_actions(
        session,
        since=last_24h,
        statuses={RemediationStatus.EXECUTED},
        stabilization=True,
    )
    escalated = await _count_actions(
        session,
        since=last_24h,
        statuses={RemediationStatus.POLICY_ESCALATED},
    )
    issues_evaluated = await _count_actions(session, since=last_24h)

    # Prior window for delta. Window is [last_48h, last_24h).
    prior_resolved = (
        await session.execute(
            select(func.count())
            .select_from(RemediationAction)
            .where(
                RemediationAction.status == RemediationStatus.EXECUTED.value,
                RemediationAction.created_at >= last_48h,
                RemediationAction.created_at < last_24h,
            )
        )
    ).scalar_one()

    def _pct_delta(curr: int, prior: int) -> float:
        if prior == 0:
            return 0.0 if curr == 0 else 100.0
        return round((curr - prior) / prior * 100.0, 1)

    # 15 min saved per autonomous action — placeholder formula (D-52).
    hours_saved = round((resolved + stabilized) * 0.25, 1)

    mrt = await _mean_response_time_seconds(session, since=last_24h)

    return OvernightSummary(
        issues_evaluated=issues_evaluated,
        resolved_autonomously=resolved,
        stabilized=stabilized,
        escalated=escalated,
        analyst_hours_saved=hours_saved,
        mean_response_time_seconds=mrt,
        deltas={"resolved": _pct_delta(resolved, prior_resolved)},
    )


async def _mean_response_time_seconds(session: AsyncSession, *, since: datetime) -> float | None:
    """Average seconds between Incident.created_at and the first
    audit-chain entry that references it.

    Returns None when there are no incidents in the window — keeps the
    UI from showing a misleading zero.
    """
    first_audit = (
        select(
            AuditLog.resource_id.label("incident_id"),
            func.min(AuditLog.created_at).label("first_audit_at"),
        )
        .where(
            AuditLog.resource_type == "incident",
            AuditLog.created_at >= since,
        )
        .group_by(AuditLog.resource_id)
        .subquery()
    )
    stmt = (
        select(
            func.avg(func.extract("epoch", first_audit.c.first_audit_at - Incident.created_at))
        )
        .select_from(first_audit)
        .join(Incident, Incident.id == first_audit.c.incident_id)
    )
    result = (await session.execute(stmt)).scalar()
    return float(result) if result is not None else None


async def _trust_score(
    session: AsyncSession,
    *,
    last_24h: datetime,
    last_7d: datetime,
    last_30d: datetime,
) -> TrustScore:
    rollbacks_24h = await _count_actions(
        session, since=last_24h, statuses={RemediationStatus.ROLLED_BACK}
    )

    # Policy adherence: executed actions that were ALLOWed by policy
    # / all decisioned actions in the window. Denied + escalated drag it
    # down; ALLOW+EXECUTED is the happy path.
    decisioned_in_7d = await _count_actions(
        session,
        since=last_7d,
        statuses={
            RemediationStatus.EXECUTED,
            RemediationStatus.POLICY_ESCALATED,
            RemediationStatus.POLICY_DENIED,
            RemediationStatus.ROLLED_BACK,
        },
    )
    executed_7d = await _count_actions(
        session, since=last_7d, statuses={RemediationStatus.EXECUTED}
    )
    adherence_pct = round(
        executed_7d / decisioned_in_7d * 100.0 if decisioned_in_7d > 0 else 100.0,
        1,
    )

    total_30d = await _count_actions(session, since=last_30d)
    rollbacks_30d = await _count_actions(
        session, since=last_30d, statuses={RemediationStatus.ROLLED_BACK}
    )
    rollback_rate = round(rollbacks_30d / total_30d * 100.0 if total_30d > 0 else 0.0, 1)

    # Score: starter heuristic. Anchored at 100, penalties for rollbacks
    # in the last day (heavy) and the 30-day rollback rate (moderate).
    # Bonus for high recent adherence.
    score = 100
    score -= min(rollbacks_24h * 3, 20)  # cap penalty
    score -= int(rollback_rate * 2)
    score -= int(max(0, 95 - adherence_pct) * 0.5)
    score = max(0, min(100, score))

    if score >= 90:
        label = "Excellent"
    elif score >= 75:
        label = "Good"
    elif score >= 50:
        label = "Fair"
    else:
        label = "Poor"

    return TrustScore(
        score=score,
        label=label,
        rollbacks_24h=rollbacks_24h,
        policy_adherence_pct_7d=adherence_pct,
        rollback_rate_pct_30d=rollback_rate,
    )


async def _risk_snapshot(
    session: AsyncSession, *, last_24h: datetime, last_48h: datetime
) -> RiskSnapshot:
    """Lower-is-better 0-100 score. Starter formula until Sprint 11."""
    open_states = [
        IncidentStatus.OPEN.value,
        IncidentStatus.AWAITING_APPROVAL.value,
        IncidentStatus.REMEDIATING.value,
        IncidentStatus.ESCALATED.value,
    ]

    severity_weight = case(
        {"critical": 12, "high": 5, "medium": 2, "low": 0.5}, value=Incident.severity
    )
    stmt_now = select(func.coalesce(func.sum(severity_weight), 0.0)).where(
        Incident.status.in_(open_states)
    )
    score_now_raw = float((await session.execute(stmt_now)).scalar_one())
    score_now = min(100, int(round(score_now_raw)))

    # Prior risk — closed incidents that were open 24h ago would have
    # contributed; approximate by looking at created_at < last_24h still
    # open OR created in [last_48h, last_24h).
    stmt_prior = (
        select(func.coalesce(func.sum(severity_weight), 0.0))
        .where(Incident.created_at < last_24h)
        .where((Incident.status.in_(open_states)) | (Incident.updated_at >= last_24h))
    )
    score_prior_raw = float((await session.execute(stmt_prior)).scalar_one())
    score_prior = min(100, int(round(score_prior_raw)))

    delta = None
    if score_prior > 0:
        delta = round((score_now - score_prior) / score_prior * 100.0, 1)
    elif score_now > 0:
        delta = 100.0

    if score_now < 30:
        label = "Low"
    elif score_now < 60:
        label = "Medium"
    elif score_now < 85:
        label = "High"
    else:
        label = "Critical"

    _ = last_48h  # consumed indirectly by prior-window comparison
    return RiskSnapshot(score=score_now, label=label, delta_pct=delta)


async def _requires_attention(session: AsyncSession) -> RequiresAttention:
    critical_escalations = (
        await session.execute(
            select(func.count())
            .select_from(Incident)
            .where(
                Incident.status == IncidentStatus.ESCALATED.value,
                Incident.severity.in_(["critical", "high"]),
            )
        )
    ).scalar_one()
    pending_reviews = (
        await session.execute(
            select(func.count())
            .select_from(Approval)
            .where(Approval.state == ApprovalState.PENDING.value)
        )
    ).scalar_one()
    stabilized_systems = (
        await session.execute(
            select(func.count())
            .select_from(RemediationAction)
            .where(
                RemediationAction.status == RemediationStatus.EXECUTED.value,
                RemediationAction.action_class.in_(_STABILIZATION_ACTION_CLASSES),
            )
        )
    ).scalar_one()
    return RequiresAttention(
        critical_escalations=int(critical_escalations),
        pending_reviews=int(pending_reviews),
        stabilized_systems=int(stabilized_systems),
    )


async def _top_policies_24h(session: AsyncSession, *, last_24h: datetime) -> list[TopPolicy]:
    """Top 5 policies by audit-chain `policy.evaluated` activity in the
    last 24h. Source of truth is `audit_logs.payload->>'winning_policy_id'`
    so this works without a schema change.

    Fallback: if no policy evaluations have happened (fresh DB), surface
    the 5 most-recently-updated active policies so the panel always
    renders something.
    """
    import uuid as _uuid

    winning_id_expr = AuditLog.payload["winning_policy_id"].astext

    # Step 1: count by winning_policy_id in the last 24h.
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
            .limit(5)
        )
    ).all()

    if counts_rows:
        # Step 2: resolve names for those ids. Bad/old ids → "(unknown)".
        resolved_ids: list[_uuid.UUID] = []
        for pid, _n in counts_rows:
            try:
                resolved_ids.append(_uuid.UUID(str(pid)))
            except ValueError:
                continue
        names_by_id = {
            str(pid): name
            for pid, name in (
                await session.execute(
                    select(Policy.id, Policy.name).where(Policy.id.in_(resolved_ids))
                )
            ).all()
        }
        return [
            TopPolicy(
                policy_id=str(pid),
                name=names_by_id.get(str(pid), "(unknown policy)"),
                actions_count=int(n),
            )
            for pid, n in counts_rows
        ]

    # Empty-history fallback.
    rows_fallback = (
        await session.execute(
            select(Policy.id, Policy.name)
            .where(Policy.is_active.is_(True))
            .order_by(Policy.updated_at.desc())
            .limit(5)
        )
    ).all()
    return [
        TopPolicy(policy_id=str(pid), name=name, actions_count=0) for pid, name in rows_fallback
    ]
