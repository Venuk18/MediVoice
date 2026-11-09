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
    "సున్నా": "0", "sunna": "0", "జీరో": "0",
    "शून्य": "0", "shunya": "0",
    "பூஜ்ஜியம்": "0", "சுழி": "0", "poojiyam": "0", "poojyam": "0",
    "ಸೊನ್ನೆ": "0", "sonne": "0",

    "one": "1", "won": "1",
    "ఒకటి": "1", "ఒక": "1", "okati": "1", "oka": "1", "వన్": "1", "వన్‌": "1",
    "एक": "1", "ek": "1",
    "ஒன்று": "1", "ஒன்னு": "1", "ondru": "1", "onnu": "1",
    "ಒಂದು": "1", "ondu": "1",

    "two": "2", "to": "2", "too": "2",
    "రెండు": "2", "rendu": "2", "టూ": "2",
    "दो": "2", "do": "2",
    "இரண்டு": "2", "ரெண்டு": "2", "irandu": "2",
    "ಎರಡು": "2", "eradu": "2",

    "three": "3",
    "మూడు": "3", "moodu": "3", "mudu": "3", "త్రీ": "3",
    "तीन": "3", "teen": "3", "tin": "3",
    "மூன்று": "3", "மூணு": "3", "moondru": "3", "moonu": "3",
    "ಮೂರು": "3", "mooru": "3",

    "four": "4", "for": "4", "fore": "4",
    "నాలుగు": "4", "naalugu": "4", "nalugu": "4", "ఫోర్": "4",
    "चार": "4", "chaar": "4", "char": "4",
    "நான்கு": "4", "நாலு": "4", "naangu": "4", "naalu": "4",
    "ನಾಲ್ಕು": "4", "naalku": "4", "nalku": "4",

    "five": "5",
    "ఐదు": "5", "aidu": "5", "ayidu": "5", "ఫైవ్": "5",
    "पाँच": "5", "पांच": "5", "paanch": "5", "panch": "5",
    "ஐந்து": "5", "அஞ்சு": "5", "aindhu": "5", "anju": "5",
    "ಐದು": "5",

    "six": "6",
    "ఆరు": "6", "aaru": "6", "aru": "6", "సిక్స్": "6",
    "छह": "6", "छ:": "6", "chhah": "6", "chhe": "6",
    "ஆறு": "6",
    "ಆರು": "6",

    "seven": "7",
    "ఏడు": "7", "yedu": "7", "edu": "7", "సెవెన్": "7",
    "सात": "7", "saat": "7",
    "ஏழு": "7", "ezhu": "7", "elu": "7",
    "ಏಳು": "7", "yelu": "7",

    "eight": "8", "ate": "8",
    "ఎనిమిది": "8", "enimidi": "8", "yenimidi": "8", "ఎన్మిది": "8", "enmidi": "8", "ఎయిట్": "8",
    "आठ": "8", "aath": "8", "aat": "8",
    "எட்டு": "8", "ettu": "8",
    "ಎಂಟು": "8", "entu": "8",

    "nine": "9",
    "తొమ్మిది": "9", "tommidi": "9", "thommidi": "9", "నైన్": "9",
    "नौ": "9", "nau": "9",
    "ஒன்பது": "9", "onbadhu": "9", "onbathu": "9",
    "ಒಂಬತ್ತು": "9", "ombattu": "9",
}

SPOKEN_TENS_WORDS_MAP: Dict[str, int] = {
    # English tens & teens
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,

    # Telugu tens & teens
    "పది": 10, "padi": 10,
    "పదకొండు": 11, "padakondu": 11,
    "పన్నెండు": 12, "pannendu": 12,
    "పదమూడు": 13, "padamoodu": 13,
    "పద్నాలుగు": 14, "padnaalugu": 14,
    "పదిహేను": 15, "padihenu": 15,
    "పదహారు": 16, "padahaaru": 16,
    "పదిహేడు": 17, "padihedu": 17,
    "పద్దెనిమిది": 18, "paddenimidi": 18,
    "పంతొమ్మిది": 19, "panthommidi": 19,
    "ఇరవై": 20, "ఇరువై": 20, "iravai": 20, "iravay": 20,
    "ముప్పై": 30, "muppai": 30, "muppay": 30,
    "నలభై": 40, "నలబై": 40, "nalabhai": 40, "nalbhai": 40, "nalaphai": 40,
    "యాభై": 50, "యాబై": 50, "yabhai": 50, "yabai": 50,
    "అరవై": 60, "aravai": 60, "aravay": 60,
    "డెబ్బై": 70, "debbai": 70, "debbay": 70,
    "ఎనభై": 80, "ఎనబై": 80, "enabhai": 80, "yenabhai": 80,
    "తొంభై": 90, "తొంబై": 90, "tombhai": 90, "thombai": 90, "thombhai": 90,

    # Hindi tens & teens
    "दस": 10, "das": 10, "बीस": 20, "bees": 20, "तीस": 30, "tees": 30,
    "चालीस": 40, "chalis": 40, "पचास": 50, "pachaas": 50, "साठ": 60, "saath": 60,
    "सत्तर": 70, "sattar": 70, "अस्सी": 80, "assi": 80, "नब्बे": 90, "nabbe": 90,
    "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15, "सोलह": 16,
    "सत्रह": 17, "अठारह": 18, "उन्नीस": 19,
}

DOUBLE_TOKENS = {"double", "డబుల్", "डबल", "டபுள்", "ಡಬಲ್"}
TRIPLE_TOKENS = {"triple", "ట్రిపుల్", "ट्रिपल", "ட்ரிபிள்", "ಟ್ರಿಪಲ್"}


def normalize_spoken_phone_number(text: str) -> Optional[str]:
    """
    Normalizes spoken phone number representations across English, Telugu, Hindi, Tamil, and Kannada.
    Supports continuous digit strings, spaced digits, spoken digit words, spoken pairs/tens (e.g. ninety eight, తొంభై ఎనిమిది),
    Indic numerals, natural conversational corrections (e.g. 'wait no', 'కాదు', 'wait not 0, 1'), and multipliers (double/triple).
    Strictly validates Indian mobile format (^[6-9]\\d{9}$). Rejects incomplete, malformed, non-phone dates/times, or non-Indian sequences.
    """
    if not text or not text.strip():
        return None

    # Step 1: Pre-process Indic numerals to ASCII digits
    processed = text
    for k, v in INDIC_DIGITS_MAP.items():
        processed = processed.replace(k, v)

    # Check if input has explicit conversational correction keywords
    has_correction = bool(re.search(r"\b(?:wait|no|not|sorry|actually|but|instead|or)\b|[కాదు|మార్పు|చివర]", processed, re.IGNORECASE))

    # Step 2: Check for explicit raw 10-digit patterns in text
    raw_candidates = re.findall(r"\b(?:\+?91[\s-]?|0)?([6-9]\d{9})(?!\d)", processed)
    if raw_candidates:
        chosen = raw_candidates[-1]
        # Check tail correction e.g. 'wait not 0, 1' or 'కాదు 1'
        idx = processed.rfind(chosen)
        if idx != -1:
            tail = processed[idx + len(chosen):]
            m_tail = re.search(
                r"(?:not\s+\d+\s*[,]?\s*|last\s+digit\s+(?:is\s+)?|sorry\s+|కాదు\s+|actually\s+)([0-9]|one|two|three|four|five|six|seven|eight|nine|zero|ఒకటి|రెండు|మూడు|నాలుగు|ఐదు|ఆరు|ఏడు|ఎనిమిది|తొమ్మిది|సున్నా)",
                tail,
                re.IGNORECASE,
            )
            if m_tail:
                val = m_tail.group(1).lower()
                c_digit = SPOKEN_DIGIT_WORDS_MAP.get(val, val if val.isdigit() else None)
                if c_digit:
                    chosen = chosen[:-1] + c_digit
        return chosen

    # Fast rejection of over-length raw digit tokens when no correction keyword is present
    for tok in re.findall(r"\d+", processed):
        cleaned_tok = re.sub(r"^(?:91|0)", "", tok)
        if len(cleaned_tok) > 10 and not has_correction:
            return None

    # Step 3: Tokenize words and numbers
    tokens = re.findall(r"[A-Za-z\u0C00-\u0C7F\u0900-\u097F\u0B80-\u0BFF\u0C80-\u0CFF\d]+", processed.lower())
    digits = []
    multiplier = 1
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in DOUBLE_TOKENS:
            multiplier = 2
            i += 1
            continue
        elif tok in TRIPLE_TOKENS:
            multiplier = 3
            i += 1
            continue

        # Check for tens + unit word e.g. 'ninety eight' (98) or 'తొంభై ఎనిమిది' (98)
        if tok in SPOKEN_TENS_WORDS_MAP and SPOKEN_TENS_WORDS_MAP[tok] >= 20 and i + 1 < len(tokens):
            next_tok = tokens[i + 1]
            if next_tok in SPOKEN_DIGIT_WORDS_MAP and SPOKEN_DIGIT_WORDS_MAP[next_tok] != "0":
                val = SPOKEN_TENS_WORDS_MAP[tok] + int(SPOKEN_DIGIT_WORDS_MAP[next_tok])
                for ch in str(val):
                    digits.extend([ch] * multiplier)
                multiplier = 1
                i += 2
                continue

        # Standalone tens or teens (e.g. 'twenty' -> 20, 'fifteen' -> 15, 'పది' -> 10)
        if tok in SPOKEN_TENS_WORDS_MAP:
            for ch in str(SPOKEN_TENS_WORDS_MAP[tok]):
                digits.extend([ch] * multiplier)
            multiplier = 1
            i += 1
            continue

        # Single spoken digit word (e.g. 'nine' -> 9, 'తొమ్మిది' -> 9)
        if tok in SPOKEN_DIGIT_WORDS_MAP:
            d = SPOKEN_DIGIT_WORDS_MAP[tok]
            digits.extend([d] * multiplier)
            multiplier = 1
            i += 1
            continue

        # Direct numeric digits inside token
        if tok.isdigit():
            for char in tok:
                digits.extend([char] * multiplier)
            multiplier = 1
            i += 1
            continue

        i += 1

    digit_str = "".join(digits)
    # Strip country code +91 or 91 if followed by 10 digits starting with 6-9
    if len(digit_str) == 12 and digit_str.startswith("91") and digit_str[2] in "6789":
        digit_str = digit_str[2:]
    # Strip leading trunk prefix 0 if followed by 10 digits starting with 6-9
    elif len(digit_str) == 11 and digit_str.startswith("0") and digit_str[1] in "6789":
        digit_str = digit_str[1:]

    # Require EXACTLY 10 digits starting with 6, 7, 8, or 9
    if len(digit_str) == 10 and digit_str[0] in "6789":
        return digit_str

    # If stream contains more digits (e.g. conversational correction), pick the last valid 10-digit Indian sequence
    if has_correction and len(digit_str) > 10:
        m = re.findall(r"[6-9]\d{9}", digit_str)
        if m:
            return m[-1]

    return None


def normalize_phone(phone: str) -> str:
    """Strips formatting, spoken words, and ensures valid 10-digit phone representation."""
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
    if len(clean) == 10:
        return clean
    return ""


def format_phone_grouped(phone: str) -> str:
    """Formats a 10-digit mobile number into clean customary Indian grouping 'XXXXX XXXXX' (e.g. '98490 12345')."""
    norm = normalize_phone(phone)
    if len(norm) == 10:
        return f"{norm[:5]} {norm[5:]}"
    return phone.strip()


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

