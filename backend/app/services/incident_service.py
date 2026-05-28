"""Incident orchestration: alert → triage → incident → proposed remediation → policy eval.

This is the spine of Sprint 1. The Celery triage task calls
`handle_new_alert()` which:

  1. Triages the alert via the `TriageService` (AI provider) — reasoning
     snapshot is persisted BEFORE any downstream decision.
  2. Correlates the alert into an existing open incident (sliding window
     on `correlation_key`) OR creates a new one.
  3. Builds a proposed `RemediationAction` (if the AI suggested one) with
     a rollback plan derived from the action class.
  4. Runs it through the `PolicyEngine` — which, in Sprint 1, always
     returns ESCALATE (ADR-005 + stub).
  5. Writes audit chain entries at each step.

Everything happens in a single DB transaction — either the whole pipeline
lands consistently, or nothing does.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.ai.base import TriageRequest
from app.core.ai.triage import TriageDecision, TriageService, get_triage_service
from app.core.audit import Actor, get_audit_logger
from app.core.policy import (
    PolicyEffect,
    PolicyEngine,
    PolicyEvalRequest,
    get_policy_engine,
)
from app.logging import get_logger
from app.models.alert import Alert, AlertSeverity, AlertStatus
from app.models.incident import Incident, IncidentStatus
from app.models.remediation_action import (
    RemediationAction,
    RemediationActionClass,
    RemediationStatus,
)

log = get_logger("services.incident")

# Statuses that count as "open enough" to correlate new alerts into.
_OPEN_INCIDENT_STATUSES = (
    IncidentStatus.OPEN,
    IncidentStatus.AWAITING_APPROVAL,
    IncidentStatus.REMEDIATING,
    IncidentStatus.ESCALATED,
)


@dataclass
class IncidentHandlingResult:
    incident_id: uuid.UUID
    triage_decision: TriageDecision
    remediation_action_id: uuid.UUID | None
    policy_effect: PolicyEffect
    is_new_incident: bool


class IncidentService:
    def __init__(
        self,
        *,
        triage_service: TriageService,
        policy_engine: PolicyEngine,
    ) -> None:
        self._triage = triage_service
        self._policy = policy_engine
        self._audit = get_audit_logger()

    async def handle_new_alert(
        self,
        session: AsyncSession,
        alert: Alert,
    ) -> IncidentHandlingResult:
        # --- 1) Triage. Persist reasoning snapshot first. -------------------
        triage_request = TriageRequest(
            alert_id=alert.id,
            source=alert.source,
            normalized=alert.normalized,
            raw_event_excerpt=alert.normalized.get("raw_event_excerpt", {}),
        )
        decision = await self._triage.triage(session, triage_request)

        # --- 2) Correlate or create incident --------------------------------
        incident, is_new = await self._correlate_or_create(
            session, alert=alert, decision=decision
        )
        # Backfill the reasoning snapshot's incident_id now that we have one.
        # We do this directly with the snapshot_id from the decision.
        await session.execute(
            _set_reasoning_incident_id(decision.reasoning_snapshot_id, incident.id)
        )

        alert.incident_id = incident.id
        alert.status = AlertStatus.LINKED

        await self._audit.record(
            session,
            actor=Actor.ai(label="aegis.triage"),
            action="incident.created" if is_new else "incident.alert_linked",
            resource_type="incident",
            resource_id=incident.id,
            payload={
                "alert_id": str(alert.id),
                "severity": decision.output.severity.value,
                "category": decision.output.category,
                "ai_confidence": decision.output.confidence,
                "mitre_techniques": decision.output.mitre_techniques,
                "ai_failed": decision.ai_failed,
            },
            reasoning_snapshot_id=decision.reasoning_snapshot_id,
        )

        # --- 3) Build proposed remediation (if AI suggested one) ------------
        proposed: RemediationAction | None = None
        if (
            decision.output.suggested_action_class
            and not decision.ai_failed
        ):
            proposed = await self._propose_remediation(
                session,
                incident=incident,
                action_class_value=decision.output.suggested_action_class,
                ai_confidence=decision.output.confidence,
                normalized=alert.normalized,
            )
            await self._audit.record(
                session,
                actor=Actor.ai(label="aegis.triage"),
                action="remediation.proposed",
                resource_type="remediation_action",
                resource_id=proposed.id,
                payload={
                    "incident_id": str(incident.id),
                    "action_class": proposed.action_class.value,
                    "blast_radius": proposed.blast_radius,
                    "ai_confidence": proposed.ai_confidence,
                    "has_rollback_plan": proposed.rollback_plan is not None,
                },
                reasoning_snapshot_id=decision.reasoning_snapshot_id,
            )

        # --- 4) Policy eval (Sprint 1: stub returns ESCALATE) --------------
        if proposed is not None:
            policy_decision = await self._policy.evaluate(
                session,
                PolicyEvalRequest(
                    action_class=proposed.action_class.value,
                    parameters=proposed.parameters,
                    blast_radius=proposed.blast_radius,
                    ai_confidence=proposed.ai_confidence,
                    incident_severity=incident.severity.value,
                    has_rollback_plan=proposed.rollback_plan is not None,
                ),
            )
            proposed.status = _map_policy_to_remediation_status(policy_decision.effect)
            incident.status = (
                IncidentStatus.AWAITING_APPROVAL
                if policy_decision.effect is PolicyEffect.ESCALATE
                else incident.status
            )

            await self._audit.record(
                session,
                actor=Actor.system(label="policy.engine"),
                action="policy.evaluated",
                resource_type="remediation_action",
                resource_id=proposed.id,
                payload={
                    "effect": policy_decision.effect.value,
                    "matched_policy_ids": policy_decision.matched_policy_ids,
                    "reasons": policy_decision.reasons,
                },
            )
            effect = policy_decision.effect
        else:
            # No proposal → the incident itself is the escalation surface.
            incident.status = IncidentStatus.ESCALATED
            effect = PolicyEffect.ESCALATE

        log.info(
            "incident.handled",
            incident_id=str(incident.id),
            alert_id=str(alert.id),
            is_new=is_new,
            policy_effect=effect.value,
            remediation_proposed=proposed is not None,
        )

        return IncidentHandlingResult(
            incident_id=incident.id,
            triage_decision=decision,
            remediation_action_id=proposed.id if proposed else None,
            policy_effect=effect,
            is_new_incident=is_new,
        )

    # ---------------------------------------------------------------- helpers
    async def _correlate_or_create(
        self,
        session: AsyncSession,
        *,
        alert: Alert,
        decision: TriageDecision,
    ) -> tuple[Incident, bool]:
        # If the alert has no correlation_key, no correlation possible —
        # always a new incident.
        if alert.correlation_key:
            window = datetime.now(UTC) - timedelta(
                seconds=settings.incident_correlation_window_seconds
            )
            result = await session.execute(
                select(Incident)
                .join(Alert, Alert.incident_id == Incident.id)
                .where(
                    Alert.correlation_key == alert.correlation_key,
                    Incident.status.in_(_OPEN_INCIDENT_STATUSES),
                    Incident.created_at >= window,
                )
                .order_by(Incident.created_at.desc())
                .limit(1)
            )
            existing = result.scalars().first()
            if existing is not None:
                return existing, False

        # Promote the AI's severity to the incident's severity.
        incident = Incident(
            title=decision.output.summary[:512],
            summary=decision.output.reasoning[:4096],
            severity=decision.output.severity,
            status=IncidentStatus.OPEN,
            ai_confidence=decision.output.confidence,
            mitre_techniques=list(decision.output.mitre_techniques),
            affected_entities=alert.normalized.get("affected_entities", {}),
        )
        session.add(incident)
        await session.flush()
        return incident, True

    async def _propose_remediation(
        self,
        session: AsyncSession,
        *,
        incident: Incident,
        action_class_value: str,
        ai_confidence: float,
        normalized: dict,
    ) -> RemediationAction:
        try:
            action_class = RemediationActionClass(action_class_value)
        except ValueError:
            action_class = RemediationActionClass.CUSTOM

        params, blast_radius = _params_and_blast_radius(action_class, normalized)
        rollback = _default_rollback_plan(action_class, params)

        action = RemediationAction(
            incident_id=incident.id,
            action_class=action_class,
            status=RemediationStatus.PROPOSED,
            parameters=params,
            rollback_plan=rollback,
            blast_radius=blast_radius,
            ai_confidence=ai_confidence,
            idempotency_key=f"propose:{incident.id}:{action_class.value}",
        )
        session.add(action)
        await session.flush()
        return action


def _map_policy_to_remediation_status(effect: PolicyEffect) -> RemediationStatus:
    match effect:
        case PolicyEffect.ALLOW:
            return RemediationStatus.POLICY_ALLOWED
        case PolicyEffect.ESCALATE:
            return RemediationStatus.POLICY_ESCALATED
        case PolicyEffect.DENY:
            return RemediationStatus.POLICY_DENIED


def _params_and_blast_radius(
    action_class: RemediationActionClass, normalized: dict
) -> tuple[dict, int]:
    """Map AI-suggested action_class + normalized alert → action parameters.

    Phase 1 keeps this trivial. The real mapping (with target validation,
    multi-entity expansion, blast-radius computation across an org graph)
    lands when we add an Identity Graph in Phase 3.
    """
    entities = normalized.get("affected_entities", {}) or {}
    match action_class:
        case (
            RemediationActionClass.REVOKE_USER_SESSIONS
            | RemediationActionClass.DISABLE_USER
            | RemediationActionClass.FORCE_PASSWORD_RESET
        ):
            users = entities.get("users") or []
            return {"users": users}, max(1, len(users))
        case RemediationActionClass.ISOLATE_HOST | RemediationActionClass.QUARANTINE_FILE:
            devices = entities.get("devices") or []
            files = entities.get("files") or []
            payload = {"devices": devices, "files": files}
            return payload, max(1, len(devices) + len(files))
        case RemediationActionClass.BLOCK_IP:
            ips = entities.get("ips") or []
            return {"ips": ips}, max(1, len(ips))
        case RemediationActionClass.BLOCK_DOMAIN:
            domains = (normalized.get("indicators") or {}).get("domains") or []
            return {"domains": domains}, max(1, len(domains))
        case _:
            return {"raw": entities}, 1


def _default_rollback_plan(
    action_class: RemediationActionClass, params: dict
) -> dict | None:
    """Declare the inverse for every action class.

    By ADR-005, an action without a rollback plan cannot be ALLOW'd by the
    policy engine. Defining defaults here makes the invariant easy to
    satisfy without ad-hoc reasoning at call sites.
    """
    inverse = {
        RemediationActionClass.REVOKE_USER_SESSIONS: None,  # cannot un-revoke
        RemediationActionClass.DISABLE_USER: "enable_user",
        RemediationActionClass.FORCE_PASSWORD_RESET: None,  # cannot un-reset
        RemediationActionClass.ISOLATE_HOST: "release_host",
        RemediationActionClass.QUARANTINE_FILE: "restore_file",
        RemediationActionClass.BLOCK_IP: "unblock_ip",
        RemediationActionClass.BLOCK_DOMAIN: "unblock_domain",
        RemediationActionClass.NOTIFY_SLACK: None,
        RemediationActionClass.OPEN_JIRA_TICKET: "close_jira_ticket",
        RemediationActionClass.CUSTOM: None,
    }
    inv = inverse.get(action_class)
    if inv is None:
        return None
    return {"action_class": inv, "parameters": params}


def _set_reasoning_incident_id(snapshot_id: uuid.UUID, incident_id: uuid.UUID):
    # Small helper used by `handle_new_alert` — keeps the SQL out of the
    # main flow for readability.
    from sqlalchemy import update

    from app.models.ai_reasoning import AIReasoningSnapshot

    return (
        update(AIReasoningSnapshot)
        .where(AIReasoningSnapshot.id == snapshot_id)
        .values(incident_id=incident_id)
    )


_singleton: IncidentService | None = None


def get_incident_service() -> IncidentService:
    global _singleton
    if _singleton is None:
        _singleton = IncidentService(
            triage_service=get_triage_service(),
            policy_engine=get_policy_engine(),
        )
    return _singleton
