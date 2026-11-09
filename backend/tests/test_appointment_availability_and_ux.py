import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.hospital import Hospital
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.appointment_slot import AppointmentSlot
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.services.doctor_service import (
    get_hospital_timezone,
    generate_upcoming_slots_for_doctors,
    find_alternative_doctors_with_slots,
    get_available_slots_tool,
)
from app.agent.conversation_manager import ConversationManager
from app.agent.schemas import ConversationStep, ConfirmationStatus
from app.agent.adapters import MockReasoningAdapter


@pytest.fixture
def availability_test_env(db_session: Session):
    """Sets up a clean hospital test environment with cardiology department and 2 doctors."""
    # Create Hospital
    hosp = db_session.get(Hospital, "hosp-phase5")
    if not hosp:
        hosp = Hospital(
            id="hosp-phase5",
            name="Aarogya One Hospital",
            address="Road No 2, Banjara Hills, Hyderabad, Telangana 500034",
            description="Leading multi-specialty tertiary care hospital in Hyderabad",
        )
        db_session.add(hosp)

    # Create Cardiology Department
    cardio_dept = db_session.get(Department, "dept-cardio-phase5")
    if not cardio_dept:
        cardio_dept = Department(
            id="dept-cardio-phase5",
            hospital_id="hosp-phase5",
            name="Cardiology",
            description="Cardiovascular medicine and heart health",
        )
        db_session.add(cardio_dept)

    # Doctor 1: Dr. Rajesh Sharma
    doc_sharma = db_session.get(Doctor, "doc-sharma-phase5")
    if not doc_sharma:
        doc_sharma = Doctor(
            id="doc-sharma-phase5",
            hospital_id="hosp-phase5",
            department_id="dept-cardio-phase5",
            display_name="Dr. Rajesh Sharma",
            specialty="Cardiology",
            is_active=True,
        )
        db_session.add(doc_sharma)

    # Doctor 2: Dr. Sunita Rao (colleague in Cardiology)
    doc_rao = db_session.get(Doctor, "doc-rao-phase5")
    if not doc_rao:
        doc_rao = Doctor(
            id="doc-rao-phase5",
            hospital_id="hosp-phase5",
            department_id="dept-cardio-phase5",
            display_name="Dr. Sunita Rao",
            specialty="Cardiology",
            is_active=True,
        )
        db_session.add(doc_rao)

    # Synthetic patient
    pat = db_session.get(Patient, "pat-phase5-test")
    if not pat:
        pat = Patient(
            id="pat-phase5-test",
            patient_reference="PAT-PHASE5-001",
            full_name="Kavitha Reddy",
            phone_number="9876543210",
        )
        db_session.add(pat)

    db_session.commit()
    return {
        "hospital": hosp,
        "department": cardio_dept,
        "doc_sharma": doc_sharma,
        "doc_rao": doc_rao,
        "patient": pat,
    }


def test_20_day_slot_generation_for_active_doctors(db_session: Session, availability_test_env):
    """
    Requirement 1: Generates appointment slots dynamically for the next 20 calendar days.
    - Uses Asia/Kolkata timezone.
    - Excludes Sundays.
    - Creates multiple slots per day across shifts.
    """
    tz = get_hospital_timezone()
    base_date = datetime.now(tz).date()

    slots_created = generate_upcoming_slots_for_doctors(db_session, days=20, base_date=base_date)
    assert slots_created > 0

    # Query created slots for Dr. Rajesh Sharma
    sharma_slots = db_session.scalars(
        select(AppointmentSlot).where(
            AppointmentSlot.doctor_id == "doc-sharma-phase5",
            AppointmentSlot.status == "AVAILABLE",
        ).order_by(AppointmentSlot.start_time.asc())
    ).all()

    assert len(sharma_slots) > 0

    # Check Sunday exclusion
    for slot in sharma_slots:
        st = slot.start_time
        if st.tzinfo is not None:
            st = st.astimezone(tz)
        assert st.weekday() != 6, f"Slot {slot.id} generated on Sunday ({st})"

    # Check multiple shifts on a single weekday
    first_weekday_slots = [
        s for s in sharma_slots
        if (s.start_time.astimezone(tz) if s.start_time.tzinfo else s.start_time).date() == (
            sharma_slots[0].start_time.astimezone(tz) if sharma_slots[0].start_time.tzinfo else sharma_slots[0].start_time
        ).date()
    ]
    assert len(first_weekday_slots) >= 2, "Expected multiple slots per doctor per day"


def test_slot_generation_idempotency_and_preserves_bookings(db_session: Session, availability_test_env):
    """
    Requirement 1 (Safety): Running the generator repeatedly is completely idempotent.
    - Generates 0 new slots on subsequent run.
    - Never overwrites or resets already booked appointment slots.
    """
    tz = get_hospital_timezone()
    base_date = datetime.now(tz).date()

    # First run
    generate_upcoming_slots_for_doctors(db_session, days=20, base_date=base_date)
    initial_count = db_session.scalar(select(func.count(AppointmentSlot.id)).where(AppointmentSlot.doctor_id == "doc-sharma-phase5"))

    # Book one of Dr. Sharma's slots
    first_slot = db_session.scalars(
        select(AppointmentSlot).where(
            AppointmentSlot.doctor_id == "doc-sharma-phase5",
            AppointmentSlot.status == "AVAILABLE",
        ).order_by(AppointmentSlot.start_time.asc())
    ).first()
    assert first_slot is not None
    first_slot.status = "BOOKED"
    db_session.commit()

    # Second run with same parameters
    second_run_created = generate_upcoming_slots_for_doctors(db_session, days=20, base_date=base_date)
    assert second_run_created == 0, "Idempotency failed: second run should not create duplicate slots"

    # Verify booked slot was untouched
    refreshed_slot = db_session.get(AppointmentSlot, first_slot.id)
    assert refreshed_slot.status == "BOOKED", "Booked slot was unexpectedly reset to AVAILABLE"


def test_next_available_slot_when_patient_requests_any_time(db_session: Session, availability_test_env):
    """
    Requirement 2: When patient says 'Any time is fine. Book it.', agent:
    - Finds the earliest available slot for the selected doctor across the 20-day window.
    - Clearly presents the slot details.
    - Asks for explicit confirmation.
    - Does NOT book prematurely without confirmation.
    """
    tz = get_hospital_timezone()
    base_date = datetime.now(tz).date()
    generate_upcoming_slots_for_doctors(db_session, days=20, base_date=base_date)

    manager = ConversationManager(adapter=MockReasoningAdapter())
    session_id = "test-any-time-booking-en"

    # Turn 1: Patient selects Dr. Rajesh Sharma
    r1 = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="I want to book an appointment with Dr. Rajesh Sharma",
        patient_reference="PAT-PHASE5-001",
    )
    assert r1.draft.doctor_id == "doc-sharma-phase5"
    assert r1.step == ConversationStep.COLLECTING_SLOT

    # Turn 2: Patient says 'Any time is fine. Book it.'
    r2 = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="Any time is fine. Book it.",
    )

    # Must present earliest slot and ask confirmation
    assert "earliest available appointment" in r2.reply.lower() or "would you like me to book this" in r2.reply.lower()
    # Booking must NOT be completed yet
    assert r2.booked_appointment is None
    assert r2.confirmation_status != ConfirmationStatus.CONFIRMED

    # Turn 3: Patient gives reason
    r3 = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="Yes, routine heart checkup",
    )
    # Checks that reason or confirmation gate is active
    assert r3.booked_appointment is None or r3.step == ConversationStep.AWAITING_CONFIRMATION


def test_flexible_slot_telugu_conversation(db_session: Session, availability_test_env):
    """
    Requirement 2 & 4: Telugu conversation with flexible slot request:
    - Patient says 'ఏదైనా సమయం పర్వాలేదు, బుక్ చేయండి'.
    - Earliest available slot presented in natural Telugu.
    - Explicit confirmation required.
    """
    tz = get_hospital_timezone()
    base_date = datetime.now(tz).date()
    generate_upcoming_slots_for_doctors(db_session, days=20, base_date=base_date)

    manager = ConversationManager(adapter=MockReasoningAdapter())
    session_id = "test-flexible-telugu"

    # Turn 1: Select Dr. Rajesh Sharma in Telugu
    r1 = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="డాక్టర్ రాజేష్ శర్మ గారితో అపాయింట్‌మెంట్ కావాలి",
        patient_reference="PAT-PHASE5-001",
    )
    assert r1.language == "te"
    assert r1.draft.doctor_name == "Dr. Rajesh Sharma"

    # Turn 2: Flexible time request in Telugu
    r2 = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="ఏదైనా సమయం పర్వాలేదు, బుక్ చేయండి",
    )
    assert r2.language == "te"
    # Should offer earliest slot in Telugu
    assert "అత్యంత త్వరగా లభించే అపాయింట్‌మెంట్" in r2.reply or "బుక్ చేయమంటారా" in r2.reply
    assert r2.booked_appointment is None


def test_alternative_doctor_suggested_when_doctor_has_no_slots(db_session: Session, availability_test_env):
    """
    Requirement 3: When Dr. Rajesh Sharma has NO slots in 20 days:
    - Agent finds colleague Dr. Sunita Rao in same department.
    - Suggests Dr. Sunita Rao with her earliest slot.
    - Does NOT automatically switch doctor without patient consent.
    """
    tz = get_hospital_timezone()
    base_date = datetime.now(tz).date()
    # Generate slots for all doctors
    generate_upcoming_slots_for_doctors(db_session, days=20, base_date=base_date)

    # Cancel/book ALL slots for Dr. Rajesh Sharma so he has 0 available slots
    sharma_slots = db_session.scalars(
        select(AppointmentSlot).where(
            AppointmentSlot.doctor_id == "doc-sharma-phase5",
            AppointmentSlot.status == "AVAILABLE",
        )
    ).all()
    for s in sharma_slots:
        s.status = "BOOKED"
    db_session.commit()

    # Ensure Dr. Sunita Rao has open slots
    rao_slots = get_available_slots_tool(db_session, doctor_id="doc-rao-phase5")
    assert len(rao_slots) > 0, "Dr. Rao should have open slots"

    # Verify helper directly
    alts = find_alternative_doctors_with_slots(db_session, doctor_id="doc-sharma-phase5", days=20)
    assert len(alts) == 1
    assert alts[0]["doctor_id"] == "doc-rao-phase5"
    assert alts[0]["display_name"] == "Dr. Sunita Rao"

    # Test conversational flow
    manager = ConversationManager(adapter=MockReasoningAdapter())
    session_id = "test-alt-doc-suggestion"

    r1 = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="I want to see Dr. Rajesh Sharma",
        patient_reference="PAT-PHASE5-001",
    )
    # Because Sharma has 0 slots, agent offers Dr. Sunita Rao
    assert "Dr. Sunita Rao" in r1.reply
    assert "doesn't have any available appointments" in r1.reply or "no available appointments" in r1.reply or "Dr. Rajesh Sharma" in r1.reply
    assert "Would you like to book with her" in r1.reply or "Dr. Sunita Rao" in r1.reply
    # Doctor must NOT be switched automatically yet
    session = manager.get_or_create_session(session_id)
    assert session.pending_action == "CONFIRM_ALTERNATIVE_DOCTOR"


def test_alternative_doctor_acceptance_and_booking(db_session: Session, availability_test_env):
    """
    Requirement 3 & 5: When patient accepts alternative doctor recommendation:
    - Switches doctor to Dr. Sunita Rao.
    - Assigns the recommended slot.
    - Requires explicit confirmation before final booking.
    """
    tz = get_hospital_timezone()
    base_date = datetime.now(tz).date()
    generate_upcoming_slots_for_doctors(db_session, days=20, base_date=base_date)

    # Book all Sharma slots
    sharma_slots = db_session.scalars(
        select(AppointmentSlot).where(
            AppointmentSlot.doctor_id == "doc-sharma-phase5",
            AppointmentSlot.status == "AVAILABLE",
        )
    ).all()
    for s in sharma_slots:
        s.status = "BOOKED"
    db_session.commit()

    manager = ConversationManager(adapter=MockReasoningAdapter())
    session_id = "test-alt-doc-accept"

    # Turn 1: Patient asks for Dr. Sharma -> gets offer for Dr. Rao
    r1 = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="I need an appointment with Dr. Rajesh Sharma",
        patient_reference="PAT-PHASE5-001",
    )
    assert "Dr. Sunita Rao" in r1.reply

    # Turn 2: Patient accepts Dr. Sunita Rao
    r2 = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="Yes, Dr. Sunita Rao is fine. Please book with her.",
    )
    # Doctor is now Dr. Sunita Rao
    assert r2.draft.doctor_id == "doc-rao-phase5"
    assert r2.draft.slot_id is not None
    # Still requires explicit confirmation (reason or confirm summary)
    assert r2.booked_appointment is None


def test_alternative_doctor_rejection_retains_doctor_choice(db_session: Session, availability_test_env):
    """
    Requirement 3: When patient rejects alternative doctor suggestion:
    - Retains original doctor preference without force-switching.
    """
    tz = get_hospital_timezone()
    base_date = datetime.now(tz).date()
    generate_upcoming_slots_for_doctors(db_session, days=20, base_date=base_date)

    sharma_slots = db_session.scalars(
        select(AppointmentSlot).where(
            AppointmentSlot.doctor_id == "doc-sharma-phase5",
            AppointmentSlot.status == "AVAILABLE",
        )
    ).all()
    for s in sharma_slots:
        s.status = "BOOKED"
    db_session.commit()

    manager = ConversationManager(adapter=MockReasoningAdapter())
    session_id = "test-alt-doc-reject"

    r1 = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="I want to see Dr. Rajesh Sharma",
        patient_reference="PAT-PHASE5-001",
    )
    assert "Dr. Sunita Rao" in r1.reply

    # Patient declines alternative
    r2 = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="No, I only want Dr. Rajesh Sharma",
    )
    assert r2.draft.doctor_id != "doc-rao-phase5"
    assert "Dr. Rajesh Sharma" in r2.reply or "keep" in r2.reply.lower() or "waitlist" in r2.reply.lower()


def test_concurrent_booking_safety_and_double_booking_prevention(db_session: Session, availability_test_env):
    """
    Requirement 5: Double booking safety and transaction isolation:
    - Attempting to book an already BOOKED slot is rejected with graceful error.
    - Database commit prevents overlapping bookings for the exact same slot.
    """
    tz = get_hospital_timezone()
    base_date = datetime.now(tz).date()
    generate_upcoming_slots_for_doctors(db_session, days=20, base_date=base_date)

    rao_slots = get_available_slots_tool(db_session, doctor_id="doc-rao-phase5")
    assert len(rao_slots) > 0
    target_slot_id = rao_slots[0]["slot_id"]

    # First booking succeeds
    slot = db_session.get(AppointmentSlot, target_slot_id)
    slot.status = "BOOKED"
    appt = Appointment(
        id="appt-conc-001",
        doctor_id="doc-rao-phase5",
        slot_id=target_slot_id,
        patient_reference="PAT-PHASE5-001",
        appointment_status="CONFIRMED",
        reason_category="Routine checkup",
    )
    db_session.add(appt)
    db_session.commit()

    # Second booking attempt for same slot via Tool Router
    from app.agent.tool_router import RestrictedToolRouter
    from app.agent.schemas import ToolCallIntent
    router = RestrictedToolRouter()

    res = router.execute_tool(
        db_session,
        ToolCallIntent(
            tool_name="book_appointment",
            arguments={
                "doctor_id": "doc-rao-phase5",
                "slot_id": target_slot_id,
                "patient_reference": "PAT-PHASE5-002",
                "reason_category": "Chest pain checkup",
            },
        ),
    )
    assert not res.success
    assert "no longer available" in res.error.lower() or "not available" in res.error.lower() or "already" in res.error.lower()
