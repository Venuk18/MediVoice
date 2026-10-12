from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class AppointmentCreate(BaseModel):
    """
    Client booking request.
    Notice: appointment_status is NOT accepted from the client; server controls initial status (CONFIRMED).
    """
    patient_reference: str = Field(..., min_length=3, max_length=100, description="Synthetic patient identifier, e.g. PAT-1002")
    doctor_id: str = Field(..., description="Target doctor UUID")
    slot_id: str = Field(..., description="Target appointment slot UUID")
    reason_category: str = Field(..., min_length=2, max_length=100, description="Operational reason category, e.g. Routine Consultation, Follow-up")


class AppointmentCancelRequest(BaseModel):
    cancellation_reason: Optional[str] = Field(default="Patient requested cancellation", max_length=255)


class AppointmentCompleteRequest(BaseModel):
    """Operational visit completion. Clinical notes are strictly omitted from scope."""
    notes: Optional[str] = Field(default=None, max_length=255, description="Operational visit completion note only")


class AppointmentFollowUpRequest(BaseModel):
    """
    Doctor-recommended follow-up schedule and operational note.
    Does not automatically book or confirm the next slot.
    """
    follow_up_date: datetime = Field(..., description="Recommended date for next review")
    follow_up_notes: str = Field(..., min_length=3, max_length=500, description="Operational follow-up instructions")


class AppointmentRead(BaseModel):
    id: str
    patient_reference: str
    doctor_id: str
    slot_id: str
    appointment_status: str
    reason_category: str
    created_at: datetime
    updated_at: datetime
    visit_completed_at: Optional[datetime] = None
    follow_up_recommended: bool = False
    follow_up_date: Optional[datetime] = None
    follow_up_notes: Optional[str] = None

    # Enriched presentation fields
    doctor_name: Optional[str] = None
    doctor_specialty: Optional[str] = None
    slot_start_time: Optional[datetime] = None
    slot_end_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
