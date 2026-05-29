"""Seed a default admin user for local development.

Idempotent: re-running just updates the password to the env default.

NEVER run this against a non-local environment. The check is enforced in
code; do not weaken it.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select

from app.config import settings
from app.core.identity.local_jwt import hash_password
from app.db import session_scope
from app.logging import configure_logging, get_logger
from app.models.user import AuthProvider, User, UserRole

DEV_ADMIN_EMAIL = os.getenv("AEGIS_DEV_ADMIN_EMAIL", "admin@aegis.local")
DEV_ADMIN_PASSWORD = os.getenv("AEGIS_DEV_ADMIN_PASSWORD", "aegis-dev-admin")


async def main() -> int:
    configure_logging()
    log = get_logger("seed")

    if settings.env not in {"local", "ci"}:
        log.error("seed.refused", env=settings.env)
        print(f"refusing to seed in env={settings.env!r}", file=sys.stderr)
        return 2

    async with session_scope() as session:
        existing = (
            await session.execute(select(User).where(User.email == DEV_ADMIN_EMAIL))
        ).scalar_one_or_none()
        if existing is None:
            user = User(
                email=DEV_ADMIN_EMAIL,
                display_name="Dev Admin",
                hashed_password=hash_password(DEV_ADMIN_PASSWORD),
                role=UserRole.ADMIN,
                auth_provider=AuthProvider.LOCAL,
                is_active=True,
            )
            session.add(user)
            log.info("seed.admin_created", email=DEV_ADMIN_EMAIL)
        else:
            existing.hashed_password = hash_password(DEV_ADMIN_PASSWORD)
            existing.role = UserRole.ADMIN
            existing.is_active = True
            log.info("seed.admin_updated", email=DEV_ADMIN_EMAIL)

    print(f"  email:    {DEV_ADMIN_EMAIL}")
    print(f"  password: {DEV_ADMIN_PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
