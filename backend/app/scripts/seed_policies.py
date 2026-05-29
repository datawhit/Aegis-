"""Seed the default policy set for local development + demo.

Idempotent: re-running upserts by name. Refuses to run outside `local`/`ci`.

The seed encodes the **Sprint 2 default posture** (ADR-011): opt-in
autonomous execution per action class. The deny-all baseline catches
anything unmodeled; specific ALLOW rules at higher priority enable
demo flows.
"""

from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select

from app.config import settings
from app.db import session_scope
from app.logging import configure_logging, get_logger
from app.models.policy import Policy, PolicyEffect

DEFAULT_POLICIES = [
    {
        "name": "baseline-deny-all",
        "priority": 1,
        "effect": PolicyEffect.ESCALATE,
        "match": {"any": True},
        "constraints": {"requires_approval": True},
        "description": (
            "Baseline catch-all. Anything not matched by a more specific "
            "policy escalates to a human."
        ),
    },
    {
        "name": "allow-revoke-sessions-for-impossible-travel",
        "priority": 100,
        "effect": PolicyEffect.ALLOW,
        "match": {
            "and": [
                {"eq": {"action_class": "revoke_user_sessions"}},
                {"in": {"incident_severity": ["medium", "high"]}},
                {"gte": {"ai_confidence": 0.85}},
                {"lte": {"blast_radius": 5}},
            ]
        },
        "constraints": {
            # Even an ALLOW can require approval — this is the
            # "shadow-mode-by-action-class" lever (Q13). Operators flip
            # this false for action classes they're ready to autonomize.
            "requires_approval": True,
            "max_blast_radius": 5,
            "min_ai_confidence": 0.85,
        },
        "description": (
            "Permit session revocation for medium/high-severity account "
            "compromise alerts with high model confidence and bounded "
            "blast radius. Still requires approval in Sprint 2."
        ),
    },
    {
        "name": "deny-disable-user-without-approval",
        "priority": 200,
        "effect": PolicyEffect.DENY,
        "match": {
            "and": [
                {"eq": {"action_class": "disable_user"}},
                {"lte": {"ai_confidence": 0.95}},
            ]
        },
        "constraints": {},
        "description": (
            "Disable-user is permanent-ish (forces a manual re-enable). "
            "Confidence below 0.95 is an outright DENY — the AI must be "
            "near-certain or the action is off the table autonomously."
        ),
    },
]


async def main() -> int:
    configure_logging()
    log = get_logger("seed.policies")

    if settings.env not in {"local", "ci"}:
        log.error("seed.policies.refused", env=settings.env)
        print(f"refusing to seed policies in env={settings.env!r}", file=sys.stderr)
        return 2

    async with session_scope() as session:
        for spec in DEFAULT_POLICIES:
            existing = (
                await session.execute(select(Policy).where(Policy.name == spec["name"]))
            ).scalar_one_or_none()
            if existing is None:
                policy = Policy(
                    id=uuid.uuid4(),
                    name=spec["name"],
                    description=spec["description"],
                    priority=spec["priority"],
                    effect=spec["effect"],
                    match=spec["match"],
                    constraints=spec["constraints"],
                    is_active=True,
                )
                session.add(policy)
                log.info("policy.seed.created", name=spec["name"])
            else:
                for attr in ("priority", "effect", "match", "constraints", "description"):
                    setattr(existing, attr, spec[attr])
                existing.is_active = True
                log.info("policy.seed.updated", name=spec["name"])

    print(f"  seeded {len(DEFAULT_POLICIES)} policies")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
