"""SlackNotifier — Slack Block Kit messages + interactive approval buttons.

Dry-run posture:
  - Default (`AEGIS_SLACK_ENABLED=false`): logs the rendered Block Kit
    payload at INFO and returns success. The end-to-end demo loop is
    visible in logs without a real Slack workspace.
  - Live: posts to `AEGIS_SLACK_WEBHOOK_URL`. Interactive actions are
    handled by `POST /api/v1/slack/interact`, which is signature-verified
    against `AEGIS_SLACK_SIGNING_SECRET`.

The interactive button's `value` carries the approval_id; the receiving
endpoint maps that back to the Approval row and runs the state machine.
"""

from __future__ import annotations

import json

import httpx

from app.config import settings
from app.core.notifications.base import ApprovalNotification, Notifier, Severity
from app.logging import get_logger

log = get_logger("notifications.slack")


_SEVERITY_TO_COLOR = {
    "info": "#5eead4",
    "warning": "#fbbf24",
    "critical": "#f87171",
}


class SlackNotifier(Notifier):
    async def notify(self, *, title: str, body: str, severity: Severity = "info") -> bool:
        payload = {
            "attachments": [
                {
                    "color": _SEVERITY_TO_COLOR.get(severity, "#5eead4"),
                    "blocks": [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": title},
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": body},
                        },
                    ],
                }
            ]
        }
        return await self._post(payload, label="notify")

    async def request_approval(self, approval: ApprovalNotification) -> bool:
        confidence_str = (
            "—" if approval.ai_confidence is None else f"{int(approval.ai_confidence * 100)}%"
        )
        payload = {
            "attachments": [
                {
                    "color": _SEVERITY_TO_COLOR["warning"],
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"Approval requested: {approval.action_class}",
                            },
                        },
                        {
                            "type": "section",
                            "fields": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Blast radius:* {approval.blast_radius}",
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*AI confidence:* {confidence_str}",
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Required role:* {approval.requested_role}",
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Expires:* {approval.expires_at}",
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"*Summary:* {approval.ai_summary}\n\n"
                                    f"*Reasoning:* {approval.ai_reasoning[:1500]}"
                                ),
                            },
                        },
                        {
                            "type": "actions",
                            "block_id": f"aegis_approval:{approval.approval_id}",
                            "elements": [
                                {
                                    "type": "button",
                                    "style": "primary",
                                    "text": {"type": "plain_text", "text": "Approve"},
                                    "value": f"approve:{approval.approval_id}",
                                    "action_id": "aegis_approve",
                                },
                                {
                                    "type": "button",
                                    "style": "danger",
                                    "text": {"type": "plain_text", "text": "Reject"},
                                    "value": f"reject:{approval.approval_id}",
                                    "action_id": "aegis_reject",
                                },
                            ],
                        },
                    ],
                }
            ]
        }
        return await self._post(payload, label="request_approval")

    async def _post(self, payload: dict, *, label: str) -> bool:
        if not settings.slack_enabled:
            log.info(
                "slack.dry_run",
                label=label,
                rendered=json.dumps(payload)[:2048],
            )
            return True
        if not settings.slack_webhook_url:
            log.warning("slack.misconfigured", label=label, reason="webhook_url_missing")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    settings.slack_webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
        except httpx.HTTPError as exc:
            log.error("slack.network_error", label=label, error=str(exc))
            return False

        if r.status_code >= 300:
            log.error(
                "slack.post_failed",
                label=label,
                status=r.status_code,
                body=r.text[:512],
            )
            return False
        return True
