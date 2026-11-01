import pytest
from app.db.session import SessionLocal
from app.agent.conversation_manager import conversation_manager
from app.agent.adapters import MockReasoningAdapter, format_human_slot_time, format_slot_display, detect_language, sanitize_patient_facing_text, is_affirmative, is_contextual_affirmative
import html


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def deterministic_conversation():
    """Keep this workflow test offline and restore global conversation state afterward."""
    previous_adapter = conversation_manager.adapter
    previous_sessions = dict(conversation_manager._sessions)
    conversation_manager.adapter = MockReasoningAdapter()
    conversation_manager._sessions.clear()
    try:
        yield
    finally:
        conversation_manager.adapter = previous_adapter
        conversation_manager._sessions.clear()
        conversation_manager._sessions.update(previous_sessions)


def test_observed_telugu_fever_workflow(db_session, seeded_hospital_data, deterministic_conversation):
    """
    Scenario from Section 6:
    Patient: 'Hi, can you book an appointment for me?'
    Assistant: Asks for symptoms or specialty.
    Patient: 'నాకు జ్వరం ఉంది'
    Expected:
    - Understand fever.
    - Identify General Medicine.
    - Identify the doctor and ask before proceeding to availability.
    - Do not silently assume patient selected a specific doctor.
    - Retrieve availability according to existing workflow.
    - Display an actually available future date and time in Telugu.
    - Maintain Telugu in subsequent turns.
    """
    from datetime import datetime, timedelta, timezone

    from app.agent.schemas import ConfirmationStatus
    from app.models.appointment_slot import AppointmentSlot
    from app.models.department import Department
    from app.models.doctor import Doctor

    # Use this test's isolated database and a future slot rather than the mutable
    # shared demo database, whose November 1 slots can be booked or in the past.
    general_medicine = Department(
        id="test-workflow-general-medicine",
        hospital_id=seeded_hospital_data["hospital"].id,
        name="General Medicine",
        description="Internal Medicine and Primary Care",
        is_active=True,
    )
    db_session.add(general_medicine)
    db_session.flush()

    doctor = Doctor(
        id="test-workflow-vikram-mehta",
        hospital_id=seeded_hospital_data["hospital"].id,
        department_id=general_medicine.id,
        display_name="Dr. Vikram Mehta",
        specialty="General Medicine",
        is_active=True,
    )
    db_session.add(doctor)
    db_session.flush()

    slot_start = datetime.now(timezone.utc).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    slot_start = (slot_start + timedelta(days=2)).replace(hour=14)
    slot = AppointmentSlot(
        id="test-workflow-vikram-slot",
        doctor_id=doctor.id,
        start_time=slot_start,
        end_time=slot_start + timedelta(minutes=30),
        status="AVAILABLE",
    )
    db_session.add(slot)
    db_session.commit()

    session_id = "test_observed_telugu_workflow_isolated"
    conversation_manager._sessions.pop(session_id, None)
    
    # Turn 1: Initial English request
    r1 = conversation_manager.process_message(db_session, "Hi, can you book an appointment for me?", session_id=session_id)
    assert r1.language == "en"
    assert "Aarogya One" in r1.reply or "Hospital" in r1.reply

    # Turn 2: Native Telugu symptom input
    r2 = conversation_manager.process_message(db_session, "నాకు జ్వరం ఉంది", session_id=session_id)
    
    # 1. Preserves collected symptom in reason_category
    assert r2.draft.reason_category == "జ్వరం"
    
    # 2. Identified General Medicine
    assert r2.draft.specialty == "General Medicine"
    
    # 3. Present doctor recommendation clearly without assuming doctor was selected
    assert (
        "సిఫార్సు చేస్తున్నాను" in r2.reply
        or "సిఫార్సు" in r2.reply
        or "కనుగొన్నాను" in r2.reply
    )
    assert "ఎంచుకోబడ్డారు" not in r2.reply  # Must NOT claim patient selected the doctor
    assert "Dr. Vikram Mehta" in r2.reply

    # Patient explicitly selects the suggested doctor before availability lookup.
    doctor_selection = conversation_manager.process_message(
        db_session, "Dr. Vikram Mehta", session_id=session_id
    )
    assert doctor_selection.language == "te"
    assert doctor_selection.draft.doctor_id == doctor.id

    # The deterministic adapter asks before looking up appointment times.
    # A Telugu confirmation authorizes only the availability lookup, not booking.
    slots_response = conversation_manager.process_message(
        db_session, "సరే", session_id=session_id
    )
    assert slots_response.language == "te"
    assert "నవంబర్" in slots_response.reply
    assert "మధ్యాహ్నం" in slots_response.reply or "ఉదయం" in slots_response.reply
    assert "గంటలకు" in slots_response.reply

    # Language remains Telugu through the follow-up slot lookup.
    assert r2.language == "te"

    # The patient selects the seeded, future slot that the workflow offered.
    selection_text = format_human_slot_time(slot.start_time.isoformat(), lang="te")
    selection_response = conversation_manager.process_message(
        db_session, selection_text, session_id=session_id
    )
    assert selection_response.language == "te"
    assert selection_response.draft.slot_id == slot.id
    assert selection_response.draft.doctor_id == doctor.id
    assert selection_response.draft.slot_start_time == slot.start_time.isoformat()

    selected_slot = db_session.get(AppointmentSlot, selection_response.draft.slot_id)
    assert selected_slot is not None
    assert selected_slot.status == "AVAILABLE"
    assert selected_slot.doctor_id == doctor.id
    assert selection_response.booked_appointment is None
    assert selection_response.confirmation_status != ConfirmationStatus.CONFIRMED


def test_doctor_preference_change_in_telugu(db):
    """
    Verifies that when a patient requests a different doctor (వద్దు, నాకు వేరే డాక్టర్ కావాలి),
    the system respects it, clears the draft doctor, and politely prompts for preferred doctor/department in Telugu.
    """
    session_id = "test_doc_pref_change_1"
    conversation_manager.process_message(db, "hi can you book appointment for me", session_id=session_id)
    r2 = conversation_manager.process_message(db, "నాకు జ్వరం ఉంది", session_id=session_id)
    assert r2.draft.doctor_name == "Dr. Vikram Mehta"

    # Patient requests another doctor
    r3 = conversation_manager.process_message(db, "వద్దు, నాకు వేరే డాక్టర్ కావాలి", session_id=session_id)
    assert r3.language == "te"
    assert r3.draft.doctor_id is None
    assert r3.draft.doctor_name is None
    assert "తప్పకుండా" in r3.reply or "డాక్టర్" in r3.reply


def test_multilingual_date_formatting():
    """Verifies that format_human_slot_time localizes dates and times in all 5 languages."""
    iso_time = "2026-11-01T14:00:00Z"
    
    # Telugu
    te_formatted = format_human_slot_time(iso_time, lang="te")
    assert "ఆదివారం, 1 నవంబర్ 2026" in te_formatted
    assert "సాయంత్రం 7:30 గంటలకు" in te_formatted

    # Hindi
    hi_formatted = format_human_slot_time(iso_time, lang="hi")
    assert "रविवार, 1 नवंबर 2026" in hi_formatted
    assert "शाम 7:30 बजे" in hi_formatted

    # Tamil
    ta_formatted = format_human_slot_time(iso_time, lang="ta")
    assert "ஞாயிற்றுக்கிழமை, 1 நவம்பர் 2026" in ta_formatted
    assert "மாலை 7:30 மணிக்கு" in ta_formatted

    # Kannada
    kn_formatted = format_human_slot_time(iso_time, lang="kn")
    assert "ಭಾನುವಾರ, 1 ನವೆಂಬರ್ 2026" in kn_formatted
    assert "ಸಂಜೆ 7:30 ಗಂಟೆಗೆ" in kn_formatted

    # English
    en_formatted = format_human_slot_time(iso_time, lang="en")
    assert "Sunday, November 1, 2026 at 7:30 PM" in en_formatted


def test_format_slot_display_localized():
    """Verifies format_slot_display localizes confirmation summaries."""
    iso_time = "2026-11-03T10:00:00Z"
    disp_te = format_slot_display("slot-1", iso_time, lang="te")
    assert "మంగళవారం, 3 నవంబర్ 2026" in disp_te
    assert "మధ్యాహ్నం 3:30 గంటలకు" in disp_te

    disp_unspec_te = format_slot_display(None, None, lang="te")
    assert disp_unspec_te == "పేర్కొనబడలేదు"


def test_html_entity_decoding():
    """Verifies html.unescape removes literal numeric character references."""
    raw_text = "• &#x4E;ovember 1, 2026 at 2:00 PM — &#x73;earch_doctors"
    clean = html.unescape(raw_text)
    assert clean == "• November 1, 2026 at 2:00 PM — search_doctors"
    assert "&#x4E;" not in clean
    assert "&#x73;" not in clean


def test_language_persistence_with_occasional_english(db):
    """
    Verifies that once an Indic language (e.g. Telugu) is established,
    occasional English words ('Dr. Vikram Mehta', 'yes', '10:00 AM') do not revert the conversation to English.
    """
    session_id = "test_lang_persist_1"
    conversation_manager.process_message(db, "నాకు జ్వరం ఉంది", session_id=session_id)
    
    # English doctor name mentioned by patient
    r2 = conversation_manager.process_message(db, "Dr. Vikram Mehta", session_id=session_id)
    assert r2.language == "te"

    # English confirmation word
    r3 = conversation_manager.process_message(db, "yes", session_id=session_id)
    assert r3.language == "te"


def test_explicit_language_switch(db):
    """Verifies explicit language switching mid-conversation."""
    session_id = "test_lang_switch_1"
    r1 = conversation_manager.process_message(db, "I want to see a cardiologist", session_id=session_id)
    assert r1.language == "en"

    # Explicit switch to Telugu
    r2 = conversation_manager.process_message(db, "తెలుగులో మాట్లాడండి", session_id=session_id)
    assert r2.language == "te"
    assert r2.reply != ""


def test_romanized_telugu_code_mixed_language_is_detected_and_persisted():
    utterance = "aku appointment book chey."
    assert detect_language(utterance, "en") == "te"
    assert detect_language("my name is Ravi", "te") == "te"
    assert is_affirmative("బుక్ చేయి")
    assert is_affirmative("book chey")
    assert is_contextual_affirmative("సరే")
    assert not is_affirmative("సరే")


def test_voice_language_selection_change_does_not_let_stt_hint_override_conversation():
    from app.agent.conversation_manager import ConversationManager

    manager = ConversationManager(adapter=MockReasoningAdapter())
    assert manager.resolve_voice_language_base("language-switch", "te-IN", "en") == "te"
    # A repeated English STT/request hint does not undo the transcript-derived Telugu language.
    assert manager.resolve_voice_language_base("language-switch", "te-IN", "te") == "te"
    # A real UI selection change is applied as the new conversation language.
    assert manager.resolve_voice_language_base("language-switch", "en-IN", "te") == "en"


def test_patient_facing_text_redacts_internal_slot_ids():
    assert sanitize_patient_facing_text("మీ సమయం slot-505 ఖరారు చేయాలా?", "te") == "మీ సమయం అపాయింట్‌మెంట్ సమయం ఖరారు చేయాలా?"

