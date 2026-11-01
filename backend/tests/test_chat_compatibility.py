"""
Regression & verification tests for MediVoice AI chat schema compatibility,
greeting interactions, and blank response prevention.
"""
import pytest
from fastapi.testclient import TestClient


def test_chat_greeting_produces_non_empty_assistant_reply(client: TestClient):
    """
    Verifies that sending 'hi' produces both 'reply' and 'assistant_reply'
    with real, non-empty hospital greeting content, preventing blank chat bubbles.
    """
    res = client.post("/api/v1/agent/chat", json={"message": "hi"})
    assert res.status_code == 200
    data = res.json()

    # Core reply fields
    assert "reply" in data
    assert isinstance(data["reply"], str)
    assert len(data["reply"].strip()) > 0
    assert "Aarogya One Hospital" in data["reply"] or "MediVoice" in data["reply"] or "consultation" in data["reply"]

    # Frontend compatibility aliases
    assert "assistant_reply" in data
    assert data["assistant_reply"] == data["reply"]
    assert "conversation_step" in data
    assert data["conversation_step"] == data["step"]
    assert "requires_confirmation" in data
    assert isinstance(data["requires_confirmation"], bool)
    assert "tool_calls" in data
    assert isinstance(data["tool_calls"], list)


def test_chat_multi_turn_compatibility_fields(client: TestClient):
    """
    Verifies multi-turn doctor discovery preserves compatibility fields
    and does not return empty assistant responses.
    """
    sid = "test-compat-session-001"

    # Turn 1: Doctor inquiry
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": sid, "message": "I need a cardiologist"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["assistant_reply"] == d1["reply"]
    assert len(d1["assistant_reply"].strip()) > 0
    assert d1["session_id"] == sid

    # Turn 2: Pick doctor
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": sid, "message": "Dr. Rajesh Sharma"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["assistant_reply"] == d2["reply"]
    assert len(d2["assistant_reply"].strip()) > 0


def test_voice_turn_response_schema_compatibility(client: TestClient):
    """
    Verifies VoiceTurnResponse schema includes compatibility aliases.
    """
    from app.api.v1.voice import VoiceTurnResponse

    vtr = VoiceTurnResponse(
        transcript="Hello",
        detected_language="en",
        session_id="voice-sess-1",
        reply="Hello! How can I help you?",
        language="en",
        step="GREETING",
        confirmation_status="NONE",
        draft={},
        tool_trace=[],
        tts_available=True,
    )

    data = vtr.model_dump()
    assert data["assistant_reply"] == "Hello! How can I help you?"
    assert data["conversation_step"] == "GREETING"
    assert data["requires_confirmation"] is False
    assert data["tool_calls"] == []

