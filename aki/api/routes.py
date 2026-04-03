"""API route handlers for Aki HTTP server."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException

from aki.api.models import (
    CreateSessionRequest,
    CreateSessionResponse,
    HealthResponse,
    SendMessageRequest,
    SendMessageResponse,
    SessionHistoryResponse,
)
from aki.api.session_manager import get_session_manager

AKI_API_KEY = os.environ.get("AKI_API_KEY", "")


async def verify_api_key(x_api_key: str = Header(default="", alias="X-API-Key")):
    """Optional API key auth — only enforced when AKI_API_KEY is set."""
    if AKI_API_KEY and x_api_key != AKI_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest):
    """Create a new persistent agent session."""
    extra_tools = None
    if req.mcp_url:
        from aki.mcp.client.adapter import discover_mcp_base_tools

        extra_tools = await discover_mcp_base_tools(url=req.mcp_url, server_name="api")

    manager = get_session_manager()
    state = await manager.create_session(
        user_id=req.user_id,
        role=req.role,
        llm_config=req.default_llm,
        extra_tools=extra_tools,
        user_context=req.user_context,
    )
    return CreateSessionResponse(
        session_id=state.session_id,
        agent_id=state.session_id,
        status="connected",
    )


@router.post("/sessions/{session_id}/messages", response_model=SendMessageResponse)
async def send_message(session_id: str, req: SendMessageRequest):
    """Send a message to an agent session and get a response."""
    manager = get_session_manager()
    try:
        result = await manager.send_message(
            session_id=session_id,
            message=req.message,
            history=req.history or None,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return SendMessageResponse(**result)


@router.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(session_id: str):
    """Get conversation history for a session."""
    manager = get_session_manager()
    try:
        messages = manager.get_history(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return SessionHistoryResponse(session_id=session_id, messages=messages)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """End and cleanup a session."""
    manager = get_session_manager()
    manager.cleanup_session(session_id)
    return {"status": "deleted", "session_id": session_id}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    manager = get_session_manager()
    return HealthResponse(active_sessions=manager.active_count)
