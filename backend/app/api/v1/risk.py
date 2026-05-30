"""Risk Analytics endpoint (Sprint 11).

Powers the Risk Analytics page — the Pillar 3 surface from ADR-022's
operator-first reframe. The endpoint aggregates:

- `summary`:        current vs prior risk score scalar + delta
- `score_history`:  time-bucketed risk score samples for the trend
                    chart. Computed on-the-fly from incident state at
                    each bucket boundary; persisted hourly snapshots
                    land when traffic justifies a new table (D-66).
- `categories`:     risk breakdown by category — derived from the
                    action_class → category mapping the actions feed
                    already uses. Each row carries current count,
                    prior count, and a % delta.
- `top_reducing`:   policies that drove the most autonomous actions
                    in the window — operator-friendly framing of
                    "which rules are doing the work."

All formulas are starter heuristics (D-52 same as the overview's
trust + risk scalars). Calibration against real customer data is
Sprint 12+.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, SessionDep
from app.models.audit_log import AuditLog
from app.models.incident import Incident, IncidentStatus
from app.models.policy import Policy
from app.models.remediation_action import (
    RemediationAction,
    RemediationActionClass,
    RemediationStatus,
)

router = APIRouter()


Window = Literal["24h", "7d", "30d"]


# Categories mirror the actions feed badges. The action_class → category
# table lives here too because the risk view groups by category, not by
# class. If a new action class lands without a category, it falls back to
# OTHER.
_ACTION_CLASS_TO_CATEGORY: dict[str, str] = {
    "revoke_user_sessions": "Identity",
    "force_password_reset": "Identity",
    "disable_user": "Identity",
    "isolate_host": "Endpoint",
    "quarantine_file": "Endpoint",
    "block_ip": "Network",
    "block_domain": "Network",
    "notify_slack": "Notification",
    "open_jira_ticket": "Notification",
    "custom": "Other",
}

# Severity → risk weight (matches overview._risk_snapshot for consistency).
_SEVERITY_WEIGHT: dict[str, float] = {
    "critical": 12.0,
    "high": 5.0,
    "medium": 2.0,
    "low": 0.5,
    "info": 0.1,
}

_OPEN_INCIDENT_STATES = (
    IncidentStatus.OPEN.value,
    IncidentStatus.AWAITING_APPROVAL.value,
    IncidentStatus.REMEDIATING.value,
    IncidentStatus.ESCALATED.value,
)


# ─────────────────────────────────────────────────────────────────────
# Response shapes
# ─────────────────────────────────────────────────────────────────────


class RiskSummary(BaseModel):
    window: Window
    current_score: int  # 0-100, lower is better
    prior_score: int
    delta_pct: float | None  # null when prior was zero
    label: str  # "Low" | "Medium" | "High" | "Critical"


class RiskHistoryPoint(BaseModel):
    t: datetime
    score: int


class RiskCategoryRow(BaseModel):
    name: str
    current_actions: int
    prior_actions: int
    delta_pct: float | None  # null when prior was zero
    trend: list[int]  # tiny sparkline samples (length matches score_history)


class TopReducingPolicy(BaseModel):
    policy_id: str
    name: str
    actions_count: int
    est_risk_reduced: int  # sum of severity weights of the affected incidents


class RiskAnalyticsResponse(BaseModel):
    generated_at: datetime
    summary: RiskSummary
    score_history: list[RiskHistoryPoint]
    categories: list[RiskCategoryRow]
    top_reducing: list[TopReducingPolicy]


# ─────────────────────────────────────────────────────────────────────
# Sprint 12: per-category drill-down (Risk Explorer page)
# ─────────────────────────────────────────────────────────────────────


class CategoryActionRow(BaseModel):
    action_id: str
    action_class: str
    incident_id: str
    incident_title: str
    incident_severity: str
    outcome: str  # "resolved" | "stabilized" | "escalated"
    ai_confidence: float | None
    created_at: datetime


class CategoryDrilldownResponse(BaseModel):
    category: str
    window: Window
    summary: dict  # {actions_count, prior_count, delta_pct, est_risk_reduced}
    trend: list[int]  # bucketed action counts
    recent_actions: list[CategoryActionRow]
    contributing_classes: list[dict]  # [{action_class, count}, ...]


# ─────────────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────────────


@router.get("/risk/analytics", response_model=RiskAnalyticsResponse)
async def get_risk_analytics(
    session: SessionDep,
    _user: CurrentUserDep,
    window: Window = Query("7d"),
) -> RiskAnalyticsResponse:
    now = datetime.now(UTC)
    window_start, prior_start, bucket = _window_bounds(window, now)

    score_history = await _score_history(session, start=window_start, end=now, bucket=bucket)
    prior_history = await _score_history(
        session, start=prior_start, end=window_start, bucket=bucket
    )

    summary = _summary(window, score_history, prior_history)
    categories = await _categories(
        session,
        window_start=window_start,
        prior_start=prior_start,
        sample_count=len(score_history),
    )
    top_reducing = await _top_reducing(session, window_start=window_start)

    return RiskAnalyticsResponse(
        generated_at=now,
        summary=summary,
        score_history=score_history,
        categories=categories,
        top_reducing=top_reducing,
    )


# ─────────────────────────────────────────────────────────────────────
# Aggregations
# ─────────────────────────────────────────────────────────────────────


def _window_bounds(window: Window, now: datetime) -> tuple[datetime, datetime, timedelta]:
    """Return (window_start, prior_window_start, bucket_size)."""
    if window == "24h":
        size = timedelta(hours=24)
        bucket = timedelta(hours=2)
    elif window == "7d":
        size = timedelta(days=7)
        bucket = timedelta(hours=12)
    else:  # 30d
        size = timedelta(days=30)
        bucket = timedelta(days=1)
    return now - size, now - 2 * size, bucket


async def _score_history(
    session: AsyncSession,
    *,
    start: datetime,
    end: datetime,
    bucket: timedelta,
) -> list[RiskHistoryPoint]:
    """Sample the risk score at each bucket boundary across [start, end].

    For each bucket boundary T we compute the risk score as if "now" were
    T: sum of severity weights for incidents that were created at or
    before T and not yet closed by T. Approximate but cheap and runs
    against the existing schema.
    """
    if bucket.total_seconds() <= 0:
        return []
    samples: list[RiskHistoryPoint] = []
    t = start
    while t <= end:
        samples.append(RiskHistoryPoint(t=t, score=await _score_at(session, t)))
        t = t + bucket
    return samples


async def _score_at(session: AsyncSession, t: datetime) -> int:
    """Risk score that *would* have been reported at moment t."""
    # Use the explicit-tuple form of `case` (each WHEN is a condition).
    # The `case(dict, value=col)` shorthand has been observed to compile
    # to a different match path under some SQLAlchemy/asyncpg combos —
    # explicit conditions are unambiguous.
    severity_weight = case(
        *[(Incident.severity == sev, weight) for sev, weight in _SEVERITY_WEIGHT.items()],
        else_=0.0,
    )
    # An incident counts toward risk at time t if it was created at or
    # before t AND not closed/resolved by t (updated_at ≥ t OR currently
    # still open). The second clause keeps still-open incidents in scope
    # regardless of how stale updated_at is.
    closed_states = (
        IncidentStatus.CLOSED_RESOLVED.value,
        IncidentStatus.CLOSED_FALSE_POSITIVE.value,
        IncidentStatus.CONTAINED.value,
    )
    stmt = (
        select(func.coalesce(func.sum(severity_weight), 0.0))
        .where(Incident.created_at <= t)
        .where(
            or_(
                Incident.status.notin_(closed_states),
                Incident.updated_at >= t,
            )
        )
    )
    raw = float((await session.execute(stmt)).scalar_one())
    return min(100, int(round(raw)))


def _summary(
    window: Window,
    current: list[RiskHistoryPoint],
    prior: list[RiskHistoryPoint],
) -> RiskSummary:
    current_score = current[-1].score if current else 0
    prior_score = prior[-1].score if prior else 0
    delta: float | None
    if prior_score == 0:
        delta = None if current_score == 0 else 100.0
    else:
        delta = round((current_score - prior_score) / prior_score * 100.0, 1)

    if current_score < 30:
        label = "Low"
    elif current_score < 60:
        label = "Medium"
    elif current_score < 85:
        label = "High"
    else:
        label = "Critical"

    return RiskSummary(
        window=window,
        current_score=current_score,
        prior_score=prior_score,
        delta_pct=delta,
        label=label,
    )


async def _categories(
    session: AsyncSession,
    *,
    window_start: datetime,
    prior_start: datetime,
    sample_count: int,
) -> list[RiskCategoryRow]:
    """For each category, count actions in [window_start, now] and the
    prior window [prior_start, window_start]. Build a small sparkline by
    bucketing within the current window.
    """
    # All actions in current + prior window in one round trip.
    stmt = (
        select(
            RemediationAction.action_class,
            RemediationAction.created_at,
            (RemediationAction.created_at < window_start).label("is_prior"),
        )
        .where(RemediationAction.created_at >= prior_start)
        .where(
            RemediationAction.status.in_(
                [
                    RemediationStatus.EXECUTED.value,
                    RemediationStatus.POLICY_ESCALATED.value,
                ]
            )
        )
    )
    rows = (await session.execute(stmt)).all()

    current_by_cat: dict[str, list[datetime]] = {}
    prior_by_cat: dict[str, int] = {}
    for action_class, created_at, is_prior in rows:
        ac = action_class.value if hasattr(action_class, "value") else str(action_class)
        category = _ACTION_CLASS_TO_CATEGORY.get(ac, "Other")
        if is_prior:
            prior_by_cat[category] = prior_by_cat.get(category, 0) + 1
        else:
            current_by_cat.setdefault(category, []).append(created_at)

    # Build sparklines bucketed evenly across the current window. We use
    # `sample_count` buckets to align with the trend chart's x-axis.
    sample_count = max(1, sample_count)
    bucket_size = (datetime.now(UTC) - window_start) / sample_count

    out: list[RiskCategoryRow] = []
    seen_cats = set(current_by_cat) | set(prior_by_cat)
    for cat in sorted(seen_cats):
        timestamps = current_by_cat.get(cat, [])
        trend = [0] * sample_count
        for ts in timestamps:
            idx = int((ts - window_start) / bucket_size) if bucket_size else 0
            idx = max(0, min(sample_count - 1, idx))
            trend[idx] += 1
        current_count = len(timestamps)
        prior_count = prior_by_cat.get(cat, 0)
        delta: float | None
        if prior_count == 0:
            delta = None if current_count == 0 else 100.0
        else:
            delta = round((current_count - prior_count) / prior_count * 100.0, 1)
        out.append(
            RiskCategoryRow(
                name=cat,
                current_actions=current_count,
                prior_actions=prior_count,
                delta_pct=delta,
                trend=trend,
            )
        )
    return out


async def _top_reducing(
    session: AsyncSession, *, window_start: datetime, limit: int = 5
) -> list[TopReducingPolicy]:
    """Top policies by action count + summed-severity risk reduction.

    Source of truth is the `policy.evaluated` audit-chain entries whose
    `winning_policy_id` points at a policy that drove an action toward
    resolution (RemediationStatus.EXECUTED). We join those entries with
    the originating incident to weigh by severity.
    """
    winning_id_expr = AuditLog.payload["winning_policy_id"].astext
    stmt = (
        select(
            winning_id_expr.label("policy_id"),
            func.count(RemediationAction.id).label("actions_count"),
            func.coalesce(
                func.sum(
                    case(
                        *[
                            (Incident.severity == sev, weight)
                            for sev, weight in _SEVERITY_WEIGHT.items()
                        ],
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("est_risk_reduced"),
        )
        .select_from(AuditLog)
        .join(
            RemediationAction,
            and_(
                AuditLog.resource_type == "remediation_action",
                RemediationAction.id == AuditLog.resource_id,
            ),
        )
        .join(Incident, Incident.id == RemediationAction.incident_id)
        .where(
            AuditLog.action == "policy.evaluated",
            AuditLog.created_at >= window_start,
            winning_id_expr.isnot(None),
            RemediationAction.status == RemediationStatus.EXECUTED.value,
        )
        .group_by(winning_id_expr)
        .order_by(func.count(RemediationAction.id).desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return []

    # Resolve names via a second query.
    import uuid as _uuid

    resolved_ids: list[_uuid.UUID] = []
    for pid, _n, _r in rows:
        try:
            resolved_ids.append(_uuid.UUID(str(pid)))
        except (TypeError, ValueError):
            continue
    names_by_id = {
        str(pid): name
        for pid, name in (
            await session.execute(select(Policy.id, Policy.name).where(Policy.id.in_(resolved_ids)))
        ).all()
    }
    return [
        TopReducingPolicy(
            policy_id=str(pid),
            name=names_by_id.get(str(pid), "(unknown policy)"),
            actions_count=int(n),
            est_risk_reduced=int(round(float(r))),
        )
        for pid, n, r in rows
    ]


# ─────────────────────────────────────────────────────────────────────
# Sprint 12: per-category drill-down (/risk/category/{name})
# ─────────────────────────────────────────────────────────────────────


@router.get("/risk/category/{category}", response_model=CategoryDrilldownResponse)
async def get_category_drilldown(
    category: str,
    session: SessionDep,
    _user: CurrentUserDep,
    window: Window = Query("7d"),
) -> CategoryDrilldownResponse:
    """Drill-down view for one risk category (Identity / Endpoint / etc).

    Returns the actions, contributing action classes, and bucketed trend
    scoped to the category over the requested window.
    """
    classes_in_category = [ac for ac, cat in _ACTION_CLASS_TO_CATEGORY.items() if cat == category]
    now = datetime.now(UTC)
    window_start, prior_start, bucket = _window_bounds(window, now)
    sample_count = int((now - window_start) / bucket) + 1

    if not classes_in_category:
        return CategoryDrilldownResponse(
            category=category,
            window=window,
            summary={
                "actions_count": 0,
                "prior_count": 0,
                "delta_pct": None,
                "est_risk_reduced": 0,
            },
            trend=[0] * sample_count,
            recent_actions=[],
            contributing_classes=[],
        )

    # All actions in current + prior window for this category.
    stmt = (
        select(RemediationAction, Incident)
        .join(Incident, Incident.id == RemediationAction.incident_id)
        .where(
            RemediationAction.action_class.in_(classes_in_category),
            RemediationAction.created_at >= prior_start,
            RemediationAction.status.in_(
                [
                    RemediationStatus.EXECUTED.value,
                    RemediationStatus.POLICY_ESCALATED.value,
                ]
            ),
        )
        .order_by(RemediationAction.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()

    current_actions: list[tuple[RemediationAction, Incident]] = []
    prior_actions_count = 0
    contributing: dict[str, int] = {}
    trend = [0] * sample_count
    bucket_size = (now - window_start) / sample_count if sample_count else bucket

    for action, incident in rows:
        ac = (
            action.action_class.value
            if hasattr(action.action_class, "value")
            else str(action.action_class)
        )
        if action.created_at < window_start:
            prior_actions_count += 1
            continue
        current_actions.append((action, incident))
        contributing[ac] = contributing.get(ac, 0) + 1
        if bucket_size.total_seconds() > 0:
            idx = int((action.created_at - window_start) / bucket_size)
            idx = max(0, min(sample_count - 1, idx))
            trend[idx] += 1

    current_count = len(current_actions)
    if prior_actions_count == 0:
        delta_pct: float | None = None if current_count == 0 else 100.0
    else:
        delta_pct = round((current_count - prior_actions_count) / prior_actions_count * 100.0, 1)

    # est_risk_reduced: sum of severity weights for the originating
    # incidents of EXECUTED actions in this window.
    est_risk_reduced = sum(
        _SEVERITY_WEIGHT.get(
            incident.severity.value if hasattr(incident.severity, "value") else "info",
            0.0,
        )
        for action, incident in current_actions
        if (action.status.value if hasattr(action.status, "value") else "")
        == RemediationStatus.EXECUTED.value
    )

    recent = [
        CategoryActionRow(
            action_id=str(action.id),
            action_class=(
                action.action_class.value
                if hasattr(action.action_class, "value")
                else str(action.action_class)
            ),
            incident_id=str(incident.id),
            incident_title=incident.title,
            incident_severity=(
                incident.severity.value
                if hasattr(incident.severity, "value")
                else str(incident.severity)
            ),
            outcome=_outcome_for(action),
            ai_confidence=action.ai_confidence,
            created_at=action.created_at,
        )
        for action, incident in current_actions[:25]
    ]

    contributing_list = [
        {"action_class": ac, "count": n}
        for ac, n in sorted(contributing.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return CategoryDrilldownResponse(
        category=category,
        window=window,
        summary={
            "actions_count": current_count,
            "prior_count": prior_actions_count,
            "delta_pct": delta_pct,
            "est_risk_reduced": int(round(est_risk_reduced)),
        },
        trend=trend,
        recent_actions=recent,
        contributing_classes=contributing_list,
    )


def _outcome_for(action: RemediationAction) -> str:
    status = action.status.value if hasattr(action.status, "value") else str(action.status)
    if status == RemediationStatus.POLICY_ESCALATED.value:
        return "escalated"
    if status == RemediationStatus.EXECUTED.value:
        return "stabilized" if action.action_class.is_stabilization else "resolved"
    return status


# Silence "imported but unused" — RemediationActionClass is referenced
# only via the mapping table above (string keys).
_: Iterable[object] = (RemediationActionClass, _OPEN_INCIDENT_STATES)
