"""Chat endpoints (placeholders until agent is wired up)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from backend.dependencies import get_or_create_session
from backend.models.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat_stream(request: ChatRequest):
    """Chat endpoint with SSE streaming. Currently returns a placeholder response."""
    session_id = get_or_create_session(request.session_id, request.user_id)

    async def event_generator():
        yield {
            "event": "token",
            "data": json.dumps({
                "content": f"[placeholder] I received your message: '{request.message}'. "
                "The agent is not yet connected. This will be replaced in Phase 7."
            }),
        }
        yield {"event": "done", "data": json.dumps({"session_id": session_id})}

    return EventSourceResponse(event_generator())


@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest):
    """Non-streaming chat endpoint. Currently returns a placeholder response."""
    session_id = get_or_create_session(request.session_id, request.user_id)

    return ChatResponse(
        response=f"[placeholder] I received your message: '{request.message}'. "
        "The agent is not yet connected. This will be replaced in Phase 7.",
        session_id=session_id,
    )
