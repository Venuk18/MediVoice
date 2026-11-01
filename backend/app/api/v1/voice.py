import logging
import base64
import json
import time
import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.speech import (
    GnaniPrismaSTT,
    GnaniTimbreTTS,
    SpeechServiceError,
    voice_orchestrator,
    is_fixed_greeting,
)

router = APIRouter(prefix="/voice", tags=["Voice AI & Speech Operations"])
logger = logging.getLogger(__name__)


class TranscribeResponse(BaseModel):
    transcript: str
    language_code: str
    detected_language: str
    confidence: float
    model: str


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="Assistant text to convert to speech")
    language: Optional[str] = Field(None, description="Language code (e.g. 'te', 'hi', 'ta', 'kn', 'en')")
    voice: Optional[str] = Field(None, description="Optional custom voice name")
    speed: Optional[float] = Field(1.0, ge=0.5, le=2.0, description="Speech rate multiplier")


class VoiceTurnResponse(BaseModel):
    correlation_id: Optional[str] = None
    transcript: str
    detected_language: str
    gnani_stt_language: Optional[str] = None
    session_id: str
    reply: str
    language: str
    step: str
    confirmation_status: str
    draft: Dict[str, Any]
    tool_trace: List[Dict[str, Any]]
    turn_tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    audio_base64: Optional[str] = None
    audio_content_type: Optional[str] = None
    tts_available: bool
    tts_error: Optional[str] = None
    timings: Optional[Dict[str, float]] = None

    # Compatibility aliases for frontend clients
    assistant_reply: Optional[str] = None
    conversation_step: Optional[str] = None
    requires_confirmation: Optional[bool] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    booked_appointment: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def populate_compatibility_aliases(self) -> "VoiceTurnResponse":
        if self.assistant_reply is None:
            self.assistant_reply = self.reply
        if self.conversation_step is None:
            self.conversation_step = self.step
        if self.requires_confirmation is None:
            self.requires_confirmation = (
                self.confirmation_status == "PENDING"
                or self.step == "AWAITING_CONFIRMATION"
            )
        if self.tool_calls is None:
            self.tool_calls = self.turn_tool_calls
        return self


@router.get(
    "/config",
    summary="Inspect voice and speech configuration",
)
def get_voice_config():
    """Returns safe metadata regarding Gnani Prisma STT, Gnani Timbre TTS, and supported voice languages."""
    return {
        "voice_enabled": settings.VOICE_ENABLED,
        "live_gnani_configured": bool(settings.GNANI_API_KEY.strip()),
        "stt_model": settings.GNANI_STT_MODEL,
        "tts_model": settings.GNANI_TTS_MODEL,
        "default_voice": settings.GNANI_TTS_VOICE,
        "default_language": settings.GNANI_DEFAULT_LANGUAGE,
        "max_duration_seconds": settings.VOICE_MAX_DURATION_SECONDS,
        "supported_languages": [
            {"code": "en", "locale": "en-IN", "name": "English (India)", "native": "English"},
            {"code": "te", "locale": "te-IN", "name": "Telugu", "native": "తెలుగు"},
            {"code": "hi", "locale": "hi-IN", "name": "Hindi", "native": "हिन्दी"},
            {"code": "ta", "locale": "ta-IN", "name": "Tamil", "native": "தமிழ்"},
            {"code": "kn", "locale": "kn-IN", "name": "Kannada", "native": "ಕನ್ನಡ"},
        ],
    }


@router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    summary="Transcribe patient voice audio to text via Gnani Prisma STT",
)
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio recording file (WAV, WebM, OGG, MP3)"),
    language: Optional[str] = Form(None, description="Target language hint or code (e.g. 'te-IN', 'en-IN')"),
):
    """
    Submits patient audio to Gnani Prisma STT:
    - Validates audio size and MIME format.
    - Resolves language code.
    - Transcribes audio on the backend without leaking Gnani credentials.
    - Returns recognized transcript and detected language.
    """
    try:
        audio_bytes = await file.read()
        stt = GnaniPrismaSTT()
        result = stt.transcribe(
            audio_bytes=audio_bytes,
            language=language,
            content_type=file.content_type,
            filename=file.filename,
        )
        return TranscribeResponse(
            transcript=result["transcript"],
            language_code=result["language_code"],
            detected_language=result["detected_language"],
            confidence=result.get("confidence", 0.95),
            model=result.get("model", "prisma"),
        )
    except SpeechServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={"code": exc.code, "message": exc.safe_message},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "TRANSCRIPTION_FAILED", "message": "Failed to process audio transcription."},
        )


@router.post(
    "/synthesize",
    summary="Synthesize assistant response text to speech via Gnani Timbre TTS",
    responses={
        200: {
            "content": {"audio/wav": {}},
            "description": "Returns raw binary WAV audio stream.",
        }
    },
)
def synthesize_speech(
    payload: SynthesizeRequest,
    x_mediavoice_correlation_id: Optional[str] = Header(None),
):
    """
    Synthesizes assistant text into audible WAV speech using Gnani Timbre:
    - Cleans Markdown and clinical metadata formatting.
    - Generates language-appropriate voice audio.
    - Returns streaming playable audio/wav.
    """
    try:
        request_arrival = time.perf_counter()
        tts = GnaniTimbreTTS()
        tts_request_start = time.perf_counter()
        audio_bytes = tts.synthesize(
            text=payload.text,
            language=payload.language,
            voice=payload.voice,
            speed=payload.speed,
        )
        if settings.VOICE_DIAGNOSTICS_ENABLED:
            logger.info(
                "TTS REST correlation_id=%s request_arrival_ms=%.2f provider_total_ms=%.2f",
                (x_mediavoice_correlation_id or "")[:100],
                (tts_request_start - request_arrival) * 1000,
                (time.perf_counter() - tts_request_start) * 1000,
            )
        is_fixed = is_fixed_greeting(payload.text)
        cache_ctrl = "public, max-age=86400" if is_fixed else "no-cache"
        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "Content-Disposition": 'inline; filename="assistant_response.wav"',
                "Cache-Control": cache_ctrl,
                "X-MediVoice-Cache": "HIT" if is_fixed else "DYNAMIC",
            },
        )
    except SpeechServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={"code": exc.code, "message": exc.safe_message},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "SYNTHESIS_FAILED", "message": "Failed to synthesize speech."},
        )


@router.post(
    "/respond",
    response_model=VoiceTurnResponse,
    summary="End-to-end voice turn: Audio -> STT -> ConversationManager -> Hospital Tools -> TTS -> Audio",
)
async def voice_respond(
    file: UploadFile = File(..., description="Audio recording from patient interface"),
    session_id: Optional[str] = Form(None, description="Existing session identifier"),
    patient_reference: Optional[str] = Form(None, description="Patient reference ID"),
    language: Optional[str] = Form(None, description="Active language choice"),
    correlation_id: Optional[str] = Form(None, description="Client-generated voice turn correlation ID"),
    db: Session = Depends(get_db),
):
    """
    Executes the complete multimodal hospital voice loop:
    1. Transcribes audio via Gnani Prisma STT.
    2. Runs central ConversationManager (with Gemini or Mock reasoning).
    3. Validates and executes allowlisted tools against the Aarogya One database.
    4. Synthesizes the final assistant response via Gnani Timbre TTS.
    5. Returns both readable text and playable audio payload.
    """
    try:
        request_arrival = time.perf_counter()
        audio_bytes = await file.read()
        upload_read_ms = (time.perf_counter() - request_arrival) * 1000
        result = voice_orchestrator.process_voice_turn(
            db=db,
            audio_bytes=audio_bytes,
            session_id=session_id,
            patient_reference=patient_reference,
            language=language,
            content_type=file.content_type,
            include_audio_base64=True,
            correlation_id=correlation_id,
        )
        result["timings"]["audio_read_ms"] = round(upload_read_ms, 2)
        if settings.VOICE_DIAGNOSTICS_ENABLED:
            logger.info(
                "Voice request correlation_id=%s audio_read_ms=%.2f backend_total_ms=%.2f",
                result["correlation_id"], upload_read_ms,
                (time.perf_counter() - request_arrival) * 1000,
            )
        return VoiceTurnResponse(**result)
    except SpeechServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={"code": exc.code, "message": exc.safe_message},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "VOICE_TURN_FAILED", "message": f"Voice turn failed: {str(exc)}"},
        )


@router.post(
    "/respond/text",
    response_model=VoiceTurnResponse,
    summary="Experimental voice turn without inline TTS audio",
)
async def voice_respond_text(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    patient_reference: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    correlation_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Experimental counterpart to /respond; preserves orchestration but defers TTS."""
    try:
        started = time.perf_counter()
        audio_bytes = await file.read()
        result = voice_orchestrator.process_voice_turn(
            db=db,
            audio_bytes=audio_bytes,
            session_id=session_id,
            patient_reference=patient_reference,
            language=language,
            content_type=file.content_type,
            include_audio_base64=False,
            correlation_id=correlation_id,
            synthesize_audio=False,
        )
        result["timings"]["audio_read_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return VoiceTurnResponse(**result)
    except SpeechServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={"code": exc.code, "message": exc.safe_message},
        )
    except Exception as exc:
        logger.exception("Experimental text-only voice turn failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "VOICE_TURN_FAILED", "message": "Failed to process voice turn."},
        )


@router.post("/synthesize/stream", summary="Experimental Gnani Timbre REST SSE proxy")
def synthesize_speech_stream(
    payload: SynthesizeRequest,
    x_mediavoice_correlation_id: Optional[str] = Header(None),
):
    """Proxy final patient-facing speech as ordered base64 raw-PCM SSE events."""
    correlation_id = (x_mediavoice_correlation_id or str(uuid.uuid4()))[:100]
    request_arrival = time.perf_counter()

    def events():
        tts = GnaniTimbreTTS()
        sent_chunks = 0
        stream_iterator = None
        tts_request_start = None
        try:
            yield "event: start\ndata: " + json.dumps(
                {"correlation_id": correlation_id, "sample_rate": tts.sample_rate, "channels": 1, "sample_width": 2}
            ) + "\n\n"
            tts_request_start = time.perf_counter()
            stream_iterator = tts.stream_synthesize(
                text=payload.text,
                language=payload.language,
                voice=payload.voice,
                speed=payload.speed,
            )
            for item in stream_iterator:
                if item["type"] == "chunk":
                    sent_chunks += 1
                    if settings.VOICE_DIAGNOSTICS_ENABLED and sent_chunks == 1:
                        logger.info(
                            "TTS stream correlation_id=%s request_arrival_ms=%.2f first_chunk_ms=%.2f",
                            correlation_id,
                            (tts_request_start - request_arrival) * 1000,
                            (time.perf_counter() - tts_request_start) * 1000,
                        )
                    yield "event: chunk\ndata: " + json.dumps({
                        "chunk_index": item["chunk_index"],
                        "audio": base64.b64encode(item["audio"]).decode("ascii"),
                    }) + "\n\n"
                elif item["type"] == "complete":
                    if settings.VOICE_DIAGNOSTICS_ENABLED:
                        logger.info(
                            "TTS stream correlation_id=%s chunks=%d provider_total_ms=%.2f",
                            correlation_id, sent_chunks, (time.perf_counter() - tts_request_start) * 1000,
                        )
                    yield "event: complete\ndata: " + json.dumps({"chunk_index": item["chunk_index"]}) + "\n\n"
        except SpeechServiceError as exc:
            # Only safe, stable codes cross the API boundary; provider event bodies are never forwarded.
            yield "event: error\ndata: " + json.dumps({
                "code": exc.code,
                "recoverable": sent_chunks == 0,
                "message": "Streaming speech failed before audio playback." if sent_chunks == 0 else "Streaming speech was interrupted.",
            }) + "\n\n"
        except GeneratorExit:
            raise
        except Exception:
            logger.exception("Experimental Timbre stream failed correlation_id=%s", correlation_id)
            yield "event: error\ndata: " + json.dumps({
                "code": "STREAM_FAILED", "recoverable": sent_chunks == 0,
                "message": "Streaming speech was interrupted.",
            }) + "\n\n"
        finally:
            if stream_iterator is not None:
                close = getattr(stream_iterator, "close", None)
                if close is not None:
                    close()
            tts.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
