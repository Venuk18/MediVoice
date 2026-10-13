from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.agent.schemas import (
    ChatRequest,
    ChatResponse,
    AgentSessionState,
    SessionResetResponse,
)
from app.agent.conversation_manager import conversation_manager

router = APIRouter(prefix="/agent", tags=["AI Text Agent"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Process patient chat message via Text-First AI Agent",
)
def chat_with_agent(
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    Submits a user message to the text-first conversation manager:
    - Maintains multi-turn context per session_id.
    - Prompts for missing booking details.
    - Executes allowlisted tools via restricted tool router.
    - Requires explicit patient confirmation before booking.
    - Re-validates slot availability and double-booking constraints on the backend.
    """
    response = conversation_manager.process_message(
        db=db,
        message=payload.message,
        session_id=payload.session_id,
        patient_reference=payload.patient_reference,
    )
    return response


@router.get(
    "/sessions/{session_id}",
    response_model=AgentSessionState,
    summary="Inspect conversation session state",
)
def get_session_state(session_id: str):
    """Retrieves full conversation state and history for an active session."""
    if session_id not in conversation_manager._sessions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return conversation_manager._sessions[session_id]


@router.post(
    "/sessions/{session_id}/reset",
    response_model=SessionResetResponse,
    summary="Reset conversation session",
)
def reset_session(session_id: str):
    """Clears conversation context and draft state for a session."""
    conversation_manager.reset_session(session_id)
    return SessionResetResponse(
        status="reset_successful",
        session_id=session_id,
    )
