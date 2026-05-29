"""Microsoft Graph execution connector.

Phase 2 scope:
  - `revoke_user_sessions`: calls `POST /users/{id}/revokeSignInSessions`
    which invalidates refresh tokens for the user. Effect: all signed-in
    sessions are cut on next token refresh attempt (typically <5 min).
  - Rollback: NOT SUPPORTED. There is no Graph endpoint to un-revoke
    sessions — the user simply re-authenticates. `supports_rollback` returns
    `False` so the executor refuses to dispatch this action autonomously
    unless the policy engine has marked it `requires_approval: true`
    (which our seed policy does — ADR-011).

Dry-run posture (Q13):
  - Default: `AEGIS_MS_GRAPH_LIVE=false`. The connector logs what it would
    do and returns `ok=True, dry_run=True`. The demo loop works end-to-end
    without real credentials.
  - Live: requires tenant_id + client_id + client_secret. Token cache is
    not implemented in Phase 2 — every call fetches a fresh client_credentials
    token. Acceptable since we expect low call volume; revisit if we
    exceed ~10/min.

References:
  https://learn.microsoft.com/en-us/graph/api/user-revokesigninsessions
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import settings
from app.core.execution.base import ExecutionConnector, ExecutionResult
from app.logging import get_logger

log = get_logger("execution.ms_graph")

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_LOGIN_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"  # noqa: S105 - URL constant, not a credential

_SUPPORTED = {"revoke_user_sessions"}
_ROLLBACK_SUPPORTED: set[str] = set()


class MicrosoftGraphConnector(ExecutionConnector):
    name = "microsoft_graph"

    def __init__(self) -> None:
        self._cached_token: str | None = None
        self._cached_token_expires_at: datetime | None = None

    def supports(self, action_class: str) -> bool:
        return action_class in _SUPPORTED

    def supports_rollback(self, action_class: str) -> bool:
        return action_class in _ROLLBACK_SUPPORTED

    async def execute(
        self,
        action_class: str,
        parameters: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> ExecutionResult:
        if action_class != "revoke_user_sessions":
            return ExecutionResult(ok=False, error=f"unsupported action_class: {action_class}")

        users: list[str] = parameters.get("users") or []
        if not users:
            return ExecutionResult(ok=False, error="no users provided")

        if not settings.ms_graph_live:
            log.info(
                "ms_graph.dry_run.revoke_user_sessions",
                idempotency_key=idempotency_key,
                user_count=len(users),
            )
            return ExecutionResult(
                ok=True,
                targets_affected={"users_revoked": users},
                provider_run_id=f"dry-run:{idempotency_key}",
                dry_run=True,
            )

        try:
            token = await self._access_token()
        except _GraphError as exc:
            return ExecutionResult(ok=False, error=f"token fetch failed: {exc}")

        revoked: list[str] = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for upn in users:
                try:
                    r = await client.post(
                        f"{_GRAPH_BASE}/users/{upn}/revokeSignInSessions",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                except httpx.HTTPError as exc:
                    log.error("ms_graph.network_error", upn=upn, error=str(exc))
                    return ExecutionResult(
                        ok=False,
                        error=f"network error revoking {upn}: {exc}",
                        targets_affected={"users_revoked": revoked},
                    )
                if r.status_code not in (200, 204):
                    log.error(
                        "ms_graph.revoke_failed",
                        upn=upn,
                        status=r.status_code,
                        body=r.text[:512],
                    )
                    return ExecutionResult(
                        ok=False,
                        error=f"revoke failed for {upn}: HTTP {r.status_code}",
                        targets_affected={"users_revoked": revoked},
                    )
                revoked.append(upn)

        return ExecutionResult(
            ok=True,
            targets_affected={"users_revoked": revoked},
            provider_run_id=idempotency_key,
            dry_run=False,
        )

    async def rollback(
        self,
        action_class: str,
        parameters: dict[str, Any],
        original_result: dict[str, Any] | None,
        *,
        idempotency_key: str,
    ) -> ExecutionResult:
        return ExecutionResult(
            ok=False,
            error=(
                f"action_class={action_class!r} is non-reversible via Graph. "
                "User must re-authenticate; affected sessions are gone."
            ),
        )

    # ---- internals ----------------------------------------------------------
    async def _access_token(self) -> str:
        now = datetime.now(UTC)
        if (
            self._cached_token
            and self._cached_token_expires_at
            and now < self._cached_token_expires_at - timedelta(seconds=30)
        ):
            return self._cached_token

        if not (
            settings.ms_graph_tenant_id
            and settings.ms_graph_client_id
            and settings.ms_graph_client_secret
        ):
            raise _GraphError("MS Graph credentials are not configured")

        url = _LOGIN_TOKEN_URL.format(tenant=settings.ms_graph_tenant_id)
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                r = await client.post(
                    url,
                    data={
                        "client_id": settings.ms_graph_client_id,
                        "client_secret": settings.ms_graph_client_secret,
                        "grant_type": "client_credentials",
                        "scope": "https://graph.microsoft.com/.default",
                    },
                )
            except httpx.HTTPError as exc:
                raise _GraphError(f"token request error: {exc}") from exc
        if r.status_code != 200:
            raise _GraphError(f"token request HTTP {r.status_code}: {r.text[:256]}")
        body = r.json()
        token = body.get("access_token")
        if not token:
            raise _GraphError("token response missing access_token")

        expires_in = body.get("expires_in")
        if isinstance(expires_in, int) and expires_in > 0:
            self._cached_token_expires_at = now + timedelta(seconds=expires_in)
        else:
            self._cached_token_expires_at = now + timedelta(minutes=5)

        self._cached_token = token
        return token


class _GraphError(RuntimeError):
    """Internal — raised from helpers, mapped to ExecutionResult by callers."""
