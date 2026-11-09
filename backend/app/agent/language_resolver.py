"""
MediVoice AI — Centralized Adaptive Language Resolver

Supports dynamic per-turn language switching across 5 hospital languages:
- English: en
- Telugu: te
- Hindi: hi
- Tamil: ta
- Kannada: kn

Features:
- Primary supported recognition languages: English (en) and Telugu (te) + natural code-mixing.
- Robust foreign script rejection: Gujarati, Malayalam, Bengali, Gurmukhi, Odia do NOT trigger language flips.
- Devanagari danda safeguard: Danda punctuation (। / ॥) is excluded from Hindi letter counts.
- Adaptive per-turn language detection for multilingual patient interactions.
- Preserves code-mixed sentences (e.g., Telugu with English clinical terms).
- Entity safeguard: Short doctor names, departments, dates, times, patient info, and affirmations do NOT trigger false language switches.
- Explicit language switch commands ("speak in english", "తెలుగులో మాట్లాడండి", "switch to auto").
- Dual-mode support: "auto" (adaptive per-turn detection) and "manual" (user-pinned language).
- Graceful retention of previous reliable language on uncertain or noisy speech.
- Structured diagnostics telemetry for observability.
"""

import re
import logging
from typing import Optional, Tuple, Dict, Any, List

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("en", "te", "hi", "ta", "kn")

LANGUAGE_NAMES: Dict[str, str] = {
    "en": "English",
    "te": "Telugu",
    "hi": "Hindi",
    "ta": "Tamil",
    "kn": "Kannada",
}

# Explicit language switch command patterns
EXPLICIT_LANGUAGE_COMMANDS: List[Tuple[str, str, str]] = [
    # (language_code, mode, regex_pattern)
    ("auto", "auto", r"(?:\b(?:switch\s+to\s+auto(?:matic)?|auto\s+mode|auto\s+detect(?:ion)?|automatic\s+language|detect\s+language\s+automatically)\b|స్వయంచాలక|ఆటో\s*మోడ్|ऑटो\s*मोड)"),
    ("en", "manual", r"(?:\b(?:speak\s+in\s+english|talk\s+in\s+english|switch\s+to\s+english|english\s+please|english\s+lo\s+matladandi|english\s+me\s+baat\s+karo|english\s+il\s+pesunga|english\s+nalli\s+mathanadi|in\s+english|please\s+speak\s+english|can\s+we\s+speak\s+in\s+english)\b|ఇంగ్లీష్‌లో\s*మాట్లాడండి|अंग्रेजी\s*में\s*बात\s*करें)"),
    ("te", "manual", r"(?:\b(?:speak\s+in\s+telugu|talk\s+in\s+telugu|switch\s+to\s+telugu|telugu\s+please|telugu\s+lo\s+matladandi|telugulo\s+matladandi|in\s+telugu|please\s+speak\s+telugu)\b|తెలుగులో\s*మాట్లాడండి|తెలుగులో\s*చెప్పండి|తెలుగు\s*మాట్లాడండి)"),
    ("hi", "manual", r"(?:\b(?:speak\s+in\s+hindi|talk\s+in\s+hindi|switch\s+to\s+hindi|hindi\s+please|hindi\s+me\s+baat\s+karo|in\s+hindi|please\s+speak\s+hindi)\b|हिंदी\s*में\s*बात\s*करो|हिंदी\s*में\s*बोलिए|हिंदी\s*बोलिए)"),
    ("ta", "manual", r"(?:\b(?:speak\s+in\s+tamil|talk\s+in\s+tamil|switch\s+to\s+tamil|tamil\s+please|tamil\s+il\s+pesunga|in\s+tamil|please\s+speak\s+tamil)\b|தமிழில்\s*பேசுங்கள்|தமிழ்\s*பேசுங்கள்)"),
    ("kn", "manual", r"(?:\b(?:speak\s+in\s+kannada|talk\s+in\s+kannada|switch\s+to\s+kannada|kannada\s+please|kannada\s+dalli\s+mathanadi|in\s+kannada|please\s+speak\s+kannada)\b|ಕನ್ನಡದಲ್ಲಿ\s*ಮಾತನಾಡಿ|ಕನ್ನಡ\s*ಮಾತನಾಡಿ)"),
]

# Prefix format: "Telugu: ...", "తెలుగు: ..."
LANGUAGE_PREFIX_MAP: List[Tuple[str, str]] = [
    ("te", r"^\s*(?:telugu|తెలుగు)\s*[:\-]\s*(.+)$"),
    ("ta", r"^\s*(?:tamil|தமிழ்)\s*[:\-]\s*(.+)$"),
    ("kn", r"^\s*(?:kannada|ಕನ್ನಡ)\s*[:\-]\s*(.+)$"),
    ("hi", r"^\s*(?:hindi|हिन्दी|हिंदी)\s*[:\-]\s*(.+)$"),
    ("en", r"^\s*(?:english|ఇంగ్లీష్|ஆங்கிலம்|ಇಂಗ್ಲಿಷ್|अंग्रेजी)\s*[:\-]\s*(.+)$"),
]

# Doctor candidate names at Aarogya One Hospital
HOSPITAL_DOCTOR_NAMES = {
    "rajesh sharma", "dr rajesh sharma", "dr. rajesh sharma", "dr rajesh", "dr. rajesh", "rajesh",
    "sunita rao", "dr sunita rao", "dr. sunita rao", "dr sunita", "dr. sunita", "sunita",
    "priya nair", "dr priya nair", "dr. priya nair", "dr priya", "dr. priya", "priya",
    "arvind kumar", "dr arvind kumar", "dr. arvind kumar", "dr arvind", "dr. arvind", "arvind",
    "vikram", "dr vikram", "dr. vikram", "vikram deshmukh", "dr vikram deshmukh",
}

# Standalone clinical departments and specialties
CLINICAL_SPECIALTIES = {
    "cardiology", "cardiologist", "cardiac",
    "neurology", "neurologist",
    "orthopedics", "orthopedic", "orthopedist",
    "pediatrics", "pediatrician",
    "general medicine", "general physician", "physician", "internal medicine",
    "dermatology", "dermatologist",
    "ent", "ophthalmology", "gynecology", "urology", "oncology",
}


def detect_explicit_language_command(text: str) -> Tuple[Optional[str], Optional[str], str]:
    """
    Detects whether the patient is issuing an explicit language switch command.
    Returns (target_lang_code, target_mode, remaining_message_text).
    """
    if not text or not text.strip():
        return None, None, ""

    stripped = text.strip()

    # 1. Check command phrases like "speak in english", "switch to auto"
    for lang_code, mode, pattern in EXPLICIT_LANGUAGE_COMMANDS:
        m = re.search(pattern, stripped, flags=re.IGNORECASE)
        if m:
            remaining = (stripped[: m.start()] + " " + stripped[m.end() :]).strip(" ,.:;-!?")
            return lang_code, mode, remaining

    # 2. Check prefix syntax: "Telugu: <text>"
    for lang_code, pattern in LANGUAGE_PREFIX_MAP:
        m = re.match(pattern, stripped, flags=re.IGNORECASE)
        if m:
            return lang_code, "manual", m.group(1).strip()

    # 3. Check single standalone language name utterance
    low_single = stripped.lower().strip(" .!?,;")
    single_word_map = {
        "telugu": "te", "తెలుగు": "te",
        "english": "en", "ఇంగ్లీష్": "en", "ஆங்கிலம்": "en", "ಇಂಗ್ಲಿಷ್": "en", "अंग्रेजी": "en",
        "hindi": "hi", "हिंदी": "hi", "हिन्दी": "hi",
        "tamil": "ta", "தமிழ்": "ta",
        "kannada": "kn", "ಕನ್ನಡ": "kn",
        "auto": "auto", "automatic": "auto",
    }
    if low_single in single_word_map:
        target = single_word_map[low_single]
        mode = "auto" if target == "auto" else "manual"
        return target, mode, ""

    return None, None, stripped


def is_entity_only_or_patient_info(text: str) -> bool:
    """
    Safeguard: Detects whether an utterance consists strictly of:
    - Doctor name (e.g. 'Dr. Rajesh Sharma', 'Rajesh Sharma')
    - Clinical specialty (e.g. 'Cardiology', 'General Physician')
    - Standalone date/time/slot (e.g. '10:00 AM', '10 AM', '2026-11-06', 'slot-101')
    - Patient registration input (e.g. 'my name is Ravi', 10-digit phone, reference ID)
    - Hospital name ('Aarogya One Hospital')
    - Short acknowledgments and affirmations across languages (e.g. 'ok', 'yes', 'సరే', 'అవును')

    Entity-only inputs must NOT trigger unintended language switches.
    """
    if not text or not text.strip():
        return False

    clean = text.strip().strip(".!?,;:").lower()
    raw_clean = text.strip().strip(".!?,;:")

    # Doctor name only
    if clean in HOSPITAL_DOCTOR_NAMES:
        return True
    if re.match(r"^(?:dr\.?|doctor)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?$", raw_clean):
        return True

    # Department only
    if clean in CLINICAL_SPECIALTIES:
        return True

    # Time or slot only: '10:00 am', '10 am', '11:30', 'slot-101', '2026-11-06'
    if re.match(r"^(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|\d{4}-\d{2}-\d{2}|slot-[a-z0-9_-]+)$", clean):
        return True

    # Patient registration / info only: 'my name is ...', 'name is ...', phone number, pat-ref
    if re.match(r"^(?:my\s+name\s+is|name\s+is|i\s+am)\s+[a-z]+(?:\s+[a-z]+)?$", clean):
        return True
    if re.match(r"^\d{10}$", clean) or re.match(r"^pat-\d+-[a-z0-9-]+$", clean):
        return True

    # Single-word conversational acknowledgments / affirmations (English, Telugu, Hindi, Tamil, Kannada)
    acknowledgments = {
        "yes", "no", "ok", "okay", "sure", "alright", "yep", "yeah", "nope", "fine",
        "సరే", "అవును", "అలాగే", "వద్దు", "avunu", "sare", "alage", "vaddu",
        "haan", "nahi", "theek hai", "theek", "ha", "na",
        "சரி", "ஆம்", "இல்லை",
        "ಸರಿ", "ಹೌದು", "ಬೇಡ",
    }
    if clean in acknowledgments:
        return True

    # Uncertainty / doctor preference responses (e.g. 'i don't know which doctor', 'i don't know', 'not sure')
    if clean in ("i don't know which doctor", "i dont know which doctor", "i don't know", "i dont know", "not sure"):
        return True

    # Hospital name only
    if clean in ("aarogya one", "aarogya one hospital", "aarogya hospital"):
        return True

    return False


def detect_unsupported_foreign_script(text: str) -> Optional[str]:
    """
    Detects if text contains characters from unsupported Indian scripts:
    - Gujarati: 0x0A80 - 0x0AFF
    - Malayalam: 0x0D00 - 0x0D7F
    - Bengali/Assamese: 0x0980 - 0x09FF
    - Gurmukhi: 0x0A00 - 0x0A7F
    - Odia: 0x0B00 - 0x0B7F
    
    Returns the script name if >= 2 characters are found, else None.
    """
    if not text:
        return None

    counts = {"gujarati": 0, "malayalam": 0, "bengali": 0, "gurmukhi": 0, "odia": 0}
    for ch in text:
        cp = ord(ch)
        if 0x0A80 <= cp <= 0x0AFF:
            counts["gujarati"] += 1
        elif 0x0D00 <= cp <= 0x0D7F:
            counts["malayalam"] += 1
        elif 0x0980 <= cp <= 0x09FF:
            counts["bengali"] += 1
        elif 0x0A00 <= cp <= 0x0A7F:
            counts["gurmukhi"] += 1
        elif 0x0B00 <= cp <= 0x0B7F:
            counts["odia"] += 1

    max_script = max(counts, key=counts.get)
    if counts[max_script] >= 2:
        return max_script
    return None


def detect_script_language(text: str) -> Optional[str]:
    """
    Detects dominant supported Indic script in text:
    - Telugu: 0x0C00 - 0x0C7F
    - Tamil: 0x0B80 - 0x0BFF
    - Kannada: 0x0C80 - 0x0CFF
    - Hindi: Devanagari letters (0x0904-0x0939, 0x0958-0x0961, 0x093E-0x094F)
    
    CRITICAL: Excludes Devanagari danda (U+0964, U+0965) and digits from Hindi count
    so that Gujarati, Bengali, or Marathi sentences ending with danda do NOT falsely classify as Hindi!
    Requires at least 2 script characters (and at least 3 for Hindi).
    """
    if not text:
        return None

    counts = {"te": 0, "ta": 0, "kn": 0, "hi": 0}
    for ch in text:
        cp = ord(ch)
        if 0x0C00 <= cp <= 0x0C7F:
            counts["te"] += 1
        elif 0x0B80 <= cp <= 0x0BFF:
            counts["ta"] += 1
        elif 0x0C80 <= cp <= 0x0CFF:
            counts["kn"] += 1
        elif (0x0904 <= cp <= 0x0939) or (0x0958 <= cp <= 0x0961) or (0x093E <= cp <= 0x094F):
            # True Devanagari alphabet letters and matras only (excluding danda \u0964, \u0965 and digits)
            counts["hi"] += 1

    max_indic = max(counts, key=counts.get)
    max_count = counts[max_indic]
    if max_indic == "hi" and max_count < 3:
        return None
    if max_count >= 2:
        return max_indic
    return None


def detect_romanized_language(text: str) -> Optional[str]:
    """
    Detects transliterated / Romanized Indic words in Latin script
    (Tenglish, Hinglish, Tanglish, Kanglish).
    """
    if not text:
        return None

    low = text.lower()

    # Telugu Romanized markers (common conversational and clinical terms)
    if re.search(
        r"\b(telugu|naaku|naku|aku|edo|mana|teesukovali|kavali|kaavali|avunu|sare|alage|chupinchandi|vaddu|chey|cheyyi|cheyyandi|namaskaram|dhanyavadalu|gunde|noppi|chati|chaati|talanoppi|jwaram|daggu|jalubu|emo|teliyadu|teleedu|telidu|evaru|evvaru|evarni|kalavali|cheppandi|cheppara|garitho|raddu|marpu|modati|rendava|sahayam|ibbandi|oopiri|upiri|chematalu|teevramaina|bheema|bhima|parikshana|rakta|repu|ellundi|undha|unda|unnara|unnaru|udayam|madhyahnam|sayantram|gantala|gantalaku|gantalu|marchandi|marchu|marusthara|kaadu|kadu|matladandi|ivvandi|chudandi|choodandi|kosam|kudurutunda|kudurthunda|thone|thoti|thoni|garithone|varithone|entha|yentha|ekkada|eppudu|ela|enti|yenti|emiti|endi|emina|koddiga|koncham)\b",
        low,
    ):
        return "te"

    # Hindi Romanized markers
    if re.search(
        r"\b(hindi|mujhe|mera|meri|chahiye|haan|nahi|namaste|shukriya|dhanyawad|seene|dard|dil|bukhar|khansi|sirdard|ghutne|kripaya|bataiye|pahla|pehla|doosra|kab|kahan|kaise|pata|shayad|samajh|dikhaun|kaun|kis|tez|gambhir|saans|theek|dikhaiye|dikhao|bima|beema|jaanch|janch|kal|subah|sham|baje|badlo|karo|baat)\b",
        low,
    ):
        return "hi"

    # Tamil Romanized markers
    if re.search(
        r"\b(tamil|enakku|vendum|venum|vendaam|vendam|vanakkam|nanri|nenju|vali|idhayam|idhaya|thalaivali|kaichal|irumal|theriyavillai|theriyala|theriyadhu|theriyathu|yaarai|endha|sollunga|maruthuvar|mudhal|irandavadhu|kadumaiyana|moochu|kaattungal|kaapeedu|kappidu|parichothanai|parisotanai|iratha|nalaikku|kaalai|maalai|mani|mathunga|maathu|pannunga|seiyunga|pesunga)\b",
        low,
    ):
        return "ta"

    # Kannada Romanized markers
    if re.search(
        r"\b(kannada|nanage|beku|bekagide|haudu|beda|namaskara|dhanyavada|ede|novu|hrudaya|talenovu|jwara|kemmu|gottilla|gothilla|tilidilla|thilidilla|yaava|yaaru|vaidyaru|dayavittu|modala|eradane|teevra|usiratada|torisi|thorisi|agali|vime|parikshe|varadi|naale|beligge|sanje|gante|badalisi|madi|mathanadi)\b",
        low,
    ):
        return "kn"

    return None


def detect_english_utterance(text: str) -> bool:
    """
    Detects whether text is an English conversational request or inquiry,
    verifying it contains English grammatical/conversational markers and no Indic tokens.
    """
    if not text:
        return False

    # If any Indic script is present, it is not pure English
    if detect_script_language(text) is not None:
        return False

    # If any unsupported foreign Indic script is present, it is not English
    if detect_unsupported_foreign_script(text) is not None:
        return False

    # If Romanized Indic tokens are present, it is code-mixed Indic, not pure English
    if detect_romanized_language(text) is not None:
        return False

    low = text.lower()
    english_words = re.findall(r"\b[a-z']+\b", low)
    if not english_words:
        return False

    # Avoid classifying single isolated greetings or affirmations as a reason to switch language
    if len(english_words) == 1 and english_words[0] in ("yes", "no", "ok", "okay", "sure", "hi", "hello", "hey"):
        return False

    # English functional words & grammatical vocabulary
    english_cues = {
        "can", "could", "will", "would", "shall", "should", "may", "might", "must",
        "do", "does", "did", "have", "has", "had", "is", "am", "are", "was", "were", "be", "been",
        "i", "me", "my", "you", "your", "we", "us", "our", "he", "him", "his", "she", "her", "they", "them",
        "what", "which", "who", "whom", "where", "when", "why", "how",
        "book", "booking", "schedule", "want", "need", "prefer", "visit", "see", "check", "tell",
        "confirm", "cancel", "change", "help", "know", "get", "like", "find", "show",
        "please", "thank", "thanks",
        "morning", "afternoon", "evening", "tomorrow", "today", "yesterday",
        "available", "availability", "slot", "slots", "time",
        "appointment", "appointments", "doctor", "doctors", "physician", "department",
        "specialty", "hospital", "clinic", "fee", "consultation", "cost", "report", "test",
        "insurance", "details", "information", "of", "course", "about",
    }

    matching = sum(1 for w in english_words if w in english_cues)
    return matching >= 1


def resolve_adaptive_language_with_details(
    text: str,
    current_session_language: str = "en",
    language_mode: str = "auto",
    preferred_language: Optional[str] = None,
    stt_detected_language: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Centralized Adaptive Language Resolver with structured diagnostic details.
    
    Guarantees:
    - Primary support for English (en) and Telugu (te) + natural code-mixing.
    - Foreign Indian scripts (Gujarati, Malayalam, Bengali, etc.) are detected and safely rejected,
      retaining the reliable session language.
    - Single noisy turns or ambiguous tokens do NOT corrupt conversation state.
    - Entity safeguard prevents doctor names, slots, dates, and short affirmations from switching languages.
    """
    safe_curr = current_session_language if current_session_language in SUPPORTED_LANGUAGES else "en"

    if not text or not text.strip():
        return {
            "resolved_language": safe_curr,
            "active_mode": language_mode,
            "decision": "empty_input_retained",
            "detected_script": None,
            "foreign_script": None,
            "romanized_language": None,
            "previous_language": current_session_language,
            "stt_detected_language": stt_detected_language,
        }

    # 1. Check for explicit language switch commands in utterance
    cmd_lang, cmd_mode, remaining = detect_explicit_language_command(text)
    if cmd_lang:
        if cmd_lang == "auto":
            if remaining:
                sub_res = resolve_adaptive_language_with_details(
                    remaining,
                    current_session_language=safe_curr,
                    language_mode="auto",
                    preferred_language=None,
                    stt_detected_language=stt_detected_language,
                )
                sub_res["decision"] = "explicit_command_auto_with_content"
                return sub_res
            return {
                "resolved_language": safe_curr,
                "active_mode": "auto",
                "decision": "explicit_command_auto",
                "detected_script": None,
                "foreign_script": None,
                "romanized_language": None,
                "previous_language": current_session_language,
                "stt_detected_language": stt_detected_language,
            }
        elif cmd_lang in SUPPORTED_LANGUAGES:
            return {
                "resolved_language": cmd_lang,
                "active_mode": cmd_mode or "manual",
                "decision": "explicit_command_switch",
                "detected_script": None,
                "foreign_script": None,
                "romanized_language": None,
                "previous_language": current_session_language,
                "stt_detected_language": stt_detected_language,
            }

    # 2. If in manual mode and preferred language is set, respect user's manual choice
    if language_mode == "manual" and preferred_language in SUPPORTED_LANGUAGES:
        return {
            "resolved_language": preferred_language,
            "active_mode": "manual",
            "decision": "manual_preference_pinned",
            "detected_script": None,
            "foreign_script": None,
            "romanized_language": None,
            "previous_language": current_session_language,
            "stt_detected_language": stt_detected_language,
        }

    # 3. Unsupported Foreign Indic Script Safeguard (Gujarati, Malayalam, Bengali, etc.)
    # Reject foreign scripts caused by STT hallucination on noisy or code-mixed audio; retain session language.
    foreign_script = detect_unsupported_foreign_script(text)
    if foreign_script:
        logger.info(
            "Foreign script detected (%s); retaining reliable session language '%s'",
            foreign_script, safe_curr
        )
        return {
            "resolved_language": safe_curr,
            "active_mode": language_mode,
            "decision": "unsupported_foreign_script_retained",
            "detected_script": None,
            "foreign_script": foreign_script,
            "romanized_language": None,
            "previous_language": current_session_language,
            "stt_detected_language": stt_detected_language,
        }

    # 4. Native Indian script detection (Telugu, Tamil, Kannada, Hindi)
    script_lang = detect_script_language(text)
    if script_lang in SUPPORTED_LANGUAGES:
        return {
            "resolved_language": script_lang,
            "active_mode": "auto",
            "decision": "script_detected",
            "detected_script": script_lang,
            "foreign_script": None,
            "romanized_language": None,
            "previous_language": current_session_language,
            "stt_detected_language": stt_detected_language,
        }

    # 5. Entity / Short affirmation safeguard:
    # Doctor names, departments, dates, times, patient info, and short affirmations (ok, yes)
    # in Latin script do NOT cause an unwanted language switch away from an active session language.
    if is_entity_only_or_patient_info(text):
        return {
            "resolved_language": safe_curr,
            "active_mode": language_mode,
            "decision": "entity_safeguard_retained",
            "detected_script": None,
            "foreign_script": None,
            "romanized_language": None,
            "previous_language": current_session_language,
            "stt_detected_language": stt_detected_language,
        }

    # 6. Romanized / Transliterated Indic detection (Tenglish, Hinglish, Tanglish, Kanglish)
    romanized_lang = detect_romanized_language(text)
    if romanized_lang in SUPPORTED_LANGUAGES:
        return {
            "resolved_language": romanized_lang,
            "active_mode": "auto",
            "decision": "romanized_detected",
            "detected_script": None,
            "foreign_script": None,
            "romanized_language": romanized_lang,
            "previous_language": current_session_language,
            "stt_detected_language": stt_detected_language,
        }

    # 7. English conversational detection
    if detect_english_utterance(text):
        return {
            "resolved_language": "en",
            "active_mode": "auto",
            "decision": "english_detected",
            "detected_script": None,
            "foreign_script": None,
            "romanized_language": None,
            "previous_language": current_session_language,
            "stt_detected_language": stt_detected_language,
        }

    # 8. Reliable STT detected language fallback
    # Only trust STT detected language if it is a known supported language and not 'uncertain'.
    # If the active session is Telugu and STT reported English but the text has no English words, retain Telugu!
    if stt_detected_language and stt_detected_language in SUPPORTED_LANGUAGES and stt_detected_language != "uncertain":
        if safe_curr == "te" and stt_detected_language == "en" and not detect_english_utterance(text):
            return {
                "resolved_language": "te",
                "active_mode": language_mode,
                "decision": "telugu_protected_against_false_stt_en",
                "detected_script": None,
                "foreign_script": None,
                "romanized_language": None,
                "previous_language": current_session_language,
                "stt_detected_language": stt_detected_language,
            }
        return {
            "resolved_language": stt_detected_language,
            "active_mode": "auto",
            "decision": "stt_fallback",
            "detected_script": None,
            "foreign_script": None,
            "romanized_language": None,
            "previous_language": current_session_language,
            "stt_detected_language": stt_detected_language,
        }

    # 9. Safe Fallback: Preserve active session language
    return {
        "resolved_language": safe_curr,
        "active_mode": language_mode,
        "decision": "session_fallback",
        "detected_script": None,
        "foreign_script": None,
        "romanized_language": None,
        "previous_language": current_session_language,
        "stt_detected_language": stt_detected_language,
    }


def resolve_adaptive_language(
    text: str,
    current_session_language: str = "en",
    language_mode: str = "auto",
    preferred_language: Optional[str] = None,
    stt_detected_language: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Centralized Adaptive Language Resolver.
    
    Determines the turn's effective language and mode:
    1. Explicit language-switch command in utterance -> switches immediately.
    2. Manual mode with pinned language -> respects manual preference unless explicitly commanded.
    3. Unsupported foreign script safeguard -> retains current reliable session language.
    4. Entity safeguard (doctor names, slots, dates, affirmations) -> preserves current session language.
    5. Native Indian script detection -> resolves to Telugu/Tamil/Kannada/Hindi.
    6. Romanized Indic detection -> resolves code-mixed speech.
    7. English conversational detection -> resolves to English.
    8. Falls back safely to STT detected language or current session language.
    
    Returns (resolved_language, active_mode).
    """
    details = resolve_adaptive_language_with_details(
        text=text,
        current_session_language=current_session_language,
        language_mode=language_mode,
        preferred_language=preferred_language,
        stt_detected_language=stt_detected_language,
    )
    return details["resolved_language"], details["active_mode"]
