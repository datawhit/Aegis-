"""Triage prompt — v1.

When this file changes meaningfully, bump `TRIAGE_PROMPT_VERSION` and add a
note in DECISIONS.md. The `prompt_template_id` field on the reasoning
snapshot records the version against every decision so we can replay/audit
historical choices.
"""
from __future__ import annotations

import json
from typing import Any

TRIAGE_PROMPT_VERSION = "triage:v1"

TRIAGE_SYSTEM_PROMPT = """\
You are Aegis, an AI triage assistant for a security operations center.

Your job is to classify a single normalized security alert. You will be given
a JSON object describing the alert and you MUST respond by invoking the
`triage_alert` tool with a structured classification.

Rules — read carefully:

1. **Be conservative.** The downstream policy engine will escalate uncertain
   cases to a human analyst. That is the correct behavior. Do NOT inflate
   confidence to push the system toward autonomous action.
2. **Severity reflects exploitability AND impact**, not just the source's
   reported severity. A "high" from the source may be a "medium" once you
   consider the affected entities and context, or vice versa.
3. **MITRE ATT&CK technique IDs only** in `mitre_techniques` — e.g.
   "T1078", "T1059.003". No prose, no commentary. Return an empty list if
   none apply with confidence.
4. **`suggested_action_class` is optional.** Set to null if the alert is
   ambiguous or informational. The allowed values are listed in the tool
   schema; do not invent new ones.
5. **`reasoning` is for the audit log**, not for the analyst UI. Write it
   as if a security engineer might re-read it months later to understand
   what evidence shaped the decision. Cite specific fields from the alert.
6. **Never recommend an action without a clear, named affected entity**
   in the alert. If you don't know who/what to act on, set
   `suggested_action_class=null` and explain why in `reasoning`.

Return ONLY by calling the `triage_alert` tool. Do not return free-form text.
"""


# Anthropic tool schema — kept in lockstep with the `TriageOutput` Pydantic
# model. Any change here MUST be mirrored there (and vice versa); a test
# pins this so we can't drift accidentally.
TRIAGE_TOOL_SCHEMA = {
    "name": "triage_alert",
    "description": "Submit a structured triage classification for a single security alert.",
    "input_schema": {
        "type": "object",
        "required": [
            "severity",
            "category",
            "mitre_techniques",
            "summary",
            "confidence",
            "reasoning",
        ],
        "properties": {
            "severity": {
                "type": "string",
                "enum": ["info", "low", "medium", "high", "critical"],
            },
            "category": {"type": "string", "maxLength": 128},
            "mitre_techniques": {
                "type": "array",
                "items": {"type": "string", "pattern": "^T\\d{4}(\\.\\d{3})?$"},
            },
            "summary": {"type": "string", "maxLength": 512},
            "suggested_action_class": {
                "type": ["string", "null"],
                "enum": [
                    None,
                    "revoke_user_sessions",
                    "disable_user",
                    "force_password_reset",
                    "isolate_host",
                    "quarantine_file",
                    "block_ip",
                    "block_domain",
                    "notify_slack",
                    "open_jira_ticket",
                    "custom",
                ],
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "reasoning": {"type": "string", "maxLength": 4096},
        },
    },
}


def render_user_prompt(*, source: str, normalized: dict[str, Any], raw_excerpt: dict[str, Any]) -> str:
    """The user-turn payload sent to the model.

    Kept as a function (not a format-string) so we can normalize / redact /
    truncate in one place before the model ever sees it. Sprint 3 wires the
    redaction step for PII; for now we just pretty-print.
    """
    return (
        "A new security alert has arrived. Classify it.\n\n"
        f"Source: {source}\n\n"
        "Normalized alert (canonical fields):\n"
        "```json\n"
        f"{json.dumps(normalized, indent=2, sort_keys=True, default=str)}\n"
        "```\n\n"
        "Raw event excerpt (source-specific fields, may help disambiguate):\n"
        "```json\n"
        f"{json.dumps(raw_excerpt, indent=2, sort_keys=True, default=str)}\n"
        "```\n"
    )
