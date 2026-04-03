"""API request/response models for Aki HTTP server."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    user_id: str
    role: str = "orchestrator"
    default_llm: str = "openai:gpt-4o"
    mcp_url: str | None = None
    user_context: dict[str, Any] | None = None


class CreateSessionResponse(BaseModel):
    session_id: str
    agent_id: str
    status: str = "connected"


class SendMessageRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    user_id: str | None = None


class SendMessageResponse(BaseModel):
    reply: str
    system_events: list[str] = Field(default_factory=list)
    profile_updates: dict[str, Any] = Field(default_factory=dict)
    preference_updates: dict[str, Any] = Field(default_factory=dict)
    next_status: str | None = None


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "aki"
    active_sessions: int = 0
