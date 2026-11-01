import random
import re
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from app.models.patient import Patient
from app.models.appointment import Appointment


def normalize_phone(phone: str) -> str:
    """Strips formatting and ensures 10-15 digit phone representation."""
    if not phone:
        return ""
    clean = re.sub(r"[^\d]", "", phone.strip())
    # If 12 digits starting with 91 (India country code), keep 10-digit national number
    if len(clean) == 12 and clean.startswith("91"):
        clean = clean[2:]
    return clean


def generate_unique_patient_reference(db: Session) -> str:
    """Generates an internal reference e.g. PAT-2026-XXXX that does not collide."""
    year = 2026
    for _ in range(50):
        suffix = random.randint(1000, 9999)
        ref = f"PAT-{year}-{suffix}"
        # Check patients table
        existing_p = db.execute(select(Patient).where(Patient.patient_reference == ref)).scalar_one_or_none()
        if existing_p:
            continue
        # Also check appointments table
        existing_a = db.execute(select(Appointment).where(Appointment.patient_reference == ref)).scalar_one_or_none()
        if existing_a:
            continue
        return ref
    # Fallback to 6-digit suffix
    suffix = random.randint(100000, 999999)
    return f"PAT-{year}-{suffix}"


def register_patient(db: Session, full_name: str, phone_number: str) -> Dict[str, Any]:
    """Registers a new patient with validation and persistence."""
    cleaned_name = full_name.strip()
    if len(cleaned_name) < 2:
        raise ValueError("Patient name must be at least 2 characters long.")

    clean_phone = normalize_phone(phone_number)
    if len(clean_phone) < 10:
        raise ValueError("Please provide a valid 10-digit mobile number.")

    # Check if a patient with this phone number is already registered
    existing_patient = db.execute(
        select(Patient).where(Patient.phone_number == clean_phone)
    ).scalar_one_or_none()

    if existing_patient:
        return {
            "patient_reference": existing_patient.patient_reference,
            "full_name": existing_patient.full_name,
            "phone_number": existing_patient.phone_number,
            "is_new": False,
        }

    # Generate new reference and persist
    new_ref = generate_unique_patient_reference(db)
    patient = Patient(
        patient_reference=new_ref,
        full_name=cleaned_name,
        phone_number=clean_phone,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    return {
        "patient_reference": patient.patient_reference,
        "full_name": patient.full_name,
        "phone_number": patient.phone_number,
        "is_new": True,
    }


def lookup_patient(
    db: Session,
    patient_reference: Optional[str] = None,
    phone_number: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Looks up a registered patient by reference or phone number."""
    if not patient_reference and not phone_number:
        return None

    query = select(Patient)
    clauses = []
    if patient_reference:
        clauses.append(Patient.patient_reference.ilike(patient_reference.strip()))
    if phone_number:
        clean_phone = normalize_phone(phone_number)
        if clean_phone:
            clauses.append(Patient.phone_number == clean_phone)

    if not clauses:
        return None

    patient = db.execute(query.where(or_(*clauses))).scalar_one_or_none()
    if patient:
        return {
            "patient_reference": patient.patient_reference,
            "full_name": patient.full_name,
            "phone_number": patient.phone_number,
        }

    # Also fallback check appointments table for existing synthetic patient_references
    if patient_reference:
        clean_ref = patient_reference.strip().upper()
        appt = db.execute(
            select(Appointment).where(Appointment.patient_reference.ilike(clean_ref))
        ).first()
        if appt:
            return {
                "patient_reference": clean_ref,
                "full_name": "Valued Patient",
                "phone_number": "",
            }

    return None


def register_patient_tool(db: Session, full_name: str, phone_number: str) -> Dict[str, Any]:
    """Allowlisted agent tool for new-patient registration."""
    try:
        return register_patient(db, full_name=full_name, phone_number=phone_number)
    except Exception as exc:
        raise ValueError(str(exc))


def verify_patient_tool(
    db: Session,
    patient_reference: Optional[str] = None,
    phone_number: Optional[str] = None,
) -> Dict[str, Any]:
    """Allowlisted agent tool for existing patient verification."""
    result = lookup_patient(db, patient_reference=patient_reference, phone_number=phone_number)
    if result:
        return {
            "verified": True,
            "patient_reference": result["patient_reference"],
            "full_name": result["full_name"],
            "message": (
                f"Matching patient contact record located ({result['patient_reference']}). "
                "Official photo identity verification is completed at hospital reception during check-in."
            ),
        }
    return {
        "verified": False,
        "patient_reference": None,
        "full_name": None,
        "message": (
            "No matching patient record was found. You can register as a new patient "
            "or request staff assistance at the Aarogya One Hospital front desk."
        ),
    }

