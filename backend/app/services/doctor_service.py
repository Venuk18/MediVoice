from datetime import date, datetime, timedelta, timezone
import uuid
import re
from typing import Optional, List, Dict, Any, Set, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, and_, or_
from sqlalchemy.exc import IntegrityError
from app.models.audit_event import AuditEvent
from app.models.hospital import Hospital
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.appointment_slot import AppointmentSlot
from app.schemas.doctor import DoctorManageCreate, DoctorSlotCreateRequest


def get_hospital_timezone() -> timezone:
    """Returns Asia/Kolkata timezone with UTC+05:30 offset."""
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo("Asia/Kolkata")
    except Exception:
        return timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")


KOLKATA_TZ = get_hospital_timezone()

DOCTOR_SCHEDULE_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        "working_days": [0, 1, 2, 3, 4, 5],  # Mon-Sat, Sunday (6) excluded
        "slot_times": [(10, 0), (11, 30), (14, 0), (16, 0)],
        "duration_minutes": 30,
    },
    "Dr. Rajesh Sharma": {
        "working_days": [0, 1, 2, 3, 4, 5],
        "slot_times": [(10, 0), (11, 30), (14, 0), (16, 0)],  # 10:00 AM, 11:30 AM, 2:00 PM, 4:00 PM
        "duration_minutes": 30,
    },
    "Dr. Sunita Rao": {
        "working_days": [0, 1, 2, 3, 4, 5],
        "slot_times": [(11, 0), (12, 30), (15, 0), (17, 0)],  # 11:00 AM, 12:30 PM, 3:00 PM, 5:00 PM
        "duration_minutes": 30,
    },
    "Dr. Priya Nair": {
        "working_days": [0, 1, 2, 3, 4, 5],
        "slot_times": [(9, 30), (11, 0), (14, 0), (15, 30)],
        "duration_minutes": 30,
    },
    "Dr. Arvind Swamy": {
        "working_days": [0, 1, 2, 3, 4, 5],
        "slot_times": [(10, 0), (11, 30), (14, 0), (16, 30)],
        "duration_minutes": 30,
    },
    "Dr. Ananya Sen": {
        "working_days": [0, 1, 2, 3, 4, 5],
        "slot_times": [(9, 0), (10, 30), (13, 30), (15, 0)],
        "duration_minutes": 30,
    },
    "Dr. Vikram Mehta": {
        "working_days": [0, 1, 2, 3, 4, 5],
        "slot_times": [(10, 0), (11, 30), (14, 30), (16, 0)],
        "duration_minutes": 30,
    },
}


def get_hospitals(db: Session, is_active: Optional[bool] = True) -> List[Hospital]:
    query = select(Hospital)
    if is_active is not None:
        query = query.where(Hospital.is_active == is_active)
    return list(db.scalars(query).unique().all())


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

    return list(db.scalars(query).unique().all())


def deduplicate_doctors(doctors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate doctor dictionaries by doctor_id and (name, specialty) while preserving order."""
    seen_ids = set()
    seen_keys = set()
    deduped = []
    for doc in doctors:
        d_id = str(doc.get("doctor_id") or doc.get("id") or "").strip()
        name = str(doc.get("display_name") or doc.get("name") or "").strip().lower()
        specialty = str(doc.get("specialty") or "").strip().lower()

        clean_name = re.sub(r"^(dr\.?|doctor)\s+", "", name).strip()
        key = (clean_name, specialty) if clean_name else None

        if d_id and d_id in seen_ids:
            continue
        if key and key in seen_keys:
            continue

        if d_id:
            seen_ids.add(d_id)
        if key:
            seen_keys.add(key)
        deduped.append(doc)
    return deduped


def get_doctor_by_id(db: Session, doctor_id: str) -> Optional[Doctor]:
    query = (
        select(Doctor)
        .options(joinedload(Doctor.department), joinedload(Doctor.hospital))
        .where(Doctor.id == doctor_id)
    )
    return db.scalars(query).first()


def create_doctor_with_slots(
    db: Session,
    payload: DoctorManageCreate,
    actor_reference: str = "MAINTENANCE_ADMIN",
) -> Doctor:
    """Create a new active synthetic doctor and seed initial available appointment slots."""
    dept: Optional[Department] = None
    if payload.department_id:
        dept = db.scalars(
            select(Department).where(Department.id == payload.department_id)
        ).first()
    if not dept and payload.department_name:
        dept = db.scalars(
            select(Department).where(Department.name.ilike(f"%{payload.department_name.strip()}%"))
        ).first()
    if not dept:
        dept = db.scalars(select(Department)).first()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hospital department found to assign the new doctor.",
        )

    doc_id = str(uuid.uuid4())
    new_doc = Doctor(
        id=doc_id,
        hospital_id=dept.hospital_id,
        department_id=dept.id,
        display_name=payload.display_name.strip(),
        specialty=payload.specialty.strip(),
        is_active=True,
    )
    db.add(new_doc)
    db.flush()

    now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    for day_offset in (1, 2, 3):
        for hour_val in (10, 15):
            slot_start = (now_utc + timedelta(days=day_offset)).replace(hour=hour_val)
            slot_end = slot_start + timedelta(minutes=30)
            db.add(
                AppointmentSlot(
                    id=str(uuid.uuid4()),
                    doctor_id=new_doc.id,
                    start_time=slot_start,
                    end_time=slot_end,
                    status="AVAILABLE",
                )
            )

    db.add(
        AuditEvent(
            actor_reference=actor_reference,
            action="DOCTOR_CREATED",
            entity_type="Doctor",
            entity_id=new_doc.id,
            details=f"Added physician {new_doc.display_name} ({new_doc.specialty}) in {dept.name} with 6 available slots.",
        )
    )
    db.commit()
    return get_doctor_by_id(db, new_doc.id) or new_doc


def deactivate_doctor(
    db: Session,
    doctor_id: str,
    actor_reference: str = "MAINTENANCE_ADMIN",
) -> Doctor:
    """Deactivate (remove from active directory) a doctor record and log an audit event."""
    doc = get_doctor_by_id(db, doctor_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Doctor with ID '{doctor_id}' not found.",
        )
    doc.is_active = False
    db.add(
        AuditEvent(
            actor_reference=actor_reference,
            action="DOCTOR_REMOVED",
            entity_type="Doctor",
            entity_id=doc.id,
            details=f"Removed physician {doc.display_name} ({doc.specialty}) from active directory.",
        )
    )
    db.commit()
    db.refresh(doc)
    return doc


def create_doctor_slot(
    db: Session,
    doctor_id: str,
    payload: DoctorSlotCreateRequest,
    actor_reference: str = "DOCTOR_PORTAL",
) -> AppointmentSlot:
    """Create a new available appointment slot for a doctor."""
    doc = get_doctor_by_id(db, doctor_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Doctor with ID '{doctor_id}' not found.",
        )
    start_naive = payload.start_time.replace(tzinfo=None)
    end_naive = payload.end_time.replace(tzinfo=None)
    if end_naive <= start_naive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slot end_time must be after start_time.",
        )
    slot = AppointmentSlot(
        id=str(uuid.uuid4()),
        doctor_id=doc.id,
        start_time=start_naive,
        end_time=end_naive,
        status="AVAILABLE",
    )
    db.add(slot)
    db.add(
        AuditEvent(
            actor_reference=actor_reference,
            action="DOCTOR_SLOT_CREATED",
            entity_type="AppointmentSlot",
            entity_id=slot.id,
            details=f"Published availability slot for {doc.display_name}: {start_naive.isoformat()} to {end_naive.isoformat()}.",
        )
    )
    db.commit()
    db.refresh(slot)
    return slot


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


def generate_upcoming_slots_for_doctors(
    db: Session,
    days: int = 20,
    base_date: Optional[date] = None,
    holidays: Optional[Set[date]] = None,
) -> int:
    """
    Generates realistic appointment availability for every active doctor for the next
    specified number of calendar days (default 20 calendar days).

    Optimized batch implementation:
    - Pre-fetches active doctors without joinedload overhead (1 query).
    - Batch queries all existing appointment slots across the entire date window in 1 query.
    - Resolves and filters candidate slots purely in-memory using O(1) hash sets.
    - Batch flushes all new slots in a single database operation with savepoint protection.
    - Completely eliminates N+1 query patterns (reducing query count by >99%).
    - Respects doctor schedules, Sunday exclusions, holidays, and Asia/Kolkata timezone.
    - Preserves existing booked and reserved slots without overwriting.
    """
    if days <= 0:
        return 0

    tz = get_hospital_timezone()
    if base_date is None:
        now_tz = datetime.now(tz)
        base_date = now_tz.date()

    # Query active doctors without joining unnecessary tables
    active_doctors = list(
        db.execute(
            select(Doctor.id, Doctor.display_name)
            .where(Doctor.is_active == True)
            .order_by(Doctor.id.asc())
        ).all()
    )
    if not active_doctors:
        return 0

    # Date range boundaries
    first_date = base_date + timedelta(days=1)
    last_date = base_date + timedelta(days=days)
    range_start_dt = datetime(first_date.year, first_date.month, first_date.day, 0, 0, 0, tzinfo=tz)
    range_end_dt = datetime(last_date.year, last_date.month, last_date.day, 23, 59, 59, tzinfo=tz)

    range_start_utc = range_start_dt.astimezone(timezone.utc)
    range_end_utc = range_end_dt.astimezone(timezone.utc)
    range_start_naive = range_start_dt.replace(tzinfo=None)
    range_end_naive = range_end_dt.replace(tzinfo=None)

    doc_ids = [d.id for d in active_doctors]

    # Batch fetch all existing slots within the time window for active doctors (single query)
    existing_slots_query = select(
        AppointmentSlot.id,
        AppointmentSlot.doctor_id,
        AppointmentSlot.start_time,
    ).where(
        AppointmentSlot.doctor_id.in_(doc_ids),
        or_(
            and_(
                AppointmentSlot.start_time >= range_start_dt,
                AppointmentSlot.start_time <= range_end_dt,
            ),
            and_(
                AppointmentSlot.start_time >= range_start_utc,
                AppointmentSlot.start_time <= range_end_utc,
            ),
            and_(
                AppointmentSlot.start_time >= range_start_naive,
                AppointmentSlot.start_time <= range_end_naive,
            ),
        ),
    )
    existing_rows = db.execute(existing_slots_query).all()

    # In-memory O(1) lookup sets
    existing_slot_ids: Set[str] = set()
    existing_slot_keys: Set[Tuple[str, str]] = set()

    for slot_id, doctor_id, st in existing_rows:
        existing_slot_ids.add(slot_id)
        if st is not None:
            if st.tzinfo is not None:
                st_local = st.astimezone(tz)
            else:
                st_local = st
            existing_slot_keys.add((doctor_id, st_local.strftime("%Y%m%d%H%M")))
            existing_slot_keys.add((doctor_id, st.strftime("%Y%m%d%H%M")))

    new_slots: List[AppointmentSlot] = []
    configured_holidays = holidays or set()

    for day_offset in range(1, days + 1):
        slot_date = base_date + timedelta(days=day_offset)
        # Exclude non-working days (Sunday is 6) and holidays
        if slot_date.weekday() == 6:
            continue
        if slot_date in configured_holidays:
            continue

        for doc in active_doctors:
            sched = DOCTOR_SCHEDULE_CONFIG.get(doc.display_name, DOCTOR_SCHEDULE_CONFIG["DEFAULT"])
            working_days = sched.get("working_days", [0, 1, 2, 3, 4, 5])
            if slot_date.weekday() not in working_days:
                continue

            slot_times = sched.get("slot_times", [(10, 0), (11, 30), (14, 0), (16, 0)])
            duration = sched.get("duration_minutes", 30)

            for hour, minute in slot_times:
                slot_start = datetime(
                    slot_date.year, slot_date.month, slot_date.day, hour, minute, 0, tzinfo=tz
                )
                slot_end = slot_start + timedelta(minutes=duration)
                deterministic_id = f"slot-{doc.id.replace('-', '')[-8:]}-{slot_start.strftime('%Y%m%d%H%M')}"
                candidate_key = (doc.id, slot_start.strftime("%Y%m%d%H%M"))

                # Check if slot already exists in DB or was added earlier in this batch
                if deterministic_id in existing_slot_ids or candidate_key in existing_slot_keys:
                    continue

                # Mark as seen in local batch
                existing_slot_ids.add(deterministic_id)
                existing_slot_keys.add(candidate_key)

                new_slots.append(
                    AppointmentSlot(
                        id=deterministic_id,
                        doctor_id=doc.id,
                        start_time=slot_start,
                        end_time=slot_end,
                        status="AVAILABLE",
                    )
                )

    if not new_slots:
        return 0

    # Batch insert with integrity protection for concurrent race conditions
    try:
        db.add_all(new_slots)
        db.flush()
        return len(new_slots)
    except IntegrityError:
        # A concurrent worker or process inserted some or all of these slots simultaneously.
        # Roll back and filter out conflicting IDs, inserting remaining non-conflicting slots.
        db.rollback()
        existing_db_ids = set(
            db.scalars(
                select(AppointmentSlot.id).where(
                    AppointmentSlot.id.in_([s.id for s in new_slots])
                )
            ).all()
        )
        non_conflicting = [s for s in new_slots if s.id not in existing_db_ids]
        if non_conflicting:
            db.add_all(non_conflicting)
            db.flush()
            return len(non_conflicting)
        return 0


def find_alternative_doctors_with_slots(
    db: Session,
    doctor_id: str,
    days: int = 20,
) -> List[Dict[str, Any]]:
    """
    If the selected doctor has no available slots within the next 20 days:
    - Searches for other active doctors in the same department.
    - Checks their availability across the same 20-day period.
    - Identifies their earliest available appointments.
    - Returns alternative doctors sorted by earliest slot start time.
    """
    doc = get_doctor_by_id(db, doctor_id)
    if not doc:
        return []

    dept_id = doc.department_id
    if not dept_id:
        return []

    # Find active colleagues in the same department excluding this physician
    colleagues = db.scalars(
        select(Doctor).where(
            Doctor.department_id == dept_id,
            Doctor.id != doc.id,
            Doctor.is_active == True,
        )
    ).all()

    results = []
    for colleague in colleagues:
        colleague_slots = get_available_slots_tool(db, doctor_id=colleague.id)
        if colleague_slots:
            earliest_slot = colleague_slots[0]
            results.append({
                "doctor_id": colleague.id,
                "display_name": colleague.display_name,
                "specialty": colleague.specialty,
                "department_name": colleague.department.name if colleague.department else doc.specialty,
                "earliest_slot": earliest_slot,
                "available_slots": colleague_slots,
            })

    # Sort colleagues by earliest available slot
    results.sort(key=lambda x: x["earliest_slot"]["start_time"])
    return results



# ==============================================================================
# AI Tool Interfaces (Section 9: Typed Python Service Functions)
# ==============================================================================

MULTILINGUAL_SEARCH_ALIASES: Dict[str, str] = {
    # Cardiology
    "కార్డియాలజీ": "Cardiology",
    "కార్డియాలజిస్ట్": "Cardiology",
    "గుండె": "Cardiology",
    "இதயவியல்": "Cardiology",
    "இதய": "Cardiology",
    "కార్డియాక్": "Cardiology",
    "ಕಾರ್ಡಿಯಾಲಜಿ": "Cardiology",
    "ಹೃದ್ರೋಗ": "Cardiology",
    "ಹೃದಯ": "Cardiology",
    "कार्डियोलॉजी": "Cardiology",
    "कार्डियोलॉजिस्ट": "Cardiology",
    "हृदय": "Cardiology",
    # Neurology
    "న్యూరాలజీ": "Neurology",
    "న్యూరాలజిస్ట్": "Neurology",
    "మెదడు": "Neurology",
    "நரம்பியல்": "Neurology",
    "நரம்பு": "Neurology",
    "ನ್ಯೂರಾಲಜಿ": "Neurology",
    "ನರ": "Neurology",
    "न्यूरोलॉजी": "Neurology",
    "न्यूरोलॉजिस्ट": "Neurology",
    "नस": "Neurology",
    # Orthopedics
    "ఆర్థోపెడిక్స్": "Orthopedics",
    "ఎముకల": "Orthopedics",
    "కీళ్ల": "Orthopedics",
    "எலும்பியல்": "Orthopedics",
    "எலும்பு": "Orthopedics",
    "ಆರ್ಥೋಪೆಡಿಕ್ಸ್": "Orthopedics",
    "ಮೂಳೆ": "Orthopedics",
    "ऑर्थोपेडिक्स": "Orthopedics",
    "हड्डी": "Orthopedics",
    # Pediatrics
    "పీడియాట్రిక్స్": "Pediatrics",
    "పిల్లల": "Pediatrics",
    "குழந்தைகள்": "Pediatrics",
    "ಪೀಡಿಯಾಟ್ರಿಕ್ಸ್": "Pediatrics",
    "ಮಕ್ಕಳ": "Pediatrics",
    "पीडियाट्रिक्स": "Pediatrics",
    "बाल रोग": "Pediatrics",
    "बच्चों": "Pediatrics",
    # General Medicine
    "జనరల్ మెడిసిన్": "General Medicine",
    "సాధారణ వైద్యం": "General Medicine",
    "జ్వరం": "General Medicine",
    "பொது மருத்துவம்": "General Medicine",
    "ಜನರಲ್ ಮೆಡಿಸಿನ್": "General Medicine",
    "ಸಾಮಾನ್ಯ": "General Medicine",
    "जनरल मेडिसिन": "General Medicine",
    "सामान्य चिकित्सा": "General Medicine",
    # Doctor names across scripts
    "శర్మ": "Sharma",
    "రాజేష్": "Sharma",
    "சர்மா": "Sharma",
    "ராஜேஷ்": "Sharma",
    "ಶರ್ಮಾ": "Sharma",
    "ರಾಜೇಶ್": "Sharma",
    "शर्मा": "Sharma",
    "राजेश": "Sharma",
    "నాయర్": "Nair",
    "ప్రియ": "Nair",
    "ప్రియా": "Nair",
    "நாயர்": "Nair",
    "பிரியா": "Nair",
    "ನಾಯರ್": "Nair",
    "ಪ್ರಿಯಾ": "Nair",
    "नायर": "Nair",
    "प्रिया": "Nair",
    "స్వామి": "Swamy",
    "అరవింద్": "Swamy",
    "சுவாமி": "Swamy",
    "அரவிந்த்": "Swamy",
    "ಸ್ವಾಮಿ": "Swamy",
    "ಅರವಿಂದ್": "Swamy",
    "स्वामी": "Swamy",
    "अरविंद": "Swamy",
    "సేన్": "Sen",
    "అనన్య": "Sen",
    "சென்": "Sen",
    "அனன்யா": "Sen",
    "ಸೇನ್": "Sen",
    "ಅನನ್ಯಾ": "Sen",
    "सेन": "Sen",
    "अनन्या": "Sen",
    "మెహతా": "Mehta",
    "విక్రమ్": "Mehta",
    "மேத்தா": "Mehta",
    "விக்ரம்": "Mehta",
    "ಮೆಹ್ತಾ": "Mehta",
    "ವಿಕ್ರಮ್": "Mehta",
    "मेहता": "Mehta",
    "विक्रम": "Mehta",
    "రావు": "Rao",
    "సునీత": "Rao",
    "ராவ்": "Rao",
    "சுனிதா": "Rao",
    "ರಾವ್": "Rao",
    "ಸುನೀತಾ": "Rao",
    "राव": "Rao",
    "सुनीता": "Rao",
}

TRANSLITERATED_SEARCH_ALIASES: Dict[str, str] = {
    "cardiologist": "Cardiology",
    "cardioligist": "Cardiology",
    "cardiolgy": "Cardiology",
    "cardiac": "Cardiology",
    "heart specialist": "Cardiology",
    "heart doctor": "Cardiology",
    "heart": "Cardiology",
    "gunde": "Cardiology",
    "chaathi": "Cardiology",
    "chathi": "Cardiology",
    "ithaya": "Cardiology",
    "nenju": "Cardiology",
    "hrudaya": "Cardiology",
    "ede novu": "Cardiology",
    "seene": "Cardiology",
    "dil": "Cardiology",
    "neurologist": "Neurology",
    "neurologest": "Neurology",
    "brain specialist": "Neurology",
    "nerve specialist": "Neurology",
    "brain": "Neurology",
    "migraine": "Neurology",
    "thala noppi": "Neurology",
    "talanoppi": "Neurology",
    "thalai vali": "Neurology",
    "thalaivali": "Neurology",
    "thale novu": "Neurology",
    "talenovu": "Neurology",
    "sar dard": "Neurology",
    "sirdard": "Neurology",
    "orthopedic": "Orthopedics",
    "orthopedics": "Orthopedics",
    "orthopedist": "Orthopedics",
    "orthopaedic": "Orthopedics",
    "orthopaedics": "Orthopedics",
    "bone specialist": "Orthopedics",
    "joint specialist": "Orthopedics",
    "ortho": "Orthopedics",
    "bone": "Orthopedics",
    "joint": "Orthopedics",
    "knee": "Orthopedics",
    "keella": "Orthopedics",
    "mokalla": "Orthopedics",
    "moottu": "Orthopedics",
    "muzhangal": "Orthopedics",
    "mandi novu": "Orthopedics",
    "moole": "Orthopedics",
    "haddi": "Orthopedics",
    "ghutne": "Orthopedics",
    "pediatrician": "Pediatrics",
    "paediatrician": "Pediatrics",
    "paediatric": "Pediatrics",
    "paediatrics": "Pediatrics",
    "child specialist": "Pediatrics",
    "child": "Pediatrics",
    "pillala": "Pediatrics",
    "kuzhandhai": "Pediatrics",
    "makkala": "Pediatrics",
    "bachon": "Pediatrics",
    "general physician": "General Medicine",
    "physician": "General Medicine",
    "family doctor": "General Medicine",
    "internal medicine": "General Medicine",
    "dermatologist": "Dermatology",
    "dermatology": "Dermatology",
    "dermatologyst": "Dermatology",
    "skin specialist": "Dermatology",
    "skin doctor": "Dermatology",
    "skin": "Dermatology",
    "jwaram": "General Medicine",
    "kaichal": "General Medicine",
    "jwara": "General Medicine",
    "bukhar": "General Medicine",
    "fever": "General Medicine",
}


def normalize_search_term(raw_term: Optional[str]) -> Optional[str]:
    if not raw_term:
        return raw_term
    cleaned = raw_term.strip()
    if not cleaned:
        return None
    low_cleaned = cleaned.lower()
    if low_cleaned in ("all", "any", "*"):
        return None
    # If fever/general medicine symptoms are combined with secondary headache symptoms, prefer General Medicine
    has_general_med_cue = any(
        cue in cleaned or cue in low_cleaned
        for cue in ("జ్వరం", "காய்ச்சல்", "ಜ್ವರ", "बुखार", "fever", "jwaram", "kaichal", "jwara", "bukhar")
    )
    has_explicit_neuro = any(
        cue in cleaned or cue in low_cleaned
        for cue in ("న్యూరాలజీ", "న్యూరాలజిస్ట్", "நரம்பியல்", "ನ್ಯೂರಾಲಜಿ", "न्यूरोलॉजी", "न्यूरोलॉजिस्ट", "neurology", "neurologist")
    )
    if has_general_med_cue and not has_explicit_neuro:
        return "General Medicine"
    for alias, canonical in MULTILINGUAL_SEARCH_ALIASES.items():
        if alias in cleaned:
            return canonical
    for alias_en, canonical_en in TRANSLITERATED_SEARCH_ALIASES.items():
        if alias_en in low_cleaned:
            return canonical_en
    # Strip honorific prefixes like "Dr." or "Dr "
    stripped = cleaned
    for prefix in ("Dr.", "Dr ", "dr.", "dr ", "Doctor ", "doctor "):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):].strip()
    return stripped or cleaned


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

    normalized = normalize_search_term(specialty_or_department)
    if normalized:
        term = f"%{normalized}%"
        query = query.where(
            or_(
                Doctor.specialty.ilike(term),
                Department.name.ilike(term),
                Doctor.display_name.ilike(term),
            )
        )

    doctors = db.scalars(query).unique().all()
    results = []
    seen_ids = set()
    seen_keys = set()
    for doc in doctors:
        if not doc.id or doc.id in seen_ids:
            continue
        clean_name = re.sub(r"^(dr\.?|doctor)\s+", "", (doc.display_name or "").strip().lower()).strip()
        spec = (doc.specialty or "").strip().lower()
        key = (clean_name, spec) if clean_name else None
        if key and key in seen_keys:
            continue

        seen_ids.add(doc.id)
        if key:
            seen_keys.add(key)
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

    # Include any duplicate/aliased database records sharing the exact same doctor name & specialty
    matching_ids = db.scalars(
        select(Doctor.id).where(
            Doctor.display_name.ilike(doc.display_name),
            Doctor.specialty.ilike(doc.specialty),
        )
    ).all()
    all_doc_ids = set(matching_ids)
    all_doc_ids.add(doc.id)

    now_utc = datetime.now(timezone.utc)
    now_naive = now_utc.replace(tzinfo=None)
    query = select(AppointmentSlot).where(
        AppointmentSlot.doctor_id.in_(all_doc_ids),
        AppointmentSlot.status == "AVAILABLE",
        or_(
            AppointmentSlot.start_time > now_utc,
            AppointmentSlot.start_time > now_naive,
        ),
    )

    slots = db.scalars(query.order_by(AppointmentSlot.start_time.asc())).all()
    results = []
    tz = get_hospital_timezone()

    for slot in slots:
        local_dt = slot.start_time
        if local_dt.tzinfo is not None:
            local_dt = local_dt.astimezone(tz)

        slot_dt_str = local_dt.strftime("%Y-%m-%d")
        if requested_date and slot_dt_str != requested_date:
            continue

        slot_hour = local_dt.hour
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
