from datetime import datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import StaffRole, require_staff_roles
from app.db.session import get_db
from app.schemas.doctor import (
    AppointmentSlotRead,
    DoctorManageCreate,
    DoctorRead,
    DoctorSlotCreateRequest,
)
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


@router.post(
    "",
    response_model=DoctorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new doctor to the hospital directory",
)
def create_doctor(
    payload: DoctorManageCreate,
    db: Session = Depends(get_db),
    staff: Optional[Dict[str, Optional[str]]] = Depends(
        require_staff_roles([StaffRole.MAINTENANCE_STAFF, StaffRole.ADMIN])
    ),
):
    """Create a new active physician record and seed initial appointment slots."""
    actor = f"{staff.get('username')}:{staff.get('role')}" if staff else "MAINTENANCE_ADMIN"
    doc = doctor_service.create_doctor_with_slots(db=db, payload=payload, actor_reference=actor)
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


@router.delete(
    "/{doctor_id}",
    response_model=DoctorRead,
    summary="Remove (deactivate) a doctor from the active directory",
)
def remove_doctor(
    doctor_id: str,
    db: Session = Depends(get_db),
    staff: Optional[Dict[str, Optional[str]]] = Depends(
        require_staff_roles([StaffRole.MAINTENANCE_STAFF, StaffRole.ADMIN])
    ),
):
    """Deactivates a physician from the active hospital roster."""
    actor = f"{staff.get('username')}:{staff.get('role')}" if staff else "MAINTENANCE_ADMIN"
    doc = doctor_service.deactivate_doctor(db=db, doctor_id=doctor_id, actor_reference=actor)
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

    if date or time_range:
        tool_slots = doctor_service.get_available_slots_tool(
            db=db,
            doctor_id=doctor_id,
            requested_date=date,
            time_range=time_range,
        )
        slot_ids = [s["slot_id"] for s in tool_slots]
        all_slots = doctor_service.get_available_slots(db, doctor_id=doctor_id)
        return [s for s in all_slots if s.id in slot_ids]

    return doctor_service.get_available_slots(
        db=db,
        doctor_id=doctor_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.post(
    "/{doctor_id}/slots",
    response_model=AppointmentSlotRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new available appointment slot for a doctor",
)
def add_doctor_slot(
    doctor_id: str,
    payload: DoctorSlotCreateRequest,
    db: Session = Depends(get_db),
    staff: Optional[Dict[str, Optional[str]]] = Depends(
        require_staff_roles([StaffRole.DOCTOR, StaffRole.MAINTENANCE_STAFF, StaffRole.ADMIN])
    ),
):
    """Add an open appointment slot for a specific physician."""
    actor = f"{staff.get('username')}:{staff.get('role')}" if staff else "DOCTOR_PORTAL"
    return doctor_service.create_doctor_slot(
        db=db,
        doctor_id=doctor_id,
        payload=payload,
        actor_reference=actor,
    )


