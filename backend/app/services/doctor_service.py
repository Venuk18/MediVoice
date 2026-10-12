from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, and_, or_
from app.models.hospital import Hospital
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.appointment_slot import AppointmentSlot


def get_hospitals(db: Session, is_active: Optional[bool] = True) -> List[Hospital]:
    query = select(Hospital)
    if is_active is not None:
        query = query.where(Hospital.is_active == is_active)
    return list(db.scalars(query).all())


def get_hospital_by_id(db: Session, hospital_id: str) -> Optional[Hospital]:
    query = (
        select(Hospital)
        .options(joinedload(Hospital.departments))
        .where(Hospital.id == hospital_id)
    )
    return db.scalars(query).first()


def get_doctors(
    db: Session,
    specialty: Optional[str] = None,
    department_id: Optional[str] = None,
    department_name: Optional[str] = None,
    hospital_id: Optional[str] = None,
    is_active: bool = True,
) -> List[Doctor]:
    """Retrieve doctors with flexible multi-field filtering."""
    query = (
        select(Doctor)
        .join(Department, Doctor.department_id == Department.id)
        .options(joinedload(Doctor.department), joinedload(Doctor.hospital))
        .where(Doctor.is_active == is_active)
    )

    if hospital_id:
        query = query.where(Doctor.hospital_id == hospital_id)
    if department_id:
        query = query.where(Doctor.department_id == department_id)
    if department_name:
        query = query.where(Department.name.ilike(f"%{department_name}%"))
    if specialty:
        query = query.where(Doctor.specialty.ilike(f"%{specialty}%"))

    return list(db.scalars(query).all())


def get_doctor_by_id(db: Session, doctor_id: str) -> Optional[Doctor]:
    query = (
        select(Doctor)
        .options(joinedload(Doctor.department), joinedload(Doctor.hospital))
        .where(Doctor.id == doctor_id)
    )
    return db.scalars(query).first()


def get_available_slots(
    db: Session,
    doctor_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[AppointmentSlot]:
    """Retrieve only unreserved, available slots for a specific doctor."""
    query = select(AppointmentSlot).where(
        AppointmentSlot.doctor_id == doctor_id,
        AppointmentSlot.status == "AVAILABLE",
    )

    if start_date:
        query = query.where(AppointmentSlot.start_time >= start_date)
    if end_date:
        query = query.where(AppointmentSlot.start_time <= end_date)

    query = query.order_by(AppointmentSlot.start_time.asc())
    return list(db.scalars(query).all())


# ==============================================================================
# AI Tool Interfaces (Section 9: Typed Python Service Functions)
# ==============================================================================

def search_doctors_tool(
    db: Session,
    specialty_or_department: Optional[str] = None,
    hospital_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    AI Tool: search_doctors
    Finds doctors matching clinical specialty or department keyword.
    Strictly validates input; returns structured JSON-compatible dictionary.
    """
    query = (
        select(Doctor)
        .join(Department, Doctor.department_id == Department.id)
        .options(joinedload(Doctor.department))
        .where(Doctor.is_active == True)
    )

    if hospital_id:
        query = query.where(Doctor.hospital_id == hospital_id)

    if specialty_or_department:
        term = f"%{specialty_or_department.strip()}%"
        query = query.where(
            or_(
                Doctor.specialty.ilike(term),
                Department.name.ilike(term),
                Doctor.display_name.ilike(term),
            )
        )

    doctors = db.scalars(query).all()
    results = []
    for doc in doctors:
        results.append({
            "doctor_id": doc.id,
            "display_name": doc.display_name,
            "specialty": doc.specialty,
            "department_name": doc.department.name if doc.department else "General",
            "hospital_id": doc.hospital_id,
        })
    return results


def get_available_slots_tool(
    db: Session,
    doctor_id: str,
    requested_date: Optional[str] = None,
    time_range: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    AI Tool: get_available_slots
    Retrieves confirmed open slots for a doctor with optional date and time filtering.
    """
    doc = get_doctor_by_id(db, doctor_id)
    if not doc:
        return []

    query = select(AppointmentSlot).where(
        AppointmentSlot.doctor_id == doctor_id,
        AppointmentSlot.status == "AVAILABLE",
    )

    slots = db.scalars(query.order_by(AppointmentSlot.start_time.asc())).all()
    results = []

    for slot in slots:
        slot_dt_str = slot.start_time.strftime("%Y-%m-%d")
        if requested_date and slot_dt_str != requested_date:
            continue

        slot_hour = slot.start_time.hour
        if time_range:
            tr = time_range.lower()
            if "morning" in tr and not (6 <= slot_hour < 12):
                continue
            if "afternoon" in tr and not (12 <= slot_hour < 17):
                continue
            if "evening" in tr and not (17 <= slot_hour < 21):
                continue

        results.append({
            "slot_id": slot.id,
            "doctor_id": doc.id,
            "doctor_name": doc.display_name,
            "specialty": doc.specialty,
            "start_time": slot.start_time.isoformat(),
            "end_time": slot.end_time.isoformat(),
            "status": slot.status,
        })

    return results
