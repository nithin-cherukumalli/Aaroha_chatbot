from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SessionRequest(BaseModel):
    access_token: str = Field(min_length=20, max_length=10000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class LifecycleRequest(BaseModel):
    action: Literal["deactivate", "reactivate", "delete"]


class PendingQuestionRequest(BaseModel):
    state: Literal["resolved", "open"]


class ProfileActivationRequest(BaseModel):
    profile_id: UUID
