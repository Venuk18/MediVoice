from app.agent.language_resolver import (
    resolve_adaptive_language,
    resolve_adaptive_language_with_details,
    detect_script_language,
    detect_unsupported_foreign_script,
)
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
        db: Optional[Session] = None,
        audio_bytes: bytes = b"",
        session_id: Optional[str] = None,
        patient_reference: Optional[str] = None,
        language: Optional[str] = None,
        content_type: Optional[str] = "audio/wav",
        include_audio_base64: bool = True,
        correlation_id: Optional[str] = None,
        synthesize_audio: bool = True,
        db_factory: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Processes a full patient voice turn:
        1. Validates and transcribes incoming audio via Gnani Prisma STT (zero DB connection held).
        2. Routes the recognized text through ConversationManager with short-lived database access.
        3. Releases database connection back to the pool BEFORE speech synthesis.
        4. Synthesizes the final assistant response text via Gnani Timbre TTS.
        """
        t_voice_start = time.perf_counter()
        correlation_id = correlation_id or str(uuid.uuid4())
        # 1. Transcribe incoming audio (External network I/O; no DB connection held)
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

        # Retrieve or initialize session state
        session = conversation_manager.get_or_create_session(session_id, patient_reference)
        t_language_start = time.perf_counter()
        
        # Configure manual vs auto mode based on request parameter
        stt_detected = stt_result.get("detected_language")
        norm_req_lang = (language or "").strip().lower()
        if norm_req_lang == "auto" or not norm_req_lang:
            session.language_mode = "auto"
            session.preferred_language = None
        elif norm_req_lang in ("en", "te", "hi", "ta", "kn"):
            prev_sel = conversation_manager._voice_selected_languages.get(session.session_id)
            if prev_sel != norm_req_lang:
                session.language_mode = "manual"
                session.preferred_language = norm_req_lang
                conversation_manager._voice_selected_languages[session.session_id] = norm_req_lang

        session_lang_prev = getattr(session, "language", "en")
        lang_details = resolve_adaptive_language_with_details(
            user_transcript,
            current_session_language=session.language,
            language_mode=getattr(session, "language_mode", "auto"),
            preferred_language=getattr(session, "preferred_language", None),
            stt_detected_language=stt_detected,
        )
        effective_lang = lang_details["resolved_language"]
        active_mode = lang_details["active_mode"]

        session.language = effective_lang
        session.language_mode = active_mode
        detected_lang = effective_lang
        language_detection_ms = (time.perf_counter() - t_language_start) * 1000

        # 2. Process message through central hospital ConversationManager
        # Database operations are strictly bounded to this phase and released before TTS
        t_agent_start = time.perf_counter()
        t_db_start = time.perf_counter()
        db_checkout_ms = 0.0
        if db is not None:
            is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"
            try:
                chat_response: ChatResponse = conversation_manager.process_message(
                    db=db,
                    message=user_transcript,
                    session_id=session.session_id,
                    patient_reference=patient_reference,
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                if not is_sqlite:
                    # In production (PostgreSQL), release the checked-out connection back
                    # to the pool immediately before starting long-running TTS synthesis.
                    db.close()
                db_checkout_ms = (time.perf_counter() - t_db_start) * 1000
        else:
            from app.db.session import SessionLocal
            factory = db_factory or SessionLocal
            with factory() as scoped_db:
                try:
                    chat_response: ChatResponse = conversation_manager.process_message(
                        db=scoped_db,
                        message=user_transcript,
                        session_id=session.session_id,
                        patient_reference=patient_reference,
                    )
                    scoped_db.commit()
                except Exception:
                    scoped_db.rollback()
                    raise
                finally:
                    db_checkout_ms = (time.perf_counter() - t_db_start) * 1000

        agent_ms = (time.perf_counter() - t_agent_start) * 1000
        chat_timings = chat_response.timings or {}
        tool_ms = chat_timings.get("tool_ms", 0.0)
        database_ms = tool_ms or round(db_checkout_ms, 2)
        gemini_reasoning_ms = (
            (chat_timings.get("initial_gemini_request_ms", 0.0) or 0.0)
            + (chat_timings.get("followup_gemini_request_ms", 0.0) or 0.0)
        )
        if not gemini_reasoning_ms:
            gemini_reasoning_ms = chat_timings.get("gemini_reasoning_ms", 0.0) or 0.0

        # 3. Synthesize assistant reply text via Gnani Timbre TTS
        # Notice: DB connection has ALREADY been closed/released back to the pool above!
        audio_bytes_out: Optional[bytes] = None
        audio_b64: Optional[str] = None
        tts_error: Optional[str] = None

        tts_ms = 0.0
        try:
            t_tts_start = time.perf_counter()
            resolved_lang = chat_response.language or session.language or effective_lang
            # Dynamically select TTS voice/language matching the actual assistant reply script
            reply_script_lang = detect_script_language(chat_response.reply)
            tts_lang = reply_script_lang or resolved_lang
            if synthesize_audio:
                audio_bytes_out = self.tts.synthesize(
                    text=chat_response.reply,
                    language=tts_lang,
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
            "gemini_reasoning_ms": round(gemini_reasoning_ms, 2),
            "agent_ms": round(agent_ms, 2),
            "tool_ms": round(tool_ms, 2),
            "database_ms": round(database_ms, 2),
            "tts_ms": round(tts_ms, 2),
            "total_turn_ms": round(total_ms, 2),
            "first_audible_response_ms": round(total_ms, 2),
        }
        if chat_response.timings:
            timings.update(chat_response.timings)
            timings["database_ms"] = round(database_ms, 2)
            timings["gemini_reasoning_ms"] = round(gemini_reasoning_ms, 2)
            timings["total_turn_ms"] = round(total_ms, 2)

        if settings.VOICE_DIAGNOSTICS_ENABLED or True:
            audio_size_bytes = len(audio_bytes_out) if audio_bytes_out else 0
            tts_status_str = "success" if audio_b64 else ("error" if tts_error else "omitted")
            script_class = lang_details.get("detected_script") or lang_details.get("foreign_script") or "latin"
            logger.info(
                "Voice turn diagnostics: correlation_id=%s session_id=%s requested_stt_lang=%s "
                "provider_reported_lang=%s resolver_selected_lang=%s script_classification=%s "
                "previous_session_lang=%s resolver_decision=%s confidence=%.2f "
                "tts_status=%s audio_bytes=%d transcode_ms=%.2f stt_ms=%.2f "
                "language_detection_ms=%.2f gemini_reasoning_ms=%.2f tool_ms=%.2f "
                "database_ms=%.2f tts_ms=%.2f total_ms=%.2f",
                correlation_id,
                session.session_id,
                language or "auto",
                stt_result.get("language_code") or "none",
                effective_lang,
                script_class,
                session_lang_prev,
                lang_details.get("decision", "unknown"),
                stt_result.get("confidence", 0.0),
                tts_status_str,
                audio_size_bytes,
                transcode_ms,
                stt_ms,
                language_detection_ms,
                gemini_reasoning_ms,
                tool_ms,
                database_ms,
                tts_ms,
                total_ms,
            )
        current_tools = [t.model_dump() for t in (chat_response.tool_calls or [])]
        resolved_lang = chat_response.language or session.language or effective_lang
        return {
            "transcript": sanitize_patient_facing_text(user_transcript, resolved_lang),
            "detected_language": effective_lang,
            "language_mode": getattr(session, "language_mode", "auto"),
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
