"""POST /slack/interact — Slack interactive component webhook.

Slack signs requests with HMAC-SHA-256 of
  `f"v0:{timestamp}:{raw_body}"`
using the signing secret. We verify, extract the action_id + value, and
route to the approval service.

The user identity carried on the Slack callback is **the Slack user**,
not an Aegis user — we map Slack identity to Aegis user via email match
(Phase 2 trade-off; full SSO mapping ships with Okta in Phase 3).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.config import settings
from app.logging import get_logger
from app.models.user import User
from app.services.approval_service import (
    ApprovalNotFoundError,
    ApprovalNotPendingError,
    get_approval_service,
)

log = get_logger("api.slack")
router = APIRouter()


@router.post("/slack/interact")
async def slack_interact(request: Request, session: SessionDep) -> dict:
    raw = await request.body()
    if not _verify_slack_signature(request, raw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="signature verification failed",
        )

    # Slack posts URL-encoded with a `payload` field whose value is JSON.
    parsed = urllib.parse.parse_qs(raw.decode("utf-8"))
    payload_raw = (parsed.get("payload") or [""])[0]
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="malformed Slack payload",
        ) from exc

    actions = payload.get("actions") or []
    if not actions:
        return {"ok": True, "note": "no actions"}

    action = actions[0]
    value: str = action.get("value", "")
    if ":" not in value:
        return {"ok": False, "note": "unexpected action value"}
    verb, approval_id_str = value.split(":", 1)

    slack_user_email = (payload.get("user") or {}).get("email") or ""
    actor = (
        await session.execute(select(User).where(User.email == slack_user_email.lower()))
    ).scalar_one_or_none()
    if actor is None:
        log.warning("slack.interact.unknown_user", slack_email=slack_user_email)
        return {
            "response_type": "ephemeral",
            "text": (
                "Your Slack identity isn't linked to an Aegis user. "
                "Ask your admin to provision a matching account."
            ),
        }

    try:
        await get_approval_service().decide(
            session,
            approval_id=uuid.UUID(approval_id_str),
            approve=(verb == "approve"),
            actor=actor,
            note=f"via slack: {payload.get('trigger_id', '')[:32]}",
        )
    except ApprovalNotFoundError:
        return {"response_type": "ephemeral", "text": "Approval not found."}
    except ApprovalNotPendingError as exc:
        return {"response_type": "ephemeral", "text": str(exc)}

    await session.commit()
    return {
        "response_type": "in_channel",
        "text": f"Approval {verb}d by {actor.email}.",
    }


def _verify_slack_signature(request: Request, raw_body: bytes) -> bool:
    if not settings.slack_signing_secret:
        # Slack disabled in this env — accept only in non-prod.
        return not settings.is_production
    ts = request.headers.get("X-Slack-Request-Timestamp")
    sig = request.headers.get("X-Slack-Signature")
    if not ts or not sig:
        return False
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    if abs(int(time.time()) - ts_int) > 60 * 5:
        return False
    basestring = f"v0:{ts}:".encode() + raw_body
    expected = (
        "v0="
        + hmac.new(
            settings.slack_signing_secret.encode("utf-8"),
            basestring,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, sig)
