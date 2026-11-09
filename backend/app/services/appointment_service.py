import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError

from app.models.doctor import Doctor
from app.models.appointment_slot import AppointmentSlot
from app.models.appointment import Appointment
from app.models.audit_event import AuditEvent
from app.models.patient import Patient


def get_appointment_by_id(db: Session, appointment_id: str) -> Optional[Appointment]:
    query = (
        select(Appointment)
        .options(
            joinedload(Appointment.doctor),
            joinedload(Appointment.slot),
        )
        .where(Appointment.id == appointment_id)
    )
    return db.scalars(query).first()


def get_appointments(
    db: Session,
    doctor_id: Optional[str] = None,
    patient_reference: Optional[str] = None,
    appointment_status: Optional[str] = None,
    date_filter: Optional[datetime] = None,
) -> List[Appointment]:
    query = (
        select(Appointment)
        .options(
            joinedload(Appointment.doctor),
            joinedload(Appointment.slot),
        )
    )

    if doctor_id:
        query = query.where(Appointment.doctor_id == doctor_id)
    if patient_reference:
        query = query.where(Appointment.patient_reference == patient_reference)
    if appointment_status:
        query = query.where(Appointment.appointment_status == appointment_status)

    query = query.order_by(Appointment.created_at.desc())
    results = list(db.scalars(query).all())

    if date_filter:
        target_date_str = date_filter.strftime("%Y-%m-%d")
        results = [
            a for a in results
            if a.slot and a.slot.start_time.strftime("%Y-%m-%d") == target_date_str
        ]

    return results


def book_appointment(
    db: Session,
    patient_reference: str,
    doctor_id: str,
    slot_id: str,
    reason_category: str,
    actor_reference: str = "PATIENT_PORTAL",
) -> Appointment:
    """
    Transaction-safe appointment booking with multi-tier validation:
    1. Doctor existence & active status validation.
    2. Slot existence & doctor ownership verification.
    3. Availability check & future slot validation.
    4. Concurrency lock (FOR UPDATE where supported) & atomic status update to BOOKED.
    5. Database unique constraint enforcement on slot_id to prevent double bookings.
    6. Audit event generation inside the same commit unit.
    """
    # Normalize current time
    now_utc = datetime.now(timezone.utc)

    try:
        # Validate doctor
        doctor = db.scalars(select(Doctor).where(Doctor.id == doctor_id)).first()
        if not doctor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Doctor with ID '{doctor_id}' does not exist.",
            )
        if not doctor.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Doctor '{doctor.display_name}' is currently inactive.",
            )

        # Slot query with row-locking when dialect supports FOR UPDATE (e.g., PostgreSQL)
        is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"
        slot_query = select(AppointmentSlot).where(AppointmentSlot.id == slot_id)
        if not is_sqlite:
            slot_query = slot_query.with_for_update()

        slot = db.scalars(slot_query).first()
        if not slot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Appointment slot with ID '{slot_id}' not found.",
            )

        # Validate doctor-slot ownership
        if slot.doctor_id != doctor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slot does not belong to the selected doctor.",
            )

        # Validate slot availability
        if slot.status != "AVAILABLE":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Slot is no longer available (current status: '{slot.status}').",
            )

        # Validate slot is not in the past
        slot_start = slot.start_time
        if slot_start.tzinfo is None:
            # Handle naive datetime as UTC for comparison
            slot_start = slot_start.replace(tzinfo=timezone.utc)
        if slot_start < now_utc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot book an appointment slot in the past.",
            )

        # Check if slot already has an active appointment
        existing_appt = db.scalars(
            select(Appointment).where(
                Appointment.slot_id == slot_id,
                Appointment.appointment_status.in_(["CONFIRMED", "COMPLETED"]),
            )
        ).first()
        if existing_appt:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Slot is already reserved by another appointment.",
            )

        # Transition slot status atomically
        slot.status = "BOOKED"

        # Create new appointment with server-enforced initial status
        appointment = Appointment(
            patient_reference=patient_reference.strip(),
            doctor_id=doctor_id,
            slot_id=slot_id,
            appointment_status="CONFIRMED",
            reason_category=reason_category.strip(),
            follow_up_recommended=False,
        )
        db.add(appointment)
        db.flush()  # Flush to generate appointment.id and verify unique constraints

        # Create audit event inside the same transaction
        audit_details = json.dumps({
            "patient_reference": appointment.patient_reference,
            "doctor_id": doctor_id,
            "doctor_name": doctor.display_name,
            "slot_id": slot_id,
            "slot_start": slot.start_time.isoformat(),
            "reason_category": appointment.reason_category,
        })
        audit = AuditEvent(
            actor_reference=actor_reference,
            action="APPOINTMENT_BOOKED",
            entity_type="Appointment",
            entity_id=appointment.id,
            details=audit_details,
        )
        db.add(audit)

        # Commit transaction atomically
        db.commit()
        db.refresh(appointment)
        return appointment

    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict: Slot has already been reserved concurrently by another transaction.",
        ) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during appointment booking: {str(exc)}",
        ) from exc


def cancel_appointment(
    db: Session,
    appointment_id: str,
    cancellation_reason: Optional[str] = None,
    actor_reference: str = "PATIENT_PORTAL",
) -> Appointment:
    """Cancels an appointment and re-releases the slot to AVAILABLE with concurrency row locking."""
    is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"
    appt_query = select(Appointment).where(Appointment.id == appointment_id)
    if not is_sqlite:
        appt_query = appt_query.with_for_update()

    appointment = db.scalars(appt_query).first()
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment '{appointment_id}' not found.",
        )

    if appointment.appointment_status == "CANCELLED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Appointment is already cancelled.",
        )

    if appointment.appointment_status == "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel an appointment that has already been marked completed.",
        )

    try:
        appointment.appointment_status = "CANCELLED"
        if appointment.slot_id:
            slot_query = select(AppointmentSlot).where(AppointmentSlot.id == appointment.slot_id)
            if not is_sqlite:
                slot_query = slot_query.with_for_update()
            slot = db.scalars(slot_query).first()
            if slot:
                slot.status = "AVAILABLE"

        audit_details = json.dumps({
            "cancellation_reason": cancellation_reason or "Patient requested",
            "released_slot_id": appointment.slot_id,
        })
        audit = AuditEvent(
            actor_reference=actor_reference,
            action="APPOINTMENT_CANCELLED",
            entity_type="Appointment",
            entity_id=appointment.id,
            details=audit_details,
        )
        db.add(audit)
        db.commit()
        db.refresh(appointment)
        return appointment
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel appointment: {str(exc)}",
        ) from exc


def complete_appointment(
    db: Session,
    appointment_id: str,
    operational_notes: Optional[str] = None,
    actor_reference: str = "DOCTOR_DASHBOARD",
) -> Appointment:
    """Marks the visit completed. Does not accept fabricated clinical notes."""
    appointment = get_appointment_by_id(db, appointment_id)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment '{appointment_id}' not found.",
        )

    if appointment.appointment_status == "CANCELLED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot complete a cancelled appointment.",
        )

    try:
        appointment.appointment_status = "COMPLETED"
        appointment.visit_completed_at = datetime.now(timezone.utc)

        audit_details = json.dumps({
            "operational_notes": operational_notes or "Visit concluded",
            "visit_completed_at": appointment.visit_completed_at.isoformat(),
        })
        audit = AuditEvent(
            actor_reference=actor_reference,
            action="APPOINTMENT_COMPLETED",
            entity_type="Appointment",
            entity_id=appointment.id,
            details=audit_details,
        )
        db.add(audit)
        db.commit()
        db.refresh(appointment)
        return appointment
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete appointment: {str(exc)}",
        ) from exc


def record_follow_up(
    db: Session,
    appointment_id: str,
    follow_up_date: datetime,
    follow_up_notes: str,
    actor_reference: str = "DOCTOR_DASHBOARD",
) -> Appointment:
    """
    Records follow-up recommendation and operational note.
    Does NOT auto-book a slot (separate booking workflow required).
    """
    appointment = get_appointment_by_id(db, appointment_id)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment '{appointment_id}' not found.",
        )

    try:
        appointment.follow_up_recommended = True
        appointment.follow_up_date = follow_up_date
        appointment.follow_up_notes = follow_up_notes.strip()

        audit_details = json.dumps({
            "follow_up_date": follow_up_date.isoformat(),
            "follow_up_notes": follow_up_notes,
        })
        audit = AuditEvent(
            actor_reference=actor_reference,
            action="FOLLOW_UP_RECORDED",
            entity_type="Appointment",
            entity_id=appointment.id,
            details=audit_details,
        )
        db.add(audit)
        db.commit()
        db.refresh(appointment)
        return appointment
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record follow-up: {str(exc)}",
        ) from exc


# ==============================================================================
# AI Tool Interfaces (Section 9: Typed Python Service Functions)
# ==============================================================================

def book_appointment_tool(
    db: Session,
    patient_reference: str,
    doctor_id: str,
    selected_slot_id: str,
    reason_category: str,
) -> Dict[str, Any]:
    """
    AI Tool: book_appointment
    Executes transaction-safe appointment booking via strict backend validation.
    The AI orchestrator cannot pass custom status or override safety checks.
    """
    appt = book_appointment(
        db=db,
        patient_reference=patient_reference,
        doctor_id=doctor_id,
        slot_id=selected_slot_id,
        reason_category=reason_category,
        actor_reference="AI_VOICE_AGENT",
    )

    patient = db.scalars(select(Patient).where(Patient.patient_reference == appt.patient_reference)).first()
    patient_name = patient.full_name if patient else "Valued Patient"
    phone_number = patient.phone_number if patient else ""

    dept_name = (
        appt.doctor.department.name
        if appt.doctor and getattr(appt.doctor, "department", None)
        else (appt.doctor.specialty if appt.doctor else "General Medicine")
    )
    hosp_name = (
        appt.doctor.hospital.name
        if appt.doctor and getattr(appt.doctor, "hospital", None)
        else "Aarogya One Hospital"
    )

    return {
        "appointment_id": appt.id,
        "patient_reference": appt.patient_reference,
        "patient_name": patient_name,
        "phone_number": phone_number,
        "doctor_id": appt.doctor_id,
        "doctor_name": appt.doctor.display_name if appt.doctor else "",
        "department_name": dept_name,
        "hospital_name": hosp_name,
        "slot_id": appt.slot_id,
        "appointment_start_time": appt.slot.start_time.isoformat() if appt.slot else "",
        "appointment_status": appt.appointment_status,
        "reason_category": appt.reason_category,
    }
