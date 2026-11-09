"""
MediVoice AI — Regression Tests for English/Telugu Speech Recognition & Language Detection Fix

Covers the 14 mandatory deterministic test cases:
1. English-only speech transcript remains English.
2. Telugu-only transcript remains Telugu.
3. English-Telugu code-mixed transcript is handled correctly.
4. Gujarati-script transcription does NOT switch an English/Telugu session to Gujarati or Hindi.
5. Malayalam-script transcription does NOT switch the session to Malayalam or English.
6. Bengali-script transcription does NOT switch the session to Bengali or Hindi.
7. Short ambiguous affirmations do NOT cause language switching.
8. English doctor names inside Telugu sentences do NOT cause language switching.
9. Telugu sentences containing English medical terminology remain Telugu/code-mixed.
10. Genuine English-to-Telugu switch is detected.
11. Genuine Telugu-to-English switch is detected.
12. One noisy turn does NOT permanently corrupt subsequent conversation language.
13. Ambiguous appointment confirmation triggers clarification (never books).
14. Empty or unusable STT results are handled safely.

All tests run locally with mocked responses (0 Gnani API credits consumed).
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session

from app.agent.language_resolver import (
    resolve_adaptive_language,
    resolve_adaptive_language_with_details,
    detect_script_language,
    detect_unsupported_foreign_script,
    detect_romanized_language,
    detect_english_utterance,
)
from app.agent.adapters import (
    MockReasoningAdapter,
    is_affirmative,
    is_contextual_affirmative,
)
from app.agent.conversation_manager import (
    ConversationManager,
    ConversationStep,
    ConfirmationStatus,
    conversation_manager,
)
from app.services.speech.stt_service import (
    GnaniPrismaSTT,
    SpeechServiceError,
    map_to_internal_language,
    normalize_stt_language,
)
from app.services.speech.voice_orchestrator import VoiceOrchestrator


# =============================================================================
# 1. English-only speech transcript remains English
# =============================================================================
def test_1_english_only_speech_remains_english():
    text = "I would like to book an appointment with a cardiologist for tomorrow."
    details = resolve_adaptive_language_with_details(text, current_session_language="en", language_mode="auto")
    assert details["resolved_language"] == "en"
    assert details["decision"] == "english_detected"


# =============================================================================
# 2. Telugu-only transcript remains Telugu
# =============================================================================
def test_2_telugu_only_speech_remains_telugu():
    text = "నాకు కార్డియాలజిస్ట్ డాక్టర్‌తో అపాయింట్‌మెంట్ కావాలి."
    details = resolve_adaptive_language_with_details(text, current_session_language="te", language_mode="auto")
    assert details["resolved_language"] == "te"
    assert details["detected_script"] == "te"
    assert details["decision"] == "script_detected"


# =============================================================================
# 3. English-Telugu code-mixed transcript is handled correctly
# =============================================================================
def test_3_english_telugu_code_mixing():
    # Native Telugu script mixed with English technical words
    code_mixed_native = "Cardiologist తో appointment book చెయ్యండి."
    lang, mode = resolve_adaptive_language(code_mixed_native, current_session_language="te")
    assert lang == "te"

    # Romanized Telugu mixed with English clinical terms
    code_mixed_romanized = "repu morning Dr. Rajesh Sharma tho appointment kavali."
    details = resolve_adaptive_language_with_details(code_mixed_romanized, current_session_language="te")
    assert details["resolved_language"] == "te"
    assert details["decision"] == "romanized_detected"


# =============================================================================
# 4. Gujarati-script transcription does NOT switch session to Gujarati or Hindi
# =============================================================================
def test_4_gujarati_script_does_not_switch_to_gujarati_or_hindi():
    gujarati_text = "હા, સારી સારી જરૂર છે।"  # Actual observed failure utterance
    assert detect_unsupported_foreign_script(gujarati_text) == "gujarati"
    # Verify that the Devanagari danda does NOT cause false Hindi detection
    assert detect_script_language(gujarati_text) is None

    # In English session: retains English
    details_en = resolve_adaptive_language_with_details(gujarati_text, current_session_language="en")
    assert details_en["resolved_language"] == "en"
    assert details_en["decision"] == "unsupported_foreign_script_retained"
    assert details_en["foreign_script"] == "gujarati"

    # In Telugu session: retains Telugu
    details_te = resolve_adaptive_language_with_details(gujarati_text, current_session_language="te")
    assert details_te["resolved_language"] == "te"
    assert details_te["decision"] == "unsupported_foreign_script_retained"


# =============================================================================
# 5. Malayalam-script transcription does NOT switch session to Malayalam or English
# =============================================================================
def test_5_malayalam_script_does_not_switch_to_malayalam_or_english():
    malayalam_text = "ആ, అപ്പോൾ അതിൻ്റെ పేര്?"  # Actual observed failure utterance
    assert detect_unsupported_foreign_script(malayalam_text) == "malayalam"

    # If STT reported 'ml-IN', map_to_internal_language should return None / uncertain, NOT 'en'
    assert map_to_internal_language("ml-IN") is None
    assert map_to_internal_language("ml") is None

    # In Telugu session: retains Telugu even if STT reported 'uncertain' or 'en'
    details_te = resolve_adaptive_language_with_details(
        malayalam_text,
        current_session_language="te",
        stt_detected_language="uncertain",
    )
    assert details_te["resolved_language"] == "te"
    assert details_te["decision"] == "unsupported_foreign_script_retained"

    # In English session: retains English
    details_en = resolve_adaptive_language_with_details(
        malayalam_text,
        current_session_language="en",
    )
    assert details_en["resolved_language"] == "en"
    assert details_en["decision"] == "unsupported_foreign_script_retained"


# =============================================================================
# 6. Bengali-script transcription does NOT switch session to Bengali or Hindi
# =============================================================================
def test_6_bengali_script_does_not_switch_to_bengali_or_hindi():
    bengali_text = "আর তুলতে পেরেছি সবাই।"  # Actual observed failure utterance
    assert detect_unsupported_foreign_script(bengali_text) == "bengali"
    # Danda does not falsely identify Hindi
    assert detect_script_language(bengali_text) is None

    # In Telugu session: retains Telugu
    details_te = resolve_adaptive_language_with_details(bengali_text, current_session_language="te")
    assert details_te["resolved_language"] == "te"
    assert details_te["decision"] == "unsupported_foreign_script_retained"

    # In English session: retains English
    details_en = resolve_adaptive_language_with_details(bengali_text, current_session_language="en")
    assert details_en["resolved_language"] == "en"
    assert details_en["decision"] == "unsupported_foreign_script_retained"


# =============================================================================
# 7. Short ambiguous affirmations do NOT cause language switching
# =============================================================================
def test_7_short_ambiguous_affirmations_retain_session_language():
    short_tokens = ["ok", "okay", "yes", "sure", "alright", "yep", "yeah"]
    for token in short_tokens:
        # In a Telugu session, English affirmation tokens like 'ok' or 'yes' must retain 'te'
        lang_te, _ = resolve_adaptive_language(token, current_session_language="te")
        assert lang_te == "te", f"Token '{token}' caused unwanted language switch away from 'te'"

        # In an English session, affirmation tokens like 'ok' or 'yes' must retain 'en'
        lang_en, _ = resolve_adaptive_language(token, current_session_language="en")
        assert lang_en == "en", f"Token '{token}' caused unwanted language switch away from 'en'"


# =============================================================================
# 8. English doctor names inside Telugu sentences do NOT cause language switching
# =============================================================================
def test_8_english_doctor_names_in_telugu_sentences():
    u1 = "డాక్టర్ Dr. Rajesh Sharma గారితో మాట్లాడాలి."
    assert resolve_adaptive_language(u1, current_session_language="te")[0] == "te"

    u2 = "Dr. Sunita Rao tho appointment book chey"
    assert resolve_adaptive_language(u2, current_session_language="te")[0] == "te"


# =============================================================================
# 9. Telugu sentences containing English medical terminology remain Telugu
# =============================================================================
def test_9_telugu_sentences_with_english_medical_terms():
    u1 = "Cardiology consultation మరియు ECG test వివరాలు చెప్పండి."
    assert resolve_adaptive_language(u1, current_session_language="te")[0] == "te"

    u2 = "General medicine doctor consultation fee entha?"
    assert resolve_adaptive_language(u2, current_session_language="te")[0] == "te"


# =============================================================================
# 10. Genuine English-to-Telugu switch is detected
# =============================================================================
def test_10_genuine_english_to_telugu_switch():
    initial_session_lang = "en"
    telugu_utterance = "దయచేసి నాకు కార్డియాలజీ విభాగంలో డాక్టర్‌ను చూపించండి."
    new_lang, mode = resolve_adaptive_language(telugu_utterance, current_session_language=initial_session_lang)
    assert new_lang == "te"
    assert mode == "auto"


# =============================================================================
# 11. Genuine Telugu-to-English switch is detected
# =============================================================================
def test_11_genuine_telugu_to_english_switch():
    initial_session_lang = "te"
    english_utterance = "Can you please show me the available appointment slots for tomorrow morning?"
    new_lang, mode = resolve_adaptive_language(english_utterance, current_session_language=initial_session_lang)
    assert new_lang == "en"
    assert mode == "auto"


# =============================================================================
# 12. One noisy turn does NOT permanently corrupt subsequent conversation language
# =============================================================================
def test_12_single_noisy_turn_does_not_corrupt_session_language():
    cm = ConversationManager(adapter=MockReasoningAdapter())
    session_id = "test-noisy-turn-resilience"
    session = cm.get_or_create_session(session_id)
    session.language = "te"

    # Turn 1: Patient speaks Telugu
    t1 = "నాకు గుండె సంబంధిత వైద్యుడిని కలవాలి."
    l1, _ = resolve_adaptive_language(t1, current_session_language=session.language)
    session.language = l1
    assert session.language == "te"

    # Turn 2: Background noise or acoustic echo causes STT to output Gujarati hallucination
    t2 = "હા, સારી સારી જરૂર છે।"
    l2, _ = resolve_adaptive_language(t2, current_session_language=session.language)
    session.language = l2
    # Verify session language remained Telugu and was NOT corrupted to Hindi or Gujarati!
    assert session.language == "te"

    # Turn 3: Patient continues speaking Telugu
    t3 = "రేపు ఉదయం 10 గంటలకు వీలవుతుందా?"
    l3, _ = resolve_adaptive_language(t3, current_session_language=session.language)
    session.language = l3
    assert session.language == "te"


# =============================================================================
# 13. Ambiguous appointment confirmation triggers clarification (never books)
# =============================================================================
def test_13_ambiguous_appointment_confirmation_triggers_clarification(db_session: Session, seeded_hospital_data):
    cm = ConversationManager(adapter=MockReasoningAdapter())
    session_id = "test-ambiguous-confirm-guard"
    session = cm.get_or_create_session(session_id)
    session.language = "te"

    doc = seeded_hospital_data["doc_sharma"]
    slot = seeded_hospital_data["slot_available"]

    session.draft.doctor_id = doc.id
    session.draft.doctor_name = doc.display_name
    session.draft.specialty = doc.specialty
    session.draft.slot_id = slot.id
    session.draft.slot_start_time = str(slot.start_time)
    session.draft.patient_reference = "PAT-2026-6910"
    session.draft.patient_name = "Venu"
    session.draft.reason_category = "Cardiology Consultation"
    session.step = ConversationStep.AWAITING_CONFIRMATION
    session.confirmation_status = ConfirmationStatus.PENDING
    session.confirmed_draft_fingerprint = session.draft.get_fingerprint()

    # Verify is_affirmative strictly rejects foreign scripts
    assert is_affirmative("હા, સારી સારી જરૂર છે।") is False
    assert is_contextual_affirmative("હા, સારી સારી જરૂર છે।") is False

    # Submit the noisy Gujarati transcript to ConversationManager
    res = cm.process_message(db_session, "હા, સારી સારી જરૂર છે।", session_id=session_id)

    # Must NOT book an appointment!
    assert session.confirmation_status == ConfirmationStatus.PENDING
    assert session.step != ConversationStep.BOOKED
    assert session.booked_appointment is None

    # Must ask for repetition / clarification in Telugu
    assert "నిర్ధారించడానికి" in res.reply or "వివరాలను చెప్పండి" in res.reply or "స్పష్టంగా" in res.reply


# =============================================================================
# 14. Empty or unusable STT results are handled safely
# =============================================================================
def test_14_empty_or_unusable_stt_results_handled_safely():
    stt = GnaniPrismaSTT(api_key="")

    # Completely empty bytes
    with pytest.raises(SpeechServiceError) as exc_empty:
        stt.validate_audio(b"")
    assert exc_empty.value.code == "EMPTY_AUDIO"

    # Micro-recording (< 32 bytes)
    with pytest.raises(SpeechServiceError) as exc_short:
        stt.validate_audio(b"RIFF\x00\x00")
    assert exc_short.value.code == "EMPTY_AUDIO"

    # Voice orchestrator rejecting empty transcript
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = {
        "transcript": "   ",
        "full_transcript": "   ",
        "language_code": "indic-auto",
        "detected_language": "uncertain",
        "confidence": 0.0,
    }
    orchestrator = VoiceOrchestrator(stt_service=mock_stt)

    with pytest.raises(SpeechServiceError) as exc_voice:
        orchestrator.process_voice_turn(
            audio_bytes=b"RIFF" + b"\x00" * 40,
            session_id="test-empty-voice-turn",
        )
    assert exc_voice.value.code == "EMPTY_TRANSCRIPTION"


# =============================================================================
# 15. Observability telemetry verification
# =============================================================================
def test_15_observability_diagnostics_structure():
    text = "Dr. Rajesh Sharma"
    details = resolve_adaptive_language_with_details(text, current_session_language="te")

    # Required diagnostic fields
    assert "resolved_language" in details
    assert "active_mode" in details
    assert "decision" in details
    assert "detected_script" in details
    assert "foreign_script" in details
    assert "previous_language" in details

    assert details["resolved_language"] == "te"
    assert details["decision"] == "entity_safeguard_retained"
    assert details["previous_language"] == "te"
