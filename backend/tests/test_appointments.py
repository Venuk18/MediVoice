from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from app.models.appointment_slot import AppointmentSlot
from app.models.appointment import Appointment
from app.models.audit_event import AuditEvent
from app.services.appointment_service import book_appointment_tool


def test_successful_appointment_booking(client, db_session, seeded_hospital_data):
    doc_id = seeded_hospital_data["doc_sharma"].id
    slot_id = seeded_hospital_data["slot_available"].id

    payload = {
        "patient_reference": "PAT-TEST-100",
        "doctor_id": doc_id,
        "slot_id": slot_id,
        "reason_category": "Annual Cardiac Checkup",
    }

    response = client.post("/api/v1/appointments", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["patient_reference"] == "PAT-TEST-100"
    assert data["doctor_id"] == doc_id
    assert data["slot_id"] == slot_id
    assert data["appointment_status"] == "CONFIRMED"
    assert data["doctor_name"] == "Dr. Rajesh Sharma"

    # Verify slot status transitioned to BOOKED in DB
    slot = db_session.scalars(select(AppointmentSlot).where(AppointmentSlot.id == slot_id)).first()
    assert slot.status == "BOOKED"

    # Verify AuditEvent was created
    audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "Appointment",
            AuditEvent.entity_id == data["id"],
            AuditEvent.action == "APPOINTMENT_BOOKED",
        )
    ).first()
    assert audit is not None
    assert audit.actor_reference == "API_CLIENT"


def test_rejection_of_unavailable_slot(client, seeded_hospital_data):
    doc_id = seeded_hospital_data["doc_sharma"].id
    slot_id = seeded_hospital_data["slot_booked"].id  # already booked

    payload = {
        "patient_reference": "PAT-TEST-200",
        "doctor_id": doc_id,
        "slot_id": slot_id,
        "reason_category": "Second Opinion",
    }

    response = client.post("/api/v1/appointments", json=payload)
    assert response.status_code == 409
    assert "no longer available" in response.json()["detail"].lower()


def test_prevention_of_double_booking_same_slot(client, seeded_hospital_data):
    doc_id = seeded_hospital_data["doc_sharma"].id
    slot_id = seeded_hospital_data["slot_available_2"].id

    payload = {
        "patient_reference": "PAT-FIRST",
        "doctor_id": doc_id,
        "slot_id": slot_id,
        "reason_category": "First Booking",
    }
    # First booking succeeds
    res1 = client.post("/api/v1/appointments", json=payload)
    assert res1.status_code == 201

    # Second concurrent/repeated attempt for same slot MUST be rejected
    payload_second = {
        "patient_reference": "PAT-SECOND",
        "doctor_id": doc_id,
        "slot_id": slot_id,
        "reason_category": "Duplicate Attempt",
    }
    res2 = client.post("/api/v1/appointments", json=payload_second)
    assert res2.status_code == 409
    assert "no longer available" in res2.json()["detail"].lower() or "conflict" in res2.json()["detail"].lower()


def test_validation_of_doctor_slot_ownership(client, seeded_hospital_data):
    # Dr. Sharma trying to book Dr. Nair's slot
    doc_sharma_id = seeded_hospital_data["doc_sharma"].id
    slot_nair_id = seeded_hospital_data["slot_nair"].id

    payload = {
        "patient_reference": "PAT-TEST-300",
        "doctor_id": doc_sharma_id,
        "slot_id": slot_nair_id,
        "reason_category": "Consultation",
    }

    response = client.post("/api/v1/appointments", json=payload)
    assert response.status_code == 400
    assert "does not belong" in response.json()["detail"].lower()


def test_rejection_of_past_slot(client, seeded_hospital_data):
    doc_id = seeded_hospital_data["doc_sharma"].id
    slot_past_id = seeded_hospital_data["slot_past"].id

    payload = {
        "patient_reference": "PAT-TEST-PAST",
        "doctor_id": doc_id,
        "slot_id": slot_past_id,
        "reason_category": "Past slot attempt",
    }

    response = client.post("/api/v1/appointments", json=payload)
    assert response.status_code == 400
    assert "in the past" in response.json()["detail"].lower()


def test_rejection_of_inactive_doctor(client, seeded_hospital_data):
    doc_inactive_id = seeded_hospital_data["doc_inactive"].id
    slot_id = seeded_hospital_data["slot_available_2"].id

    payload = {
        "patient_reference": "PAT-INACTIVE-TEST",
        "doctor_id": doc_inactive_id,
        "slot_id": slot_id,
        "reason_category": "Consultation",
    }

    response = client.post("/api/v1/appointments", json=payload)
    assert response.status_code == 400
    assert "inactive" in response.json()["detail"].lower()


def test_appointment_cancellation_and_slot_release(client, db_session, seeded_hospital_data):
    appt_id = seeded_hospital_data["existing_appt"].id
    slot_id = seeded_hospital_data["slot_booked"].id

    # Ensure initial state is BOOKED
    slot = db_session.scalars(select(AppointmentSlot).where(AppointmentSlot.id == slot_id)).first()
    assert slot.status == "BOOKED"

    # Cancel appointment
    response = client.post(
        f"/api/v1/appointments/{appt_id}/cancel",
        json={"cancellation_reason": "Patient requested reschedule"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["appointment_status"] == "CANCELLED"

    # Verify slot was released back to AVAILABLE
    db_session.expire_all()
    slot_after = db_session.scalars(select(AppointmentSlot).where(AppointmentSlot.id == slot_id)).first()
    assert slot_after.status == "AVAILABLE"

    # Verify audit event
    audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "Appointment",
            AuditEvent.entity_id == appt_id,
            AuditEvent.action == "APPOINTMENT_CANCELLED",
        )
    ).first()
    assert audit is not None


def test_appointment_completion(client, db_session, seeded_hospital_data):
    appt_id = seeded_hospital_data["existing_appt"].id

    response = client.post(
        f"/api/v1/appointments/{appt_id}/complete",
        json={"notes": "Patient attended consultation smoothly"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["appointment_status"] == "COMPLETED"
    assert data["visit_completed_at"] is not None

    # Verify audit event
    audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "Appointment",
            AuditEvent.entity_id == appt_id,
            AuditEvent.action == "APPOINTMENT_COMPLETED",
        )
    ).first()
    assert audit is not None


def test_follow_up_recommendation_recording(client, db_session, seeded_hospital_data):
    appt_id = seeded_hospital_data["existing_appt"].id
    follow_up_time = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()

    payload = {
        "follow_up_date": follow_up_time,
        "follow_up_notes": "Repeat lipid profile in 14 days and review fasting glucose.",
    }

    response = client.post(f"/api/v1/appointments/{appt_id}/follow-up", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["follow_up_recommended"] is True
    assert data["follow_up_notes"] == payload["follow_up_notes"]

    # Verify in DB
    db_session.expire_all()
    appt_db = db_session.scalars(select(Appointment).where(Appointment.id == appt_id)).first()
    assert appt_db.follow_up_recommended is True

    # Verify audit event
    audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "Appointment",
            AuditEvent.entity_id == appt_id,
            AuditEvent.action == "FOLLOW_UP_RECORDED",
        )
    ).first()
    assert audit is not None


def test_ai_tool_book_appointment(db_session, seeded_hospital_data):
    doc_id = seeded_hospital_data["doc_sharma"].id
    slot_id = seeded_hospital_data["slot_available_2"].id

    result = book_appointment_tool(
        db=db_session,
        patient_reference="PAT-AI-VOICE-01",
        doctor_id=doc_id,
        selected_slot_id=slot_id,
        reason_category="Voice AI booking",
    )
    assert result["appointment_id"] is not None
    assert result["patient_reference"] == "PAT-AI-VOICE-01"
    assert result["appointment_status"] == "CONFIRMED"
    assert result["doctor_name"] == "Dr. Rajesh Sharma"
