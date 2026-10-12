from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.doctor import DoctorRead, AppointmentSlotRead
from app.services import doctor_service

router = APIRouter(prefix="/doctors", tags=["Doctors"])


@router.get("", response_model=List[DoctorRead], summary="List and filter doctors")
def list_doctors(
    specialty: Optional[str] = Query(None, description="Filter by clinical specialty (e.g., Cardiology)"),
    department_id: Optional[str] = Query(None, description="Filter by department ID"),
    department_name: Optional[str] = Query(None, description="Filter by department name (e.g., Pediatrics)"),
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    db: Session = Depends(get_db),
):
    """Retrieve list of active physicians with optional filtering."""
    doctors = doctor_service.get_doctors(
        db=db,
        specialty=specialty,
        department_id=department_id,
        department_name=department_name,
        hospital_id=hospital_id,
    )
    # Enrich department_name and hospital_name for response
    results = []
    for doc in doctors:
        doc_read = DoctorRead(
            id=doc.id,
            hospital_id=doc.hospital_id,
            department_id=doc.department_id,
            display_name=doc.display_name,
            specialty=doc.specialty,
            is_active=doc.is_active,
            created_at=doc.created_at,
            department_name=doc.department.name if doc.department else None,
            hospital_name=doc.hospital.name if doc.hospital else None,
        )
        results.append(doc_read)
    return results


@router.get("/{doctor_id}", response_model=DoctorRead, summary="Get doctor details")
def get_doctor(doctor_id: str, db: Session = Depends(get_db)):
    """Retrieve detailed physician profile."""
    doc = doctor_service.get_doctor_by_id(db, doctor_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Doctor with ID '{doctor_id}' not found.",
        )
    return DoctorRead(
        id=doc.id,
        hospital_id=doc.hospital_id,
        department_id=doc.department_id,
        display_name=doc.display_name,
        specialty=doc.specialty,
        is_active=doc.is_active,
        created_at=doc.created_at,
        department_name=doc.department.name if doc.department else None,
        hospital_name=doc.hospital.name if doc.hospital else None,
    )


@router.get("/{doctor_id}/slots", response_model=List[AppointmentSlotRead], summary="Get available doctor appointment slots")
def get_doctor_slots(
    doctor_id: str,
    date: Optional[str] = Query(None, description="Target date in YYYY-MM-DD format"),
    start_date: Optional[datetime] = Query(None, description="Slot start range filter"),
    end_date: Optional[datetime] = Query(None, description="Slot end range filter"),
    time_range: Optional[str] = Query(None, description="Time of day filter: 'morning', 'afternoon', 'evening'"),
    db: Session = Depends(get_db),
):
    """
    Retrieve open, unbooked appointment slots for a specific doctor.
    Guarantees only AVAILABLE slots are returned.
    """
    doc = doctor_service.get_doctor_by_id(db, doctor_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Doctor with ID '{doctor_id}' not found.",
        )

    # Use AI tool ready helper for flexible date/time filtering
    if date or time_range:
        tool_slots = doctor_service.get_available_slots_tool(
            db=db,
            doctor_id=doctor_id,
            requested_date=date,
            time_range=time_range,
        )
        # Fetch the actual slots to map cleanly
        slot_ids = [s["slot_id"] for s in tool_slots]
        all_slots = doctor_service.get_available_slots(db, doctor_id=doctor_id)
        return [s for s in all_slots if s.id in slot_ids]

    return doctor_service.get_available_slots(
        db=db,
        doctor_id=doctor_id,
        start_date=start_date,
        end_date=end_date,
    )
