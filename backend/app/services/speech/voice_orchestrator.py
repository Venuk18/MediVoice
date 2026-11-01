import time
import base64
import logging
import uuid
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.agent.conversation_manager import conversation_manager
from app.agent.schemas import ChatResponse
from app.agent.adapters import detect_language, sanitize_patient_facing_text
from app.core.config import settings
from app.services.speech.stt_service import (
    GnaniPrismaSTT,
    SpeechServiceError,
)
from app.services.speech.tts_service import GnaniTimbreTTS

logger = logging.getLogger(__name__)


class VoiceOrchestrator:
    """
    Coordinates the end-to-end voice pipeline:
    Audio In -> Gnani Prisma STT -> Transcript -> ConversationManager (Gemini/Mock)
    -> Approved Backend Tool Execution -> Hospital Database -> Assistant Response
    -> Gnani Timbre TTS -> Audio Out.
    
    Guarantees:
    - Never accesses the database directly from LLM/speech layers.
    - Preserves session state and strict explicit confirmation before booking.
    - If speech synthesis fails, returns the assistant's text response gracefully.
    - Never submits empty transcripts to the reasoning engine.
    """

    def __init__(
        self,
        stt_service: Optional[GnaniPrismaSTT] = None,
        tts_service: Optional[GnaniTimbreTTS] = None,
    ):
        self.stt = stt_service or GnaniPrismaSTT()
        self.tts = tts_service or GnaniTimbreTTS()

    def process_voice_turn(
        self,
        db: Session,
        audio_bytes: bytes,
        session_id: Optional[str] = None,
        patient_reference: Optional[str] = None,
        language: Optional[str] = None,
        content_type: Optional[str] = "audio/wav",
        include_audio_base64: bool = True,
        correlation_id: Optional[str] = None,
        synthesize_audio: bool = True,
    ) -> Dict[str, Any]:
        """
        Processes a full patient voice turn:
        1. Validates and transcribes incoming audio via Gnani Prisma STT.
        2. Routes the recognized text through ConversationManager.
        3. Executes allowlisted hospital tools via RestrictedToolRouter.
        4. Synthesizes the final assistant response text via Gnani Timbre TTS.
        """
        t_voice_start = time.perf_counter()
        correlation_id = correlation_id or str(uuid.uuid4())
        # 1. Transcribe incoming audio
        stt_result = self.stt.transcribe(
            audio_bytes=audio_bytes,
            language=language,
            content_type=content_type,
        )
        transcode_ms = stt_result.get("transcode_ms", 0.0)
        stt_ms = stt_result.get("stt_ms", 0.0)

        user_transcript = stt_result["transcript"].strip()
        if not user_transcript:
            raise SpeechServiceError(
                code="EMPTY_TRANSCRIPTION",
                safe_message="No clear speech was recognized in the audio recording.",
                status_code=422,
            )

        # Use recognized words and the active UI language for a new session. Provider
        # language metadata is only an STT hint and must not override conversation state.
        session = conversation_manager.get_or_create_session(session_id, patient_reference)
        t_language_start = time.perf_counter()
        language_base = conversation_manager.resolve_voice_language_base(
            session.session_id, language, session.language
        )
        effective_lang = detect_language(user_transcript, language_base)

        session.language = effective_lang
        detected_lang = effective_lang
        language_detection_ms = (time.perf_counter() - t_language_start) * 1000

        # 2. Process message through central hospital ConversationManager
        t_agent_start = time.perf_counter()
        chat_response: ChatResponse = conversation_manager.process_message(
            db=db,
            message=user_transcript,
            session_id=session.session_id,
            patient_reference=patient_reference,
        )
        agent_ms = (time.perf_counter() - t_agent_start) * 1000
        tool_ms = chat_response.timings.get("tool_ms", 0.0) if chat_response.timings else 0.0

        # 3. Synthesize assistant reply text via Gnani Timbre TTS
        audio_bytes_out: Optional[bytes] = None
        audio_b64: Optional[str] = None
        tts_error: Optional[str] = None

        tts_ms = 0.0
        try:
            t_tts_start = time.perf_counter()
            resolved_lang = chat_response.language or session.language or effective_lang
            if synthesize_audio:
                audio_bytes_out = self.tts.synthesize(
                    text=chat_response.reply,
                    language=resolved_lang,
                )
                tts_ms = (time.perf_counter() - t_tts_start) * 1000
                if include_audio_base64 and audio_bytes_out:
                    audio_b64 = base64.b64encode(audio_bytes_out).decode("ascii")
        except Exception as exc:
            logger.warning("TTS speech generation failed for response: %s", exc)
            tts_error = getattr(exc, "safe_message", str(exc))

        total_ms = (time.perf_counter() - t_voice_start) * 1000
        timings = {
            "transcode_ms": round(transcode_ms, 2),
            "stt_ms": round(stt_ms, 2),
            "language_detection_ms": round(language_detection_ms, 2),
            "agent_ms": round(agent_ms, 2),
            "tool_ms": round(tool_ms, 2),
            "tts_ms": round(tts_ms, 2),
            "total_turn_ms": round(total_ms, 2),
            "first_audible_response_ms": round(total_ms, 2),
        }
        if chat_response.timings:
            timings.update(chat_response.timings)
        if settings.VOICE_DIAGNOSTICS_ENABLED:
            logger.info(
                "Voice turn correlation_id=%s transcode_ms=%.2f stt_ms=%.2f language_detection_ms=%.2f agent_ms=%.2f tool_ms=%.2f tts_ms=%.2f total_ms=%.2f",
                correlation_id, transcode_ms, stt_ms, language_detection_ms, agent_ms, tool_ms, tts_ms, total_ms,
            )
        current_tools = [t.model_dump() for t in (chat_response.tool_calls or [])]
        resolved_lang = chat_response.language or session.language or effective_lang
        return {
            "transcript": sanitize_patient_facing_text(user_transcript, resolved_lang),
            "detected_language": resolved_lang,
            "gnani_stt_language": stt_result.get("language_code"),
            "session_id": chat_response.session_id,
            "reply": chat_response.reply,
            "language": resolved_lang,
            "step": chat_response.step.value,
            "confirmation_status": chat_response.confirmation_status.value,
            "draft": chat_response.draft.model_dump(),
            "tool_trace": [t.model_dump() for t in chat_response.tool_trace],
            "turn_tool_calls": current_tools,
            "tool_calls": current_tools,
            "audio_base64": audio_b64,
            "audio_content_type": "audio/wav" if audio_b64 else None,
            "tts_available": audio_b64 is not None,
            "tts_error": tts_error,
            "timings": timings,
            "correlation_id": correlation_id,
            "booked_appointment": chat_response.booked_appointment,
        }


# Singleton orchestrator for dependency injection
voice_orchestrator = VoiceOrchestrator()
