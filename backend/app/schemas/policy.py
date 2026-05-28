"""Policy schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    priority: int
    effect: str
    match: dict = Field(default_factory=dict)
    constraints: dict = Field(default_factory=dict)
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PolicyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    priority: int = 100
    effect: str = Field(..., pattern=r"^(allow|escalate|deny)$")
    match: dict = Field(default_factory=dict)
    constraints: dict = Field(default_factory=dict)
    is_active: bool = True


class PolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = None
    priority: int | None = None
    effect: str | None = Field(default=None, pattern=r"^(allow|escalate|deny)$")
    match: dict | None = None
    constraints: dict | None = None
    is_active: bool | None = None


class PolicyList(BaseModel):
    items: list[PolicyRead]
