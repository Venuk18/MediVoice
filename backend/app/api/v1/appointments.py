from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentRead,
    AppointmentCancelRequest,
    AppointmentCompleteRequest,
    AppointmentFollowUpRequest,
)
from app.services import appointment_service

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def _to_appointment_read(appt) -> AppointmentRead:
    return AppointmentRead(
        id=appt.id,
        patient_reference=appt.patient_reference,
        doctor_id=appt.doctor_id,
        slot_id=appt.slot_id,
        appointment_status=appt.appointment_status,
        reason_category=appt.reason_category,
        created_at=appt.created_at,
        updated_at=appt.updated_at,
        visit_completed_at=appt.visit_completed_at,
        follow_up_recommended=appt.follow_up_recommended,
        follow_up_date=appt.follow_up_date,
        follow_up_notes=appt.follow_up_notes,
        doctor_name=appt.doctor.display_name if appt.doctor else None,
        doctor_specialty=appt.doctor.specialty if appt.doctor else None,
        slot_start_time=appt.slot.start_time if appt.slot else None,
        slot_end_time=appt.slot.end_time if appt.slot else None,
    )


@router.post(
    "",
    response_model=AppointmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Book an appointment",
)
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
):
    """
    Transaction-safe appointment booking:
    - Validates doctor and slot
    - Validates slot availability & future time
    - Server sets initial status (CONFIRMED)
    - Concurrency-safe slot lock and double-booking prevention
    - Commits transaction & logs audit event
    """
    appt = appointment_service.book_appointment(
        db=db,
        patient_reference=payload.patient_reference,
        doctor_id=payload.doctor_id,
        slot_id=payload.slot_id,
        reason_category=payload.reason_category,
        actor_reference="API_CLIENT",
    )
    return _to_appointment_read(appt)


@router.get("", response_model=List[AppointmentRead], summary="List and filter appointments")
def list_appointments(
    doctor_id: Optional[str] = Query(None, description="Filter by doctor ID"),
    patient_reference: Optional[str] = Query(None, description="Filter by synthetic patient reference"),
    status: Optional[str] = Query(None, description="Filter by status (CONFIRMED, COMPLETED, CANCELLED)"),
    date: Optional[datetime] = Query(None, description="Filter by date"),
    db: Session = Depends(get_db),
):
    """Retrieve appointments with optional filters."""
    appts = appointment_service.get_appointments(
        db=db,
        doctor_id=doctor_id,
        patient_reference=patient_reference,
        appointment_status=status,
        date_filter=date,
    )
    return [_to_appointment_read(a) for a in appts]


@router.get("/{appointment_id}", response_model=AppointmentRead, summary="Get appointment by ID")
def get_appointment(appointment_id: str, db: Session = Depends(get_db)):
    """Retrieve single appointment by identifier."""
    appt = appointment_service.get_appointment_by_id(db, appointment_id)
    if not appt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment with ID '{appointment_id}' not found.",
        )
    return _to_appointment_read(appt)


@router.post("/{appointment_id}/cancel", response_model=AppointmentRead, summary="Cancel an appointment")
def cancel_appointment_endpoint(
    appointment_id: str,
    payload: Optional[AppointmentCancelRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Controlled cancellation:
    - Updates appointment status to CANCELLED
    - Releases the slot back to AVAILABLE
    - Logs audit trail
    """
    reason = payload.cancellation_reason if payload else "Patient requested"
    appt = appointment_service.cancel_appointment(
        db=db,
        appointment_id=appointment_id,
        cancellation_reason=reason,
        actor_reference="API_CLIENT",
    )
    return _to_appointment_read(appt)


@router.post("/{appointment_id}/complete", response_model=AppointmentRead, summary="Complete appointment visit")
def complete_appointment_endpoint(
    appointment_id: str,
    payload: Optional[AppointmentCompleteRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Marks operational visit as completed.
    Clinical notes are excluded; only operational completion status is recorded.
    """
    notes = payload.notes if payload else "Visit concluded"
    appt = appointment_service.complete_appointment(
        db=db,
        appointment_id=appointment_id,
        operational_notes=notes,
        actor_reference="DOCTOR_DASHBOARD",
    )
    return _to_appointment_read(appt)


@router.post("/{appointment_id}/follow-up", response_model=AppointmentRead, summary="Record follow-up recommendation")
def record_follow_up_endpoint(
    appointment_id: str,
    payload: AppointmentFollowUpRequest,
    db: Session = Depends(get_db),
):
    """
    Records doctor-recommended follow-up date and operational instructions.
    Does NOT automatically create or book a subsequent appointment.
    """
    appt = appointment_service.record_follow_up(
        db=db,
        appointment_id=appointment_id,
        follow_up_date=payload.follow_up_date,
        follow_up_notes=payload.follow_up_notes,
        actor_reference="DOCTOR_DASHBOARD",
    )
    return _to_appointment_read(appt)
