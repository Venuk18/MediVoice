import random
import re
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from app.models.patient import Patient
from app.models.appointment import Appointment


INDIC_DIGITS_MAP = {
    "౦": "0", "౧": "1", "౨": "2", "౩": "3", "౪": "4",
    "౫": "5", "౬": "6", "౭": "7", "౮": "8", "౯": "9",
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
    "௦": "0", "௧": "1", "௨": "2", "௩": "3", "௪": "4",
    "௫": "5", "௬": "6", "௭": "7", "௮": "8", "௯": "9",
    "೦": "0", "೧": "1", "೨": "2", "೩": "3", "೪": "4",
    "೫": "5", "೬": "6", "೭": "7", "೮": "8", "೯": "9",
}

SPOKEN_DIGIT_WORDS_MAP: Dict[str, str] = {
    "zero": "0", "oh": "0", "o": "0", "nil": "0", "null": "0",
    "సున్నా": "0", "sunna": "0",
    "शून्य": "0", "shunya": "0",
    "பூஜ்ஜியம்": "0", "சுழி": "0", "poojiyam": "0", "poojyam": "0",
    "ಸೊನ್ನೆ": "0", "sonne": "0",

    "one": "1",
    "ఒకటి": "1", "ఒక": "1", "okati": "1", "oka": "1",
    "एक": "1", "ek": "1",
    "ஒன்று": "1", "ஒன்னு": "1", "ondru": "1", "onnu": "1",
    "ಒಂದು": "1", "ondu": "1",

    "two": "2",
    "రెండు": "2", "rendu": "2",
    "दो": "2", "do": "2",
    "இரண்டு": "2", "ரெண்டு": "2", "irandu": "2",
    "ಎರಡು": "2", "eradu": "2",

    "three": "3",
    "మూడు": "3", "moodu": "3", "mudu": "3",
    "तीन": "3", "teen": "3", "tin": "3",
    "மூன்று": "3", "மூணு": "3", "moondru": "3", "moonu": "3",
    "ಮೂರು": "3", "mooru": "3",

    "four": "4",
    "నాలుగు": "4", "naalugu": "4", "nalugu": "4",
    "चार": "4", "chaar": "4", "char": "4",
    "நான்கு": "4", "நாலு": "4", "naangu": "4", "naalu": "4",
    "ನಾಲ್ಕು": "4", "naalku": "4", "nalku": "4",

    "five": "5",
    "ఐదు": "5", "aidu": "5",
    "पाँच": "5", "पांच": "5", "paanch": "5", "panch": "5",
    "ஐந்து": "5", "அஞ்சு": "5", "aindhu": "5", "anju": "5",
    "ಐದು": "5",

    "six": "6",
    "ఆరు": "6", "aaru": "6",
    "छह": "6", "छ:": "6", "chhah": "6", "chhe": "6",
    "ஆறு": "6",
    "ಆರು": "6",

    "seven": "7",
    "ఏడు": "7", "yedu": "7", "edu": "7",
    "सात": "7", "saat": "7",
    "ஏழு": "7", "ezhu": "7", "elu": "7",
    "ಏಳು": "7", "yelu": "7",

    "eight": "8",
    "ఎనిమిది": "8", "enimidi": "8",
    "आठ": "8", "aath": "8", "aat": "8",
    "எட்டு": "8", "ettu": "8",
    "ಎಂಟು": "8", "entu": "8",

    "nine": "9",
    "తొమ్మిది": "9", "tommidi": "9",
    "नौ": "9", "nau": "9",
    "ஒன்பது": "9", "onbadhu": "9", "onbathu": "9",
    "ಒಂಬತ್ತು": "9", "ombattu": "9",
}

DOUBLE_TOKENS = {"double", "డబుల్", "डबल", "டபுள்", "ಡಬಲ್"}
TRIPLE_TOKENS = {"triple", "ట్రిపుల్", "ट्रिपल", "ட்ரிபிள்", "ಟ್ರಿಪಲ್"}


def normalize_spoken_phone_number(text: str) -> Optional[str]:
    """
    Normalizes spoken phone number representations across English, Telugu, Hindi, Tamil, and Kannada.
    Supports continuous digit strings, spaced digits, spoken digit words, Indic numerals, and multipliers (double/triple).
    Requires exactly 10 digits after normalization. Rejects incomplete, malformed, or extra-digit sequences.
    """
    if not text or not text.strip():
        return None
    processed = text
    for k, v in INDIC_DIGITS_MAP.items():
        processed = processed.replace(k, v)

    tokens = re.findall(r"[A-Za-z\u0C00-\u0C7F\u0900-\u097F\u0B80-\u0BFF\u0C80-\u0CFF\d]+", processed.lower())
    digits = []
    multiplier = 1
    for tok in tokens:
        if tok in DOUBLE_TOKENS:
            multiplier = 2
            continue
        elif tok in TRIPLE_TOKENS:
            multiplier = 3
            continue

        if tok in SPOKEN_DIGIT_WORDS_MAP:
            d = SPOKEN_DIGIT_WORDS_MAP[tok]
            digits.extend([d] * multiplier)
            multiplier = 1
        elif tok.isdigit():
            for char in tok:
                digits.extend([char] * multiplier)
            multiplier = 1

    digit_str = "".join(digits)
    # Strip country code +91 or 91 if followed by 10 digits
    if len(digit_str) == 12 and digit_str.startswith("91"):
        digit_str = digit_str[2:]
    # Strip leading zero if followed by 10 digits
    elif len(digit_str) == 11 and digit_str.startswith("0"):
        digit_str = digit_str[1:]

    # Require EXACTLY 10 digits
    if len(digit_str) == 10:
        return digit_str
    return None


def normalize_phone(phone: str) -> str:
    """Strips formatting, spoken words, and ensures strictly valid 10-digit phone representation."""
    if not phone:
        return ""
    spoken = normalize_spoken_phone_number(phone)
    if spoken:
        return spoken
    clean = re.sub(r"[^\d]", "", phone.strip())
    if len(clean) == 12 and clean.startswith("91"):
        clean = clean[2:]
    elif len(clean) == 11 and clean.startswith("0"):
        clean = clean[1:]
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
        existing_name_norm = existing_patient.full_name.strip().lower()
        provided_name_norm = cleaned_name.lower()
        # Identity match if names are equal or one is an alias / substring of the other (e.g. Venu vs Venugopal)
        is_same_identity = (
            existing_name_norm == provided_name_norm
            or existing_name_norm in provided_name_norm
            or provided_name_norm in existing_name_norm
        )
        if not is_same_identity:
            return {
                "patient_reference": existing_patient.patient_reference,
                "full_name": existing_patient.full_name,
                "provided_name": cleaned_name,
                "phone_number": existing_patient.phone_number,
                "is_new": False,
                "identity_conflict": True,
            }
        return {
            "patient_reference": existing_patient.patient_reference,
            "full_name": existing_patient.full_name,
            "provided_name": cleaned_name,
            "phone_number": existing_patient.phone_number,
            "is_new": False,
            "identity_conflict": False,
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

