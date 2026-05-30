"""Well-known endpoints (Sprint 6, D-28).

Per convention, `/.well-known/...` URLs are unauthenticated and live at
the root of the host, not behind `/api/v1`. Today the only entry here
serves the audit-export public key registry, so verifiers can fetch the
right public PEM by `signing_key_id` without an out-of-band channel.

Adding a second well-known (`security.txt`, `openid-configuration`, etc.)
later: drop another route into this module.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.audit.key_registry import KeyRegistryError, load_registry

router = APIRouter()


@router.get("/.well-known/aegis-audit-public-key")
async def audit_public_key_registry() -> dict:
    """Return the public view of the audit-export signing key registry.

    Shape:
        {
          "keys": [
            {"key_id": "...", "status": "active|retired", "public_pem": "..."}
          ]
        }

    No private material is ever exposed here (the registry's
    `public_view()` helper enforces that). Unauthenticated by design —
    auditors must be able to fetch this without a credential.
    """
    try:
        registry = load_registry()
    except KeyRegistryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return {"keys": registry.public_view()}
