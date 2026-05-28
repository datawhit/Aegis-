"""Token transport schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_at: datetime | None = None
