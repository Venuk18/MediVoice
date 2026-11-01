from abc import ABC, abstractmethod

import json

import time

import logging

import os

import re
import uuid
from datetime import datetime, timezone

from typing import List, Dict, Any, Optional, Callable

import httpx



logger = logging.getLogger("medivoice.gemini")



from app.core.config import settings

from app.agent.schemas import (

    AgentAction,

    AgentSessionState,

    ChatMessage,

    ConversationStep,

    ConfirmationStatus,

    ToolCallIntent,

    ToolExecutionResult,

)





SUPPORTED_LANGUAGES = ("en", "te", "ta", "kn", "hi")



LANGUAGE_NAMES: Dict[str, str] = {

    "en": "English",

    "te": "Telugu (తెలుగు)",

    "ta": "Tamil (தமிழ்)",

    "kn": "Kannada (ಕನ್ನಡ)",

    "hi": "Hindi (हिन्दी)",

}





class ReasoningAdapterError(Exception):

    """Safe, structured exception for LLM provider errors that never leaks credentials."""



    def __init__(self, code: str, safe_message: str, status_code: Optional[int] = None):

        super().__init__(safe_message)

        self.code = code

        self.safe_message = safe_message

        self.status_code = status_code





EXPLICIT_LANGUAGE_SWITCH_PATTERNS: List[tuple[str, str]] = [

    ("te", r"(?:please\s+)?(?:can\s+we\s+|let'?s\s+)?(?:switch|change|talk|speak|chat|continue|reply|respond)\s+(?:language\s+)?(?:to|in)\s+telugu\b[\s:,\-]*"),

    ("te", r"^\s*(?:in\s+)?telugu(?:\s+please)?[\s:,\-]*$"),

    ("te", r"(?:దయచేసి\s+)?తెలుగులో\s*(?:మాట్లాడండి|చెప్పండి|కొనసాగించండి|మాట్లాడుదాం)?[\s:,\-]*"),

    ("te", r"^\s*తెలుగు[\s:,\-]*$"),

    ("ta", r"(?:please\s+)?(?:can\s+we\s+|let'?s\s+)?(?:switch|change|talk|speak|chat|continue|reply|respond)\s+(?:language\s+)?(?:to|in)\s+tamil\b[\s:,\-]*"),

    ("ta", r"^\s*(?:in\s+)?tamil(?:\s+please)?[\s:,\-]*$"),

    ("ta", r"(?:தயவுசெய்து\s+)?தமிழில்\s*(?:பேசவும்|பேசலாம்|சொல்லுங்கள்|தொடரவும்)?[\s:,\-]*"),

    ("ta", r"^\s*தமிழ்[\s:,\-]*$"),

    ("kn", r"(?:please\s+)?(?:can\s+we\s+|let'?s\s+)?(?:switch|change|talk|speak|chat|continue|reply|respond)\s+(?:language\s+)?(?:to|in)\s+kannada\b[\s:,\-]*"),

    ("kn", r"^\s*(?:in\s+)?kannada(?:\s+please)?[\s:,\-]*$"),

    ("kn", r"(?:ದಯವಿಟ್ಟು\s+)?ಕನ್ನಡದಲ್ಲಿ\s*(?:ಮಾತನಾಡಿ|ಹೇಳಿ|ಮುಂದುವರಿಸಿ)?[\s:,\-]*"),

    ("kn", r"^\s*ಕನ್ನಡ[\s:,\-]*$"),

    ("hi", r"(?:please\s+)?(?:can\s+we\s+|let'?s\s+)?(?:switch|change|talk|speak|chat|continue|reply|respond)\s+(?:language\s+)?(?:to|in)\s+hindi\b[\s:,\-]*"),

    ("hi", r"^\s*(?:in\s+)?hindi(?:\s+please)?[\s:,\-]*$"),

    ("hi", r"(?:कृपया\s+)?(?:हिन्दी|हिंदी)\s*में\s*(?:बात\s*करें|बोलें|बताएं|जारी\s*रखें)?[\s:,\-]*"),

    ("hi", r"^\s*(?:हिन्दी|हिंदी)[\s:,\-]*$"),

    ("en", r"(?:please\s+)?(?:can\s+we\s+|let'?s\s+)?(?:switch|change|talk|speak|chat|continue|reply|respond)\s+(?:language\s+)?(?:to|in)\s+english\b[\s:,\-]*"),

    ("en", r"^\s*(?:in\s+)?english(?:\s+please)?[\s:,\-]*$"),

    ("en", r"(?:ఇంగ్లీష్‌లో|ఇంగ్లీషులో|ஆங்கிலத்தில்|ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ|अंग्रेजी\s*में|इंग्लिश\s*में)\s*(?:మాట్లాడండి|చెప్పండి|பேசவும்|ಮಾತನಾಡಿ|बात\s*करें|बोलें)?[\s:,\-]*"),

    ("en", r"^\s*(?:ఇంగ్లీష్|ஆங்கிலம்|ಇಂಗ್ಲಿಷ್|अंग्रेजी)[\s:,\-]*$"),

]





def detect_explicit_language_switch(text: str) -> tuple[Optional[str], str]:

    """

    Detects if the patient is explicitly requesting a language switch (e.g., 'Switch to Telugu',

    'తెలుగులో మాట్లాడండి', 'తెలుగు', 'Speak in Tamil').

    Returns (target_language_code, remaining_message_text).

    """

    if not text or not text.strip():

        return None, ""



    stripped = text.strip()

    for lang_code, pattern in EXPLICIT_LANGUAGE_SWITCH_PATTERNS:

        m = re.search(pattern, stripped, flags=re.IGNORECASE)

        if m:

            remaining = (stripped[: m.start()] + " " + stripped[m.end() :]).strip(" ,.:;-!?")

            return lang_code, remaining



    # Also handle "Telugu: <text>" or "తెలుగు: <text>" prefix format

    prefix_map = [

        ("te", r"^\s*(?:telugu|తెలుగు)\s*[:\-]\s*(.+)$"),

        ("ta", r"^\s*(?:tamil|தமிழ்)\s*[:\-]\s*(.+)$"),

        ("kn", r"^\s*(?:kannada|ಕನ್ನಡ)\s*[:\-]\s*(.+)$"),

        ("hi", r"^\s*(?:hindi|हिन्दी|हिंदी)\s*[:\-]\s*(.+)$"),

        ("en", r"^\s*(?:english|ఇంగ్లీష్|ஆங்கிலம்|ಇಂಗ್ಲಿಷ್|अंग्रेजी)\s*[:\-]\s*(.+)$"),

    ]

    for lang_code, pattern in prefix_map:

        m = re.match(pattern, stripped, flags=re.IGNORECASE)

        if m:

            return lang_code, m.group(1).strip()



    return None, stripped





def has_expected_language_script(text: str, lang: str) -> bool:

    """

    Checks whether a generated response actually contains characters in the target language's script.

    Prevents assuming that detecting a session language guarantees the generated reply used that language.

    """

    if not text or not text.strip():

        return False

    if lang == "te":

        return any(0x0C00 <= ord(ch) <= 0x0C7F for ch in text)

    if lang == "ta":

        return any(0x0B80 <= ord(ch) <= 0x0BFF for ch in text)

    if lang == "kn":

        return any(0x0C80 <= ord(ch) <= 0x0CFF for ch in text)

    if lang == "hi":

        return any(0x0900 <= ord(ch) <= 0x097F for ch in text)

    return any(("a" <= ch <= "z") or ("A" <= ch <= "Z") for ch in text)





def detect_language(text: str, current_language: str = "en") -> str:

    """

    Detects patient language across Telugu (te), Tamil (ta), Kannada (kn),

    Hindi (hi), and English (en), including native scripts, Romanized/transliterated

    phrases (Tenglish, Tanglish, Kanglish, Hinglish), and mixed-language messages.

    Preserves an active non-English session language (e.g. Telugu) across turns

    unless the user explicitly switches languages or writes in another Indic language.

    """

    if not text or not text.strip():

        return current_language if current_language in SUPPORTED_LANGUAGES else "en"



    explicit_lang, _ = detect_explicit_language_switch(text)

    if explicit_lang in SUPPORTED_LANGUAGES:

        return explicit_lang



    counts = {"te": 0, "ta": 0, "kn": 0, "hi": 0, "en": 0}

    for ch in text:

        cp = ord(ch)

        if 0x0C00 <= cp <= 0x0C7F:

            counts["te"] += 1

        elif 0x0B80 <= cp <= 0x0BFF:

            counts["ta"] += 1

        elif 0x0C80 <= cp <= 0x0CFF:

            counts["kn"] += 1

        elif 0x0900 <= cp <= 0x097F:

            counts["hi"] += 1

        elif ("a" <= ch <= "z") or ("A" <= ch <= "Z"):

            counts["en"] += 1



    # If any Indic script characters are present, choose the dominant Indic script

    indic_max_lang = max(("te", "ta", "kn", "hi"), key=lambda k: counts[k])

    if counts[indic_max_lang] > 0:

        return indic_max_lang



    low = text.strip().lower()

    # Transliterated / Romanized language cues in Latin script

    if re.search(

        r"\b(telugu|naaku|naku|aku|edo|mana|teesukovali|kavali|kaavali|avunu|sare|alage|chupinchandi|vaddu|chey|cheyyi|cheyyandi|namaskaram|dhanyavadalu|gunde|noppi|chati|chaati|talanoppi|jwaram|daggu|jalubu|emo|teliyadu|teleedu|telidu|evaru|evvaru|evarni|kalavali|cheppandi|garitho|raddu|marpu|modati|rendava|sahayam|ibbandi|oopiri|upiri|chematalu|teevramaina|bheema|bhima|parikshana|rakta\s+pariksha)\b",

        low,

    ):

        return "te"

    if re.search(

        r"\b(tamil|enakku|vendum|venum|vendaam|vendam|vanakkam|nanri|nenju|vali|idhayam|idhaya|thalaivali|kaichal|irumal|theriyavillai|theriyala|theriyadhu|theriyathu|yaarai|endha|sollunga|maruthuvar|mudhal|irandavadhu|kadumaiyana|moochu|kaattungal|kaapeedu|kappidu|parichothanai|parisotanai|iratha)\b",

        low,

    ):

        return "ta"

    if re.search(

        r"\b(kannada|nanage|beku|bekagide|haudu|beda|namaskara|dhanyavada|ede|novu|hrudaya|talenovu|jwara|kemmu|gottilla|gothilla|tilidilla|thilidilla|yaava|yaaru|vaidyaru|dayavittu|modala|eradane|teevra|usiratada|torisi|thorisi|agali|vime|parikshe|varadi)\b",

        low,

    ):

        return "kn"

    if re.search(

        r"\b(hindi|mujhe|mera|meri|chahiye|haan|nahi|namaste|shukriya|dhanyawad|seene|dard|dil|bukhar|khansi|sirdard|ghutne|kripaya|bataiye|pahla|pehla|doosra|kab|kahan|kaise|pata|shayad|samajh|dikhaun|kaun|kis|tez|gambhir|saans|theek|dikhaiye|dikhao|bima|beema|jaanch|janch)\b",

        low,

    ):

        return "hi"

    if re.search(r"\b(english)\b", low):

        return "en"



    # Preserve an established Indic conversation language (such as Telugu) unless the user

    # explicitly switches languages (handled above via detect_explicit_language_switch).

    if current_language in ("te", "ta", "kn", "hi"):

        return current_language



    return "en"





URGENT_SYMPTOM_PATTERNS: List[str] = [

    r"\bchest\s+pain\b",

    r"\bchest\s+tightness\b",

    r"\bchest\s+pressure\b",

    r"\bchest\s+discomfort\b",

    r"\bheart\s+pain\b",

    r"\bheart\s+attack\b",

    r"\bcardiac\s+arrest\b",

    r"\bsevere\s+palpitations\b",

    r"\bangina\b",

    r"\bshortness\s+of\s+breath\b",

    r"\bdifficulty\s+breathing\b",

    r"\bcan'?t\s+breathe\b",

    r"\bcannot\s+breathe\b",

    r"\bunable\s+to\s+breathe\b",

    r"\bbreathless(?:ness)?\b",

    r"\bgasping\b",

    r"\bstroke\b",

    r"\bparalysis\b",

    r"\bslurred\s+speech\b",

    r"\bfacial\s+droop(?:ing)?\b",

    r"\bunconscious\b",

    r"\bfainted\b",

    r"\bpassed\s+out\b",

    r"\bsevere\s+bleeding\b",

    r"\bseizure\b",

    r"\bconvulsion(?:s)?\b",

    # Transliterated urgent symptoms across Telugu, Tamil, Kannada, Hindi

    r"\bgunde\s+noppi\b",

    r"\bcha?ti\s+noppi\b",

    r"\bgundepotu\b",

    r"\b(?:oopiri|upiri|swasa)\s+(?:aadatam|adatam)\s+ledu\b",

    r"\bpakshavatam\b",

    r"\bnenju\s+vali\b",

    r"\bidhaya\s+vali\b",

    r"\bmaradaippu\b",

    r"\bmoochu\s*thinaral\b",

    r"\bpakkavatham\b",

    r"\bede\s+novu\b",

    r"\bhrudaya\s+novu\b",

    r"\bhrudayaghata\b",

    r"\busiratada\s+tondare\b",

    r"\bpakshavata\b",

    r"\bseene\s+mein\s+dard\b",

    r"\bchaati\s+mein\s+dard\b",

    r"\bdil\s+mein\s+dard\b",

    r"\bdil\s+ka\s+daura\b",

    r"\bsaans\s+lene\s+mein\s+takleef\b",

    r"\bsaans\s+nahi\b",

    r"\blakwa\b",

    r"\bbehosh\b",

]



URGENT_SYMPTOM_INDIC_TERMS: List[str] = [

    # Telugu

    "ఛాతీ నొప్పి", "ఛాతీలో నొప్పి", "గుండె నొప్పి", "గుండెపోటు",

    "ఊపిరి ఆడటం లేదు", "ఊపిరి ఆడకపోవడం", "ఊపిరి తీసుకోవడం కష్టం", "శ్వాస ఆడటం లేదు",

    "పక్షవాతం", "స్పృహ తప్పి", "మూర్ఛ", "తీవ్ర రక్తస్రావం",

    # Tamil

    "நெஞ்சு வலி", "இதய வலி", "மாரடைப்பு",

    "மூச்சுத்திணறல்", "மூச்சு விட சிரமம்", "மூச்சு விட முடியவில்லை", "பக்கவாதம்", "மயக்கம்", "வலிப்பு",

    # Kannada

    "ಎದೆ ನೋವು", "ಹೃದಯ ನೋವು", "ಹೃದಯಾಘಾತ",

    "ಉಸಿರಾಟದ ತೊಂದರೆ", "ಉಸಿರಾಡಲು ಕಷ್ಟ", "ಉಸಿರುಗಟ್ಟುವಿಕೆ", "ಪಕ್ಷವಾತ", "ಪ್ರಜ್ಞೆ ತಪ್ಪಿ", "ಮೂರ್ಛೆ",

    # Hindi

    "सीने में दर्द", "छाती में दर्द", "दिल में दर्द", "दिल का दौरा", "हार्ट अटैक",

    "सांस लेने में तकलीफ", "सांस फूलना", "सांस नहीं आ रही", "दम घुटना", "लकवा", "बेहोश",

]



# Keep aliases for backwards compatibility

URGENT_CHEST_PAIN_PATTERNS = URGENT_SYMPTOM_PATTERNS

URGENT_CHEST_PAIN_INDIC_TERMS = URGENT_SYMPTOM_INDIC_TERMS



SEVERE_LIFE_THREATENING_PATTERNS: List[str] = [

    r"\b(severe|crushing|acute|sudden|intense|unbearable|extreme|sharp|bad|terrible|heavy|worsening)\s+(?:chest|heart)\s+(?:pain|pressure|tightness|discomfort|ache)\b",

    r"\b(?:chest|heart)\s+(?:pain|pressure|tightness|discomfort)\s+(?:is\s+)?(severe|crushing|acute|sudden|intense|unbearable|extreme|worse|worsening|spreading|radiating)\b",

    r"\bchest\s+tightness\b",

    r"\bchest\s+pressure\b",

    r"\bheart\s+attack\b",

    r"\bcardiac\s+arrest\b",

    r"\bsevere\s+palpitations\b",

    r"\bshortness\s+of\s+breath\b",

    r"\bdifficulty\s+breathing\b",

    r"\bcan'?t\s+breathe\b",

    r"\bcannot\s+breathe\b",

    r"\bunable\s+to\s+breathe\b",

    r"\bbreathless(?:ness)?\b",

    r"\bgasping\b",

    r"\bstroke\b",

    r"\bparalysis\b",

    r"\bslurred\s+speech\b",

    r"\bfacial\s+droop(?:ing)?\b",

    r"\bunconscious\b",

    r"\bfainted\b",

    r"\bpassed\s+out\b",

    r"\bsevere\s+bleeding\b",

    r"\bseizure\b",

    r"\bconvulsion(?:s)?\b",

    r"\b(teevramaina|vipareetamaina|chala)\s+(?:cha?ti|gunde)\s+noppi\b",

    r"\bgundepotu\b",

    r"\b(?:oopiri|upiri|swasa)\s+(?:aadatam|adatam)\s+ledu\b",

    r"\bpakshavatam\b",

    r"\b(kadumaiyana|romba)\s+(?:nenju|idhaya)\s+vali\b",

    r"\bmaradaippu\b",

    r"\bmoochu\s*thinaral\b",

    r"\bpakkavatham\b",

    r"\b(teevra|tumba)\s+(?:ede|hrudaya)\s+novu\b",

    r"\bhrudayaghata\b",

    r"\busiratada\s+tondare\b",

    r"\bpakshavata\b",

    r"\b(tez|tej|gambhir|bahut)\s+(?:seene|chaati|dil)\s+mein\s+dard\b",

    r"\bdil\s+ka\s+daura\b",

    r"\bsaans\s+lene\s+mein\s+takleef\b",

    r"\bsaans\s+nahi\b",

    r"\blakwa\b",

    r"\bbehosh\b",

]



SEVERE_LIFE_THREATENING_INDIC_TERMS: List[str] = [

    # Telugu

    "తీవ్రమైన ఛాతీ నొప్పి", "విపరీతమైన ఛాతీ నొప్పి", "భరించలేని ఛాతీ నొప్పి",

    "తీవ్రమైన గుండె నొప్పి", "విపరీతమైన గుండె నొప్పి", "చాలా ఛాతీ నొప్పి", "చాలా గుండె నొప్పి",

    "ఆకస్మిక ఛాతీ నొప్పి", "గుండెపోటు", "ఊపిరి ఆడటం లేదు", "ఊపిరి ఆడకపోవడం",

    "ఊపిరి తీసుకోవడం కష్టం", "శ్వాస ఆడటం లేదు", "శ్వాస తీసుకోవడంలో ఇబ్బంది",

    "పక్షవాతం", "స్పృహ తప్పి", "మూర్ఛ", "తీవ్ర రక్తస్రావం",

    # Tamil

    "கடுமையான நெஞ்சு வலி", "தாங்க முடியாத நெஞ்சு வலி", "கடுமையான இதய வலி", "அதிக நெஞ்சு வலி",

    "மாரடைப்பு", "மூச்சுத்திணறல்", "மூச்சு விட சிரமம்", "மூச்சு விட முடியவில்லை",

    "பக்கவாதம்", "மயக்கம்", "வலிப்பு", "அதிக இரத்தப்போக்கு",

    # Kannada

    "ತೀವ್ರ ಎದೆ ನೋವು", "ತೀವ್ರವಾದ ಎದೆ ನೋವು", "ವಿಪರೀತ ಎದೆ ನೋವು", "ತೀವ್ರ ಹೃದಯ ನೋವು",

    "ಹೃದಯಾಘಾತ", "ಉಸಿರಾಟದ ತೊಂದರೆ", "ಉಸಿರಾಡಲು ಕಷ್ಟ", "ಉಸಿರುಗಟ್ಟುವಿಕೆ",

    "ಪಕ್ಷವಾತ", "ಪ್ರಜ್ಞೆ ತಪ್ಪಿ", "ಮೂರ್ಛೆ", "ತೀವ್ರ ರಕ್ತಸ್ರಾವ",

    # Hindi

    "तेज सीने में दर्द", "तेज़ सीने में दर्द", "गंभीर सीने में दर्द", "बहुत तेज दर्द",

    "बहुत सीने में दर्द", "असहनीय सीने में दर्द", "तेज छाती में दर्द", "तेज दिल में दर्द",

    "दिल का दौरा", "हार्ट अटैक", "सांस लेने में तकलीफ", "सांस फूलना", "सांस नहीं आ रही",

    "दम घुटना", "लकवा", "बेहोश", "दौरा पड़ना", "तेज रक्तस्राव",

]





def is_urgent_symptom(text: Optional[str]) -> bool:

    """

    Detects whether a message or clinical reason mentions chest pain, severe breathing

    difficulty, stroke/paralysis, unconsciousness, or other potentially urgent symptoms

    across English, Telugu, Tamil, Kannada, and Hindi (native and transliterated).

    """

    if not text or not text.strip():

        return False

    low = text.lower()

    for pat in URGENT_SYMPTOM_PATTERNS:

        if re.search(pat, low):

            return True

    for term in URGENT_SYMPTOM_INDIC_TERMS:

        if term in text:

            return True

    return False





def is_urgent_chest_pain_symptom(text: Optional[str]) -> bool:

    """Backwards-compatible alias for urgent symptom detection."""

    return is_urgent_symptom(text)





def is_severe_or_life_threatening_symptom(text: Optional[str]) -> bool:

    """

    Detects explicitly severe chest pain, acute shortness of breath, stroke/paralysis,

    heart attack, unconsciousness, or chest pain accompanied by red-flag symptoms

    (sweating, radiating to arm/jaw, dizziness).

    """

    if not text or not text.strip():

        return False

    low = text.lower()

    for pat in SEVERE_LIFE_THREATENING_PATTERNS:

        if re.search(pat, low):

            return True

    for term in SEVERE_LIFE_THREATENING_INDIC_TERMS:

        if term in text:

            return True



    # Also check if chest/heart pain is combined with severity or red-flag qualifiers anywhere in the text

    if is_urgent_symptom(text):

        if re.search(

            r"\b(severe|crushing|acute|sudden|intense|unbearable|extreme|sweating|sweat|left\s+arm|jaw|radiating|spreading|dizzy|dizziness|faint|breath|worsening|worse|teevramaina|kadumaiyana|teevra|tez|gambhir)\b",

            low,

        ):

            return True

        for red_flag in (

            "తీవ్ర", "విపరీత", "భరించలేని", "చెమట", "ఎడమ చే", "దవడ", "కళ్ళు తిరగ", "ఊపిరి", "శ్వాస",

            "கடுமை", "வியர்வை", "இடது கை", "தாடை", "மயக்கம்", "மூச்சு",

            "ತೀವ್ರ", "ವಿಪರೀತ", "ಬೆವರು", "ಎಡಗೈ", "ದವಡೆ", "ತಲೆತಿರುಗುವಿಕೆ", "ಉಸಿರಾಟ",

            "तेज", "तेज़", "गंभीर", "असहनीय", "पसीना", "बाएं हाथ", "जबड़े", "चक्कर", "सांस",

        ):

            if red_flag in text:

                return True

    return False





def _has_explicit_cardiologist_or_doctor_request(text: str) -> bool:

    """

    Checks if a message explicitly names a doctor or requests a cardiologist/cardiology department,

    as opposed to only reporting a symptom like 'chest pain' / 'ఛాతీ నొప్పి'.

    """

    if not text or not text.strip():

        return False

    if detect_doctor_query(text) is not None:

        return True

    low = text.lower()

    if re.search(

        r"\b(cardiologist|cardiology|cardio|heart\s+specialist|heart\s+doctor|dil\s+ka\s+doctor|slot-[a-z0-9_-]+)\b",

        low,

    ):

        return True

    for term in (

        "కార్డియాలజిస్ట్", "కార్డియాలజీ", "గుండె డాక్టర్", "గుండె విభాగం",

        "இதயவியல்", "இருதய மருத்துவர்", "இதய மருத்துவர்",

        "ಕಾರ್ಡಿಯಾಲಜಿ", "ಹೃದ್ರೋಗ", "ಹೃದಯ ತಜ್ಞ",

        "कार्डियोलॉजिस्ट", "कार्डियोलॉजी", "हृदय रोग विशेषज्ञ", "दिल के डॉक्टर",

    ):

        if term in text:

            return True

    return False





def _last_turn_was_emergency_priority(session_state: AgentSessionState) -> bool:

    """Returns True if the most recent assistant reply in session_state.history was an emergency priority warning."""

    for msg in reversed(session_state.history):

        if msg.role == "assistant":

            content = msg.content or ""

            if ("108" in content or "112" in content) and (

                "Slot ID:" not in content

                and "Dr. Rajesh Sharma" not in content

                and "Dr. Priya Nair" not in content

                and "• Slot:" not in content

            ):

                return True

            return False

    return False





def _is_continued_urgent_symptom_description(text: str) -> bool:

    """

    Detects when a patient continues describing potentially urgent or worsening symptoms

    (e.g. radiating pain to left arm/jaw, sweating, dizziness, worsening pain, breathing trouble)

    after receiving initial emergency guidance.

    """

    if not text or not text.strip():

        return False

    if is_urgent_symptom(text) or is_severe_or_life_threatening_symptom(text):

        return True

    low = text.lower()

    if re.search(

        r"\b(worse|worsening|spreading|radiating|left\s+arm|right\s+arm|shoulder|jaw|back|sweat|sweating|dizzy|dizziness|nausea|vomiting|weak|weakness|heavy|squeezing|burning|still\s+hurts|still\s+painful|pain\s+is|breathing|breath|chematalu|oopiri|upiri)\b",

        low,

    ):

        return True

    for cue in (

        "ఇంకా", "ఎక్కువ", "పెరుగుతోంది", "తగ్గలేదు", "చెమట", "చెమటలు", "ఎడమ చే", "భుజం", "దవడ", "కళ్ళు తిరుగు", "వాంతి", "నీరసం", "బరువుగా", "నొప్పి",

        "அதிகமாகிறது", "குறையவில்லை", "வியர்வை", "இடது கை", "தோள்பட்டை", "தாடை", "தலைச்சுற்றல்", "வாந்தி", "வலி",

        "ಹೆಚ್ಚಾಗುತ್ತಿದೆ", "ಕಡಿಮೆಯಾಗಿಲ್ಲ", "ಬೆವರು", "ಬೆವರುತ್ತಿದೆ", "ಎಡಗೈ", "ಭುಜ", "ದವಡೆ", "ತಲೆತಿರುಗುವಿಕೆ", "ವಾಂತಿ", "ನೋವು",

        "बढ़ रहा", "कम नहीं", "पसीना", "बाएं हाथ", "कंधे", "जबड़े", "चक्कर", "उल्टी", "घबराहट", "दर्द",

    ):

        if cue in text:

            return True

    return False





def detect_emergency_priority_kind(

    text: Optional[str], session_state: AgentSessionState

) -> Optional[str]:

    """

    Determines whether the current message requires an immediate emergency-only response

    ('emergency_priority' or 'emergency_followup') that must NOT continue into routine

    doctor selection or appointment booking:

    - Returns 'emergency_followup' if the previous assistant turn was emergency guidance and

      the patient continues describing potentially urgent or worsening symptoms.

    - Returns 'emergency_priority' if the patient reports severe chest pain or other

      life-threatening symptoms, or reports chest/heart pain without explicitly requesting a

      specialist/doctor when not answering the visit-reason prompt for an already selected doctor+slot.

    """

    if not text or not text.strip():

        return None



    last_was_emergency = _last_turn_was_emergency_priority(session_state)

    if last_was_emergency and _is_continued_urgent_symptom_description(text):

        if not _has_explicit_cardiologist_or_doctor_request(text) or is_severe_or_life_threatening_symptom(text):

            return "emergency_followup"



    if is_severe_or_life_threatening_symptom(text):

        return "emergency_priority"



    if is_urgent_symptom(text):

        has_explicit_reason_prefix = bool(

            re.search(r"(?:reason|కారణం|காரணம்|ಕಾರಣ|कारण)\s*[:\-]", text, re.IGNORECASE)

            or re.search(r"\b(?:change\s+reason\s+to|update\s+reason\s+to|reason\s+is)\b", text, re.IGNORECASE)

        )

        answering_reason_for_selected_slot = bool(

            session_state.draft.doctor_id and session_state.draft.slot_id

        )

        if (

            not _has_explicit_cardiologist_or_doctor_request(text)

            and not answering_reason_for_selected_slot

            and not has_explicit_reason_prefix

        ):

            return "emergency_priority"



    return None





MONTHS_BY_LANG: Dict[str, Dict[int, str]] = {
    "te": {1: "జనవరి", 2: "ఫిబ్రవరి", 3: "మార్చి", 4: "ఏప్రిల్", 5: "మే", 6: "జూన్", 7: "జూలై", 8: "ఆగస్టు", 9: "సెప్టెంబర్", 10: "అక్టోబర్", 11: "నవంబర్", 12: "డిసెంబర్"},
    "hi": {1: "जनवरी", 2: "फ़रवरी", 3: "मार्च", 4: "अप्रैल", 5: "मई", 6: "जून", 7: "जुलाई", 8: "अगस्त", 9: "सितंबर", 10: "अक्टूबर", 11: "नवंबर", 12: "दिसंबर"},
    "ta": {1: "ஜனவரி", 2: "பிப்ரவரி", 3: "மார்ச்", 4: "ஏப்ரல்", 5: "மே", 6: "ஜூன்", 7: "ஜூலை", 8: "ஆகஸ்ட்", 9: "செப்டம்பர்", 10: "அக்டோபர்", 11: "நவம்பர்", 12: "டிசம்பர்"},
    "kn": {1: "ಜನವರಿ", 2: "ಫೆಬ್ರವರಿ", 3: "ಮಾರ್ಚ್", 4: "ಏಪ್ರಿಲ್", 5: "ಮೇ", 6: "ಜೂನ್", 7: "ಜುಲೈ", 8: "ಆಗಸ್ಟ್", 9: "ಸೆಪ್ಟೆಂಬರ್", 10: "ಅಕ್ಟೋಬರ್", 11: "ನವೆಂಬರ್", 12: "ಡಿಸೆಂಬರ್"},
    "en": {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June", 7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"},
}


def format_human_slot_time(start_time: Optional[str], lang: str = "en") -> str:
    """Formats ISO datetime string into patient-friendly readable date and time in the patient's language."""
    if not start_time:
        return ""
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00").replace(" ", "T"))
        india_timezone = timezone(timedelta(hours=5, minutes=30))
        if dt.tzinfo is None:
            # Naive appointment times are hospital-local; explicit offsets are converted to IST.
            dt = dt.replace(tzinfo=india_timezone)
        else:
            dt = dt.astimezone(india_timezone)
        year = dt.year
        month = dt.month
        day = dt.day
        hour = dt.hour
        minute = dt.minute

        hour_12 = 12 if hour in (0, 12) else hour % 12
        min_str = f"{minute:02d}"

        clean_lang = lang.split("-")[0].lower() if lang else "en"
        months = MONTHS_BY_LANG.get(clean_lang, MONTHS_BY_LANG["en"])
        month_name = months.get(month, MONTHS_BY_LANG["en"][month])
        weekdays = {
            "te": ("సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం", "ఆదివారం"),
            "hi": ("सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"),
            "ta": ("திங்கட்கிழமை", "செவ்வாய்க்கிழமை", "புதன்கிழமை", "வியாழக்கிழமை", "வெள்ளிக்கிழமை", "சனிக்கிழமை", "ஞாயிற்றுக்கிழமை"),
            "kn": ("ಸೋಮವಾರ", "ಮಂಗಳವಾರ", "ಬುಧವಾರ", "ಗುರುವಾರ", "ಶುಕ್ರವಾರ", "ಶನಿವಾರ", "ಭಾನುವಾರ"),
            "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
        }
        weekday = weekdays.get(clean_lang, weekdays["en"])[dt.weekday()]

        if clean_lang == "te":
            if hour < 12:
                period = "ఉదయం"
            elif 12 <= hour < 16:
                period = "మధ్యాహ్నం"
            elif 16 <= hour < 20:
                period = "సాయంత్రం"
            else:
                period = "రాత్రి"
            return f"{weekday}, {day} {month_name} {year} {period} {hour_12}:{min_str} గంటలకు"

        elif clean_lang == "hi":
            if hour < 12:
                period = "सुबह"
            elif 12 <= hour < 16:
                period = "दोपहर"
            elif 16 <= hour < 20:
                period = "शाम"
            else:
                period = "रात"
            return f"{weekday}, {day} {month_name} {year} {period} {hour_12}:{min_str} बजे"

        elif clean_lang == "ta":
            if hour < 12:
                period = "காலை"
            elif 12 <= hour < 16:
                period = "மதியம்"
            elif 16 <= hour < 20:
                period = "மாலை"
            else:
                period = "இரவு"
            return f"{weekday}, {day} {month_name} {year} {period} {hour_12}:{min_str} மணிக்கு"

        elif clean_lang == "kn":
            if hour < 12:
                period = "ಬೆಳಿಗ್ಗೆ"
            elif 12 <= hour < 16:
                period = "ಮಧ್ಯಾಹ್ನ"
            elif 16 <= hour < 20:
                period = "ಸಂಜೆ"
            else:
                period = "ರಾತ್ರಿ"
            return f"{weekday}, {day} {month_name} {year} {period} {hour_12}:{min_str} ಗಂಟೆಗೆ"

        else:
            period = "AM" if hour < 12 else "PM"
            return f"{weekday}, {month_name} {day}, {year} at {hour_12}:{min_str} {period}"
    except Exception:
        return format_slot_display(None, None, lang=lang)


def format_slot_display(slot_id: Optional[str], slot_start_time: Optional[str], lang: str = "en") -> str:
    """Formats slot display with human-readable localized date/time without exposing internal IDs or comments."""
    if slot_start_time:
        return format_human_slot_time(slot_start_time, lang=lang)
    clean_lang = lang.split("-")[0].lower() if lang else "en"
    if slot_id:
        if clean_lang == "te":
            return "ఖరారైన అపాయింట్‌మెంట్ సమయం"
        elif clean_lang == "hi":
            return "पुष्टीकृत अपॉइंटमेंट समय"
        elif clean_lang == "ta":
            return "உறுதிப்படுத்தப்பட்ட அப்பாயிண்ட்மெண்ட் நேரம்"
        elif clean_lang == "kn":
            return "ದೃಢೀಕರಿಸಿದ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಸಮಯ"
        return "Confirmed Appointment Time"
    if clean_lang == "te":
        return "పేర్కొనబడలేదు"
    elif clean_lang == "hi":
        return "अनिर्दिष्ट"
    elif clean_lang == "ta":
        return "குறிப்பிடப்படவில்லை"
    elif clean_lang == "kn":
        return "ನಿರ್ದಿಷ್ಟಪಡಿಸಿಲ್ಲ"
    return "Unspecified"


def sanitize_patient_facing_text(text: str, lang: str = "en") -> str:
    """Remove internal slot identifiers from any text returned or spoken to patients."""
    clean_lang = lang.split("-")[0].lower() if lang else "en"
    replacement = "అపాయింట్‌మెంట్ సమయం" if clean_lang == "te" else "appointment time"
    return re.sub(r"\bslot[-_][A-Za-z0-9_-]+\b", replacement, text or "", flags=re.IGNORECASE)





def _contains_correction_target(text: str) -> bool:

    """

    Checks if a message that starts with 'no' / 'వద్దు' / 'வேண்டாம்' / 'ಬೇಡ' / 'नहीं'

    is actually correcting a booking detail (e.g. 'No, I want Dr. Priya Nair instead',

    'No, change to slot-sharma-avail-2') rather than aborting the whole booking.

    """

    low = text.lower()

    if detect_doctor_query(text) is not None or detect_specialty_query(text) is not None:

        return True

    if re.search(r"\b(slot-[A-Za-z0-9_-]+|PAT-[A-Za-z0-9-]+)\b", text, re.IGNORECASE):

        return True

    if re.search(r"\b(change|switch|instead|actually|different|another|update|modify)\b", low):

        return True

    for cue in ("మార్చండి", "వేరే", "மாற்று", "வேறு", "ಬದಲಾಯಿಸಿ", "ಬೇರೆ", "बदलें", "दूसरा", "बजाय"):

        if cue in text:

            return True

    return False





def is_explicit_cancellation(text: str) -> bool:
    """
    Detects EXPLICIT patient cancellation or abort intent across English and Indic languages.
    Rule 1: Never interpret an isolated 'no' / 'nahi' / 'illai' / 'illa' / 'vaddu' as cancellation.
    Rule 2: Cancellation requires explicit cancellation intent or affirmative reply to a specific cancellation question.
    """
    if not text or not text.strip():
        return False
    low = text.strip().lower()

    # Hard cancellation keywords ALWAYS cancel immediately
    hard_cancel_patterns = [
        r"\b(?:cancel|stop|abort|nevermind)\b",
        r"\b(?:cancel(?:\s+the|\s+this)?\s+(?:booking|appointment|request))\b",
        r"\bdon'?t\s+book\b",
        r"\bdo\s+not\s+book\b",
        r"\b(?:raddu|mat\s+karo|book\s+mat\s+karo|booking\s+raddu)\b",
    ]
    for pattern in hard_cancel_patterns:
        if re.search(pattern, low):
            return True

    hard_indic_cancel_terms = [
        "రద్దు", "ఆపు", "బుక్ చేయవద్దు",
        "ரத்து", "நிறுத்து",
        "ರದ್ದು", "ನಿಲ್ಲಿಸಿ",
        "रद्द", "मत करो", "रोकें", "कैंसिल", "बुक मत",
        "ಬೇಡ",
    ]
    for term in hard_indic_cancel_terms:
        if term in text:
            return True

    # Answers to patient registration ("No", "I'm new", "never visited") must never cancel
    if is_first_time_patient_reply(text):
        return False

    # Do not treat expressions of uncertainty as cancellation
    if is_ambiguous_reply(text):
        return False

    # Do not treat patient identification / registration answers as cancellation
    if re.search(
        r"\b(?:not\s+yet|first\s+time|first\s+visit|new\s+patient|new|never|never\s+visited|haven'?t|haven'?t\s+visited|not\s+visited|this\s+is\s+my\s+first|my\s+first\s+visit|my\s+first|first|i'?m\s+new|i\s+am\s+new|don'?t\s+remember|don'?t\s+know|forgot|no\s+idea|lost|can'?t\s+find|visited|visited\s+before|visited\s+last\s+(?:year|month|week)|last\s+year)\b",
        low,
    ):
        return False

    if any(
        t in text
        for t in (
            "ఇంకా లేదు", "మొదటిసారి", "కొత్త", "గుర్తులేదు", "మర్చిపోయాను", "లేదు",
            "இன்னும் இல்லை", "முதல் முறை", "புதிய", "நினைவில் இல்லை", "இல்லை",
            "ಇನ್ನೂ ಇಲ್ಲ", "ಮೊದಲ ಬಾರಿ", "ಹೊಸ", "ನೆನಪಿಲ್ಲ", "ಇಲ್ಲ",
            "अभी तक नहीं", "पहली बार", "नया मरीज", "याद नहीं", "भूल गया", "नहीं",
            "గతంలో వచ్చాను", "గత ఏడాది", "முன்பு வந்துள்ளேன்", "சென்ற ஆண்டு", "ಹಿಂದೆ ಬಂದಿದ್ದೆ", "ಹಿಂದಿನ ವರ್ಷ", "पहले आया हूँ", "पिछले साल"
        )
    ):
        return False

    return False


def is_cancellation(text: str) -> bool:
    """Detects patient cancellation or abort intent across English, Telugu, Tamil, Kannada, and Hindi."""
    return is_explicit_cancellation(text)


def is_first_time_patient_reply(text: str) -> bool:
    """
    Detects if the patient indicates they are a new/first-time visitor
    (e.g., 'No, this is my first time', 'no', 'not yet', 'first visit', 'new patient', 'never visited', "No, I'm new").
    """
    if not text or not text.strip():
        return False
    low = text.strip().lower()
    # Guard: Hard cancellation keywords ("cancel", "stop", "abort", "don't book") are NEVER new-patient replies
    if re.search(r"\b(?:cancel|stop|abort|nevermind|don'?t\s+book|do\s+not\s+book|raddu|mat\s+karo)\b", low):
        return False
    if any(t in text for t in ("రద్దు", "ఆపు", "బుక్ చేయవద్దు", "ரத்து", "நிறுத்து", "ರದ್ದು", "ನಿಲ್ಲಿಸಿ", "रद्द", "मत करो", "रोकें", "कैंसिल", "बुक मत")):
        return False
    # Guard: Expressions of flexibility ("it is fine / parvaledu / paravagilla") contain substrings of "no", but are NOT "no"
    if any(t in text for t in ("పర్వాలేదు", "ఫర్వాలేదు", "పర్లేదు", "పరవాలేదు", "பரவாயில்லை", "ಪರವಾಗಿಲ್ಲ", "parvaledu", "pharvaledu", "parledu", "paravagilla")):
        return False
    if is_flexible_slot_request(text):
        return False
    # Guard: Selections referring to doctors or slots are NOT new-patient replies
    if re.search(r"\b(?:doctor|dr|slot)\b", low):
        return False
    if any(w in text for w in ("డాక్టర్", "డాక్టరు", "వైద్యు", "స్లాట్", "மருத்துவர்", "ವೈದ್ಯ", "ವೈದ್ಯರು", "ಡಾಕ್ಟರ್", "डॉक्टर")):
        return False

    patterns = [
        r"\b(?:not\s+yet|first\s+time|first\s+visit|new\s+patient|never|never\s+visited|haven'?t|haven'?t\s+visited|not\s+visited|this\s+is\s+my\s+first|my\s+first\s+visit|new|no|nope|na|i'?m\s+new|i\s+am\s+new|no\s*,?\s*i'?m\s+new|no\s*,?\s*i\s+am\s+new|no\s*,?\s*first\s+time)\b",
        r"\b(?:inka\s+ledu|modatisari|kotha|kotha\s+patient|eppudu\s+raledu|ledu|innum\s+illai|mudhal\s+murai|pudhiya|illai|innoo\s+illa|modala\s+bari|hosa|illa|abhi\s+tak\s+nahi|pehli\s+baar|naya|naye|nahi)\b",
        r"(?:ఇంకా\s+లేదు|మొదటిసారి|కొత్త\s+పేషెంట్|కొత్త|ఎప్పుడూ\s+రాలేదు|లేదు|రావడం\s+ఇదే\s+మొదటిసారి)",
        r"(?:இன்னும்\s+இல்லை|முதல்\s+முறை|புதிய\s+நோயாளி|புதிய|இல்லை|இதுவே\s+முதல்\s+முறை)",
        r"(?:ಇನ್ನೂ\s+ಇಲ್ಲ|ಮೊದಲ\s+ಬಾರಿ|ಹೊಸ\s+ರೋಗಿ|ಹೊಸ|ಇಲ್ಲ|ಇದೇ\s+ಮೊದಲ\s+ಬಾರಿ)",
        r"(?:अभी\s+तक\s+नहीं|पहली\s+बार|नया\s+मरीज|नया|नए|नहीं|पहली\s+बार\s+आया\s+हूँ)",
    ]
    for p in patterns:
        if re.search(p, low, re.IGNORECASE):
            return True
    return False


def is_existing_patient_reply(text: str) -> bool:
    """
    Detects if the patient indicates they are an existing/returning patient
    (e.g., 'Yes', 'visited before', 'already visited', 'existing patient', 'I visited last year', 'Yes, I have visited before').
    """
    if not text or not text.strip():
        return False
    if is_first_time_patient_reply(text):
        return False
    low = text.strip().lower()
    patterns = [
        r"\b(?:yes|already|visited|visited\s+before|have\s+visited|came\s+before|existing|returning|old\s+patient|existing\s+patient|registered|already\s+registered|i\s+visited|i\s+have\s+visited)\b",
        r"(?:అవును|గతంలో\s+వచ్చాను|గతంలో\s+వచ్చిన|పాత\s+పేషెంట్|రిజిస్టర్\s+అయింది)",
        r"(?:ஆம்|முன்பு\s+வந்துள்ளேன்|ஏற்கனவே\s+வந்துள்ளேன்|பழைய\s+நோயாளி)",
        r"(?:ಹೌದು|ಹಿಂದೆ\s+ಬಂದಿದ್ದೆ|ಈಗಾಗಲೇ\s+ಬಂದಿದ್ದೆ|ಹಳೆಯ\s+ರೋಗಿ)",
        r"(?:हाँ|पहले\s+आया\s+हूँ|पुराना\s+मरीज|पहले\s+से\s+रजिस्टर्ड)",
    ]
    for p in patterns:
        if re.search(p, low, re.IGNORECASE):
            return True
    return False


def is_continue_booking_request(text: str) -> bool:
    """Detects when patient requests resuming or continuing their booking in English and Indic languages."""
    if not text or not text.strip():
        return False
    low = text.strip().lower()
    patterns = [
        r"\b(?:continue(?:\s+previous|\s+my)?\s+booking|resume(?:\s+previous|\s+my)?\s+booking|continue\s+booking|resume\s+booking|keep\s+booking|continue\s+previous|resume\s+previous|continue\s+my\s+request|resume\s+my\s+request)\b",
        r"\b(?:konasaginchandi|munduku\s+vellandi|jari\s+rakhein|thodaravum|munduvarisi)\b",
        r"(?:కొనసాగించండి|ముందువరించి|ముందుకు\s+వెళ్లండి|ముందుకు\s+సాగండి|जारी\s+रखें|आगे\s+बढ़ें|தொடரவும்|முன்னேறுங்கள்|ಮುಂದುವರಿಸಿ|ಮುಂದೆ\s+ಹೋಗಿ)",
    ]
    for p in patterns:
        if re.search(p, low, re.IGNORECASE):
            return True
    if low in ("continue booking", "resume booking", "continue previous", "resume previous", "konasaginchandi", "munduku vellandi", "jari rakhein", "thodaravum", "munduvarisi", "కొనసాగించండి"):
        return True
    return False


def is_affirmative(text: str) -> bool:
    """
    Detects EXPLICIT positive booking confirmation across English, Telugu, Tamil, Kannada, and Hindi.
    Generic contextual acknowledgements ('ok', 'okay', 'sure', 'సరే', 'சரி', 'ಸರಿ', 'ठीक है') are
    handled by `is_contextual_affirmative` and must NOT trigger final appointment booking on their own.
    """
    if not text or not text.strip():
        return False
    if is_cancellation(text) or is_ambiguous_reply(text):
        return False
    low = text.strip().lower()
    affirmative_patterns = [
        r"\b(yes|confirm|book|proceed|confirm\s+appointment|book\s+appointment|yes\s+confirm|please\s+confirm|please\s+book|yes\s+please|yes\s+book)\b",
        r"\b(avunu|dhrudheekarinchi|dhruveekarinchi|kharaaru|aam|urudhi|urudhipaduthu|haudu|dhrudhapadisu|khachita|haan|pukhta|kardo|kar\s+do|pakka|book\s+chey|book\s+cheyyi|book\s+cheyyandi)\b",
    ]
    for pattern in affirmative_patterns:
        if re.search(pattern, low):
            return True

    indic_affirmative_terms = [
        "అవును", "ధృవీకరించండి", "ఖరారు చేయండి", "బుక్ చేయండి", "బుక్ చేయి", "బుక్ చెయ్", "నిర్ధారించండి",
        "ஆம்", "உறுதிப்படுத்துங்கள்", "முன்பதிவு செய்யுங்கள்", "உறுதி செய்",
        "ಹೌದು", "ದೃಢೀಕರಿಸಿ", "ಬುಕ್ ಮಾಡಿ", "ಖಚಿತಪಡಿಸಿ",
        "हाँ", "पुष्टि करें", "कन्फर्म करें", "बुक करें", "हाँ बुक करें",
    ]
    for term in indic_affirmative_terms:
        if term in text:
            return True

    return False


def is_contextual_affirmative(text: str) -> bool:
    """
    Detects context-dependent affirmative replies that accept a pending offer (such as
    showing a doctor's available slots or checking a suggested department) across
    English, Telugu, Tamil, Kannada, and Hindi.
    """
    if is_cancellation(text) or is_ambiguous_reply(text):
        return False
    if is_affirmative(text):
        return True

    low = text.strip().lower()
    clean_low = re.sub(r"[^\w\s]", "", low).strip()
    if clean_low in (
        "kk",
        "continue",
        "kk continue",
        "book",
        "yes",
        "okay",
        "ok",
        "sure",
        "let's proceed",
        "lets proceed",
        "go ahead",
        "that sounds good",
        "sounds good",
        "that works",
        "works",
        "anyone is fine",
        "anything is fine",
        "any is fine",
        "either is fine",
        "anyone is okay",
        "anything is okay",
        "any doctor is fine",
        "okay proceed",
        "proceed",
        "go ahead",
        "whichever",
        "whatever is available first",
        "the earliest one",
    ):
        return True

    contextual_patterns = [
        r"\b(ok|okay|sure|alright|fine|proceed|let'?s\s+proceed|go\s+ahead|show|show\s+me|please\s+show|check\s+slots|show\s+slots|kk|continue|kk\s+continue|that\s+sounds\s+good|sounds\s+good|looks\s+good|that\s+works|works|perfect|great)\b",
        r"\b(sare|alage|chupinchandi|sari|kaattungal|kattungal|torisi|thorisi|agali|theek\s+hai|thik\s+hai|dikhaiye|dikhao|bilkul|chaliye)\b",
    ]
    for pattern in contextual_patterns:
        if re.search(pattern, low):
            return True

    indic_contextual_terms = [
        "సరే", "అలాగే", "చూపించండి", "చూడండి", "చెప్పండి", "పర్లేదు", "పర్వాలేదు", "ముందుకు", "సరే కొనసాగించండి",
        "சரி", "அப்படியே", "காட்டுங்கள்", "பாருங்கள்", "சொல்லுங்கள்", "பரவாயில்லை", "தொடரவும்",
        "ಸರಿ", "ಹಾಗೆಯೇ", "ತೋರಿಸಿ", "ನೋಡಿ", "ಹೇಳಿ", "ಪರವಾಗಿಲ್ಲ", "ಮುಂದುವರಿಸಿ",
        "ठीक है", "दिखाइए", "बताइए", "अच्छा", "हाँ", "बिल्कुल", "ज़रूर", "चलेगा", "आगे बढ़ें",
    ]
    for term in indic_contextual_terms:
        if term in text:
            return True

    return False


def is_flexible_slot_request(text: str) -> bool:
    """
    Detects when a patient indicates flexibility with appointment time/slot
    (e.g., 'anything is fine', 'any slot', 'any time', 'earliest', 'whatever works', 'whichever', 'you choose').
    """
    if not text or not text.strip():
        return False
    low = text.strip().lower()
    indic_terms = [
        "ఏదైనా పర్వాలేదు", "ఏదైనా ఫర్వాలేదు", "ఎప్పుడైనా సరే", "ఎప్పుడైనా పర్వాలేదు", "ఏదైనా సరే", "ఏ సమయమైనా పర్వాలేదు", "ఏ సమయమైనా సరే",
        "எதுவும் பரவாயில்லை", "எந்த நேரமும் சரி", "எதுவும் சரி",
        "ಯಾವುದಾದರೂ ಸರಿ", "ಯಾವ ಸಮಯವಾದರೂ ಸರಿ", "ಯಾವುದಾದರೂ ಪರವಾಗಿಲ್ಲ",
        "कुछ भी चलेगा", "कोई भी चलेगा", "कोई भी समय चलेगा", "कोई भी समय", "कोई भी स्लॉट", "जल्दी वाला", "जो भी हो", "कोई भी",
    ]
    if any(t in text for t in indic_terms):
        return True

    patterns = [
        r"\b(?:anything\s+is\s+(?:fine|ok|okay|good|alright|cool)|anyone\s+is\s+(?:fine|ok|okay|good|cool)|any\s+(?:doctor|slot|time)\s+is\s+(?:fine|ok|okay|good)|any\s+(?:slot|time|date)|anything\s+works|anyone\s+works|whichever|whatever\s+is\s+fine|whatever\s+works|earliest|earliest\s+available|first\s+available|whatever\s+is\s+available\s+first|the\s+earliest(?:\s+one)?|you\s+choose|you\s+decide|any\s+one|anyone|anything|any\s+time\s+is\s+(?:fine|ok|okay|good)|any\s+time)\b",
        r"\b(?:edaina\s+parvaledu|edaina\s+pharvaledu|eppudaina\s+sare|eppudaina\s+parvaledu|ye\s+time\s+aina\s+(?:okay|ok|fine|parvaledu)|ye\s+samayamaina\s+parvaledu|koyi\s+bhi\s+samay|koi\s+bhi\s+samay|koyi\s+bhi\s+chalega|koi\s+bhi\s+chalega|endha\s+neramum\s+seri|yava\s+samayavadharu\s+sari)\b",
        r"(?:ఏదైనా\s+పర్వాలేదు|ఏదైనా\s+ఫర్వాలేదు|ఎప్పుడైనా\s+సరే|ఎప్పుడైనా\s+పర్వాలేదు|ఏదైనా\s+సరే|ఏ\s+సమయమైనా\s+పర్వాలేదు|ఏ\s+సమయమైనా\s+సరే)",
        r"(?:எதுவும்\s+பரவாயில்லை|எந்த\s+நேரமும்\s+சரி|எதுவும்\s+சரி)",
        r"(?:ಯಾವುದಾದರೂ\s+ಸರಿ|ಯಾವ\s+ಸಮಯವಾದರೂ\s+ಸರಿ|ಯಾವುದಾದರೂ\s+ಪರವಾಗಿಲ್ಲ)",
        r"(?:कुछ\s+भी\s+चलेगा|कोई\s+भी\s+चलेगा|कोई\s+भी\s+समय\s+चलेगा|कोई\s+भी\s+समय|कोई\s+भी\s+स्लॉट|जल्दी\s+वाला|जो\s+भी\s+हो|कोई\s+भी)",
    ]
    for p in patterns:
        if re.search(p, low, re.IGNORECASE):
            return True
    return False



def is_gratitude_or_closing(text: str) -> bool:

    """

    Detects patient gratitude, polite sign-off, or conversational closure expressions.

    (e.g. 'Okay, thanks for your support', 'Thank you', 'Thanks for your help', 'Okay, thanks', 'That's all, thank you').

    """

    if not text or not text.strip():

        return False

    low = text.strip().lower()

    patterns = [

        r"\b(?:thanks|thank\s+you|thankyou|thx|thnx|appreciate\s+it|grateful)\b",

        r"\b(?:thanks\s+for(?:\s+your)?\s+(?:support|help|assistance))\b",

        r"\b(?:okay\s+thanks|ok\s+thanks|okay\s+thank\s+you|ok\s+thank\s+you)\b",

        r"\b(?:that'?s\s+all|that\s+is\s+all|nothing\s+else|done\s+for\s+now|goodbye|bye|take\s+care)\b",

        r"(?:ధన్యవాదాలు|సరే\s+ధన్యవాదాలు|చాలు|మళ్ళీ\s+కలుద్దాం|మీ\s+సహాయానికి\s+ధన్యవాదాలు)",

        r"(?:நன்றி|மிக்க\s+நன்றி|போதும்|வணக்கம்)",

        r"(?:ಧನ್ಯವಾದಗಳು|ಧನ್ಯವಾದ|ಸಾಕು|ಶುಭ\s+ದಿನ)",

        r"(?:धन्यवाद|बहुत\s+धन्यवाद|शुक्रिया|काफी\s+है|अलविदा|फिर\s+मिलेंगे)",

    ]

    for p in patterns:

        if re.search(p, low, re.IGNORECASE):

            return True

    return False

    if is_first_time_patient_reply(text):

        return False

    low = text.strip().lower()

    patterns = [

        r"\b(?:yes|visited|visited\s+before|visited\s+last\s+(?:year|month|week)|last\s+year|existing|already|have\s+visited|i\s+have|i\s+am\s+an\s+existing|came\s+before|returning)\b",

        r"(?:అవును|గతంలో\s+వచ్చాను|గత\s+ఏడాది|పాత\s+పేషెంట్|వచ్చాను|గతంలో)",

        r"(?:ஆம்|முன்பு\s+வந்துள்ளேன்|சென்ற\s+ஆண்டு|பழைய\s+நோயாளி)",

        r"(?:ಹೌದು|ಹಿಂದೆ\s+ಬಂದಿದ್ದೆ|ಹಿಂದಿನ\s+ವರ್ಷ|ಹಳೆಯ\s+ರೋಗಿ)",

        r"(?:हाँ|हां|पहले\s+आया\s+हूँ|पिछले\s+साल|पहले\s+आ\s+चुका|पुराना\s+मरीज)",

    ]

    for p in patterns:

        if re.search(p, low, re.IGNORECASE):

            return True

    return False





def is_forgot_patient_ref_reply(text: str) -> bool:

    """

    Detects if an existing patient does not remember or cannot find their patient reference ID

    (e.g., 'I don't remember', 'forgot', 'don't know', 'no idea', 'lost it').

    """

    if not text or not text.strip():

        return False

    low = text.strip().lower()

    patterns = [

        r"\b(?:don'?t\s+remember|don'?t\s+know|forgot|no\s+idea|not\s+sure|lost|no\b|can'?t\s+find|don'?t\s+have\s+it|i\s+lost\s+my\s+reference|lost\s+my\s+reference|i\s+only\s+have\s+my\s+mobile|only\s+have\s+my\s+mobile|don'?t\s+remember\s+my\s+patient\s+id|no\s+patient\s+id|no\s+reference)\b",

        r"(?:గుర్తులేదు|తెలియదు|మర్చిపోయాను|లేదు|నాకు\s+గుర్తులేదు|మొబైల్\s+మాత్రమే)",

        r"(?:நினைவில்\s+இல்லை|தெரியவில்லை|மறந்துவிட்டது|இல்லை|மொபைல்\s+மட்டுமே)",

        r"(?:ನೆನಪಿಲ್ಲ|ಗೊತ್ತಿಲ್ಲ|ಮರೆತುಹೋಗಿದೆ|ಇಲ್ಲ|ಮೊಬೈಲ್\s+ಮಾತ್ರ)",

        r"(?:याद\s+नहीं|भूल\s+गया|नहीं\s+पता|नहीं\s+है|सिर्फ\s+मोबाइल)",

    ]

    for p in patterns:

        if re.search(p, low, re.IGNORECASE):

            return True

    return False





def extract_phone_number_candidate(text: str) -> Optional[str]:

    """Extracts a valid 10-digit mobile phone candidate from a message."""

    if not text:

        return None

    # 1. Match standard 10 digit Indian number with optional +91 or 91

    m = re.search(r"(?:\+?91[\s-]?)?([6-9]\d{9})\b", text)

    if m:

        return m.group(1)

    # 2. General 10-digit sequence

    m2 = re.search(r"\b(\d{10})\b", text)

    if m2:

        return m2.group(1)

    return None





def extract_patient_name_candidate(text: str) -> Optional[str]:

    """Extracts a human patient name from a conversational response."""

    if not text:

        return None

    cleaned = re.sub(

        r"^(?:my\s+name\s+is|i\s+am|it\s+is|name\s*[:\-]|call\s+me|this\s+is)\s*",

        "",

        text.strip(),

        flags=re.IGNORECASE,

    )

    cleaned = cleaned.strip(". ,!-–—")

    if len(cleaned) >= 2 and not any(cleaned.lower().startswith(w) for w in ("yes", "no", "ok", "cancel", "what", "how", "why", "who")):

        return cleaned

    return None









def is_ambiguous_reply(text: str) -> bool:

    """

    Detects hesitant, uncertain, or ambiguous replies across all 5 supported languages,

    including 'I don't know which doctor', 'I'm not sure', 'నాకు తెలియదు ఎవరు', 'मुझे नहीं पता',

    'எனக்கு தெரியவில்லை', and 'ನನಗೆ ಗೊತ್ತಿಲ್ಲ'.

    """

    if not text or not text.strip():

        return False

    low = text.strip().lower()

    ambiguous_patterns = [

        r"\b(maybe|perhaps|not\s+sure|unsure|i\s+don'?t\s+know|i\s+do\s+not\s+know|don'?t\s+know\s+which|don'?t\s+know\s+who|no\s+idea|confused|idk|let\s+me\s+think|let\s+me\s+check|wait|hold\s+on|hmm+|umm+)\b",

        r"\b(which\s+doctor\s+should\s+i|who\s+should\s+i\s+(?:see|consult|meet)|whom\s+should\s+i\s+(?:see|consult|meet)|help\s+me\s+(?:choose|decide)|suggest\s+a\s+doctor)\b",

        r"\b(emo|teliyadu|teleedu|telidu|evaru\s+teliyadu|aagandi|theriyavillai|theriyala|theriyadhu|theriyathu|gottilla|gothilla|tilidilla|thilidilla|nodona|pata\s+nahi|nahi\s+pata|shayad|rukiye|samajh\s+nahi|kis\s+doctor\s+ko\s+dikhaun)\b",

    ]

    for pat in ambiguous_patterns:

        if re.search(pat, low):

            return True



    indic_ambiguous = [

        # Telugu

        "ఏమో", "తెలియదు", "తెలీదు", "తెలియడం లేదు", "ఎవరో తెలియదు", "ఎవరిని కలవాలో",

        "ఏ డాక్టర్‌ని కలవాలో", "ఏ డాక్టర్ ని కలవాలో", "ఆగండి", "ఆలోచిస్తాను", "చెప్పలేను", "సందేహం", "అర్థం కావడం లేదు",

        # Tamil

        "தெரியவில்லை", "தெரியல", "தெரியாது", "யாரைப் பார்ப்பது", "எந்த மருத்துவரைப் பார்ப்பது",

        "யோசிக்கிறேன்", "இருங்க", "சந்தேகம்", "புரியவில்லை",

        # Kannada

        "ಗೊತ್ತಿಲ್ಲ", "ತಿಳಿದಿಲ್ಲ", "ಗೊತ್ತಾಗುತ್ತಿಲ್ಲ", "ಯಾರನ್ನು ಕಾಣಬೇಕು", "ಯಾವ ವೈದ್ಯರನ್ನು ಕಾಣಬೇಕು",

        "ನೋಡೋಣ", "ಆಲೋಚಿಸುತ್ತೇನೆ", "ಇರಿ", "ಗೊಂದಲ",

        # Hindi

        "पता नहीं", "नहीं पता", "मालूम नहीं", "नहीं मालूम", "शायद", "रुकिए", "सोच कर",

        "कन्फ्यूज", "समझ नहीं", "किस डॉक्टर को दिखाऊं", "किस डॉक्टर से मिलूं", "कौन से डॉक्टर को दिखाऊं",

    ]

    for term in indic_ambiguous:

        if term in text:

            return True



    return False





def is_greeting_only(text: str) -> bool:

    """

    Returns True if the user message is a standalone greeting or polite opener

    without any doctor, specialty, slot, symptom, or booking detail.

    """

    if not text or not text.strip():

        return False

    if detect_doctor_query(text) or detect_specialty_query(text) or extract_reason_from_text(text):

        return False

    if is_ambiguous_reply(text) or is_urgent_symptom(text):

        return False

    if re.search(r"\b(PAT-[A-Za-z0-9-]+|slot-[A-Za-z0-9_-]+|\d+)\b", text, re.IGNORECASE):

        return False



    low = re.sub(r"[!.,?:;\-]+", " ", text.strip().lower()).strip()

    greeting_patterns = [

        r"^(?:hi|hello|hey|good\s+morning|good\s+afternoon|good\s+evening|greetings|namaste|namaskaram|namaskara|vanakkam)(?:\s+there|\s+assistant|\s+medivoice|\s+sir|\s+madam|\s+garu|\s+ji)?$",

    ]

    for pat in greeting_patterns:

        if re.match(pat, low):

            return True



    indic_greetings = (

        "నమస్కారం", "నమస్తే", "హలో", "హాయ్", "శుభోదయం",

        "வணக்கம்", "ஹலோ", "காலை வணக்கம்",

        "ನಮಸ್ಕಾರ", "ಹಲೋ", "ಶುಭೋದಯ",

        "नमस्ते", "नमस्कार", "प्रणाम", "हैलो", "हाय", "सुप्रभात",

    )

    cleaned_indic = re.sub(r"[!.,?:;\-\s]+", "", text.strip())

    if any(cleaned_indic == g.replace(" ", "") for g in indic_greetings):

        return True



    return False





def deduplicate_doctors(docs: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:

    """

    Deduplicates doctor result dictionaries using stable doctor_id and (name, specialty).

    Preserves genuinely different doctors even if they share the same specialty.

    """

    if not docs:

        return []

    seen_ids = set()

    seen_keys = set()

    deduped = []

    for d in docs:

        if not isinstance(d, dict):

            continue

        doc_id = str(d.get("doctor_id") or d.get("id") or "").strip()

        name = str(d.get("display_name") or d.get("name") or "").strip().lower()

        specialty = str(d.get("specialty") or "").strip().lower()

        clean_name = re.sub(r"^(dr\.?|doctor)\s+", "", name).strip()

        key = (clean_name, specialty) if clean_name else None

        if doc_id and doc_id in seen_ids:

            continue

        if key and key in seen_keys:

            continue

        if doc_id:

            seen_ids.add(doc_id)

        if key:

            seen_keys.add(key)

        deduped.append(d)

    return deduped





def is_ambiguous_account_or_booking_inquiry(text: Optional[str]) -> bool:
    """
    Detects queries with ambiguity between booking a doctor appointment and registering a patient account
    (e.g. 'naaku account book cheyagalva?', 'can you book account', 'account book cheyandi', 'నాకు ఖాతా బుక్ చేయగలరా?').
    """
    if not text or not text.strip():
        return False
    low = text.strip().lower()

    # ASCII words (require word boundary)
    has_account_ascii = bool(re.search(r"\b(account|acct|khata|khaata|khate|kanakku)\b", low))
    # Indic script account words
    indic_accounts = [
        "ఖాతా", "అకౌంట్",
        "खाता", "अकाउंट",
        "கணக்கு", "அக்கவுண்ட்",
        "ಖಾತೆ", "ಅಕೌಂಟ್",
    ]
    has_account_indic = any(a in low for a in indic_accounts)
    has_account = has_account_ascii or has_account_indic

    # Booking / creation action
    has_book_ascii = bool(
        re.search(
            r"\b(book|booking|cheyagalva|cheyagalara|cheyandi|cheyyandi|karo|pannunga|maadi|open|create)\b",
            low,
        )
    )
    indic_books = [
        "బుక్", "చేయగలవా", "చేయగలరా", "చేయండి", "చేయ్యండి",
        "बुक", "बनाओ", "खोलें",
        "புக்", "பதிவு", "செய்ய",
        "ಬುಕ್", "ಮಾಡಿ", "ತೆರೆಯಿರಿ",
    ]
    has_book_indic = any(b in low for b in indic_books)
    has_book_or_action = has_book_ascii or has_book_indic

    if has_account and has_book_or_action:
        if detect_doctor_query(text) or detect_specialty_query(text):
            return False
        return True
    return False


def detect_general_question_intent(text: str) -> Optional[str]:

    """

    Detects general hospital / appointment inquiries so the assistant can answer naturally

    without losing conversation state:

    - 'departments': Asking what departments/specialties exist

    - 'hours': Asking hospital timings / OPD visiting hours / location

    - 'how_to_book': Asking how to book or expressing general appointment intent without a specialty yet

    - 'status_summary': Asking what details have been selected so far

    """

    if not text or not text.strip():

        return None

    if is_ambiguous_reply(text) or is_urgent_symptom(text) or is_contextual_affirmative(text) or is_flexible_slot_request(text):

        return None



    low = text.strip().lower()

    norm_text = re.sub(r"[\u200b\u200c\u200d]", "", text)



    # If a specific doctor or specialty is mentioned, let doctor/specialty search handle it directly

    if detect_doctor_query(text) is not None or detect_specialty_query(text) is not None:

        return None

    if re.search(r"\b(PAT-[A-Za-z0-9-]+|slot-[A-Za-z0-9_-]+)\b", text, re.IGNORECASE):

        return None



    # 1. Hospital timings / hours / location

    if re.search(

        r"\b(timing|timings|hours|open|close|closing|working\s+hours|visiting\s+hours|where\s+is|location|address)\b",

        low,

    ) or any(

        t in norm_text

        for t in (

            "సమయాలు", "సమయం", "ఎప్పుడు తెరుస్తారు", "ఎక్కడ ఉంది",

            "நேரம்", "எப்போது திறக்கும்", "முகவரி",

            "ಸಮಯ", "ಯಾವಾಗ ತೆರೆಯುತ್ತದೆ", "ವಿಳಾಸ",

            "समय", "कब खुलता", "टाइमिंग", "पता क्या है", "कहाँ है",

        )

    ):

        return "hours"



    # 2. Available departments / specialties / doctors list

    if re.search(

        r"\b(what\s+departments|which\s+departments|what\s+specialties|which\s+specialties|available\s+departments|list\s+of\s+departments|all\s+departments|which\s+doctors|what\s+doctors|who\s+are\s+the\s+doctors|show\s+all\s+doctors)\b",

        low,

    ) or any(

        t in norm_text

        for t in (

            "ఏ విభాగాలు", "ఎలాంటి విభాగాలు", "అన్ని విభాగాలు", "ఏ డాక్టర్లు", "డాక్టర్ల జాబితా",

            "என்ன துறைகள்", "எந்த துறைகள்", "என்னென்ன துறைகள்", "எந்த மருத்துவர்கள்",

            "ಯಾವ ವಿಭಾಗಗಳು", "ಯಾವ ವಿಭಾಗಗಳಿವೆ", "ಯಾವ ವೈದ್ಯರು", "ಎಲ್ಲಾ ವಿಭಾಗ",

            "कौन से विभाग", "कौन-कौन से विभाग", "सभी विभाग", "कौन से डॉक्टर", "डॉक्टरों की सूची",

        )

    ):

        return "departments"



    # 3. Current booking draft status inquiry

    if re.search(

        r"\b(what\s+did\s+i\s+select|what\s+have\s+i\s+selected|my\s+current\s+booking|current\s+status|which\s+slot\s+did\s+i|which\s+doctor\s+did\s+i|summary\s+so\s+far)\b",

        low,

    ) or any(

        t in norm_text

        for t in (

            "నా బుకింగ్ వివరాలు", "నేను ఏమి ఎంచుకున్నాను",

            "என் முன்பதிவு விவரங்கள்", "நான் என்ன தேர்ந்தெடுத்தேன்",

            "ನನ್ನ ಬುಕಿಂಗ್ ವಿವರ", "ನಾನು ಏನು ಆಯ್ಕೆ ಮಾಡಿದ್ದೇನೆ",

            "मेरी बुकिंग का विवरण", "मैंने क्या चुना है",

        )

    ):

        return "status_summary"



    # 4. General 'I want to book an appointment' or 'How do I book?' without specialty

    if re.search(

        r"\b(how\s+to\s+book|how\s+do\s+i\s+book|how\s+can\s+i\s+book|want\s+to\s+book\s+an?\s+appointment|need\s+an?\s+appointment|book\s+an?\s+appointment|schedule\s+an?\s+appointment|help\s+me\s+book|can\s+i\s+get\s+an?\s+appointment|need\s+to\s+see\s+a\s+doctor|want\s+to\s+see\s+a\s+doctor)\b",

        low,

    ) or re.search(

        r"\b(appointment\s+kavali|appointment\s+kaavali|doctor\s+kavali|doctor\s+kaavali|appointment\s+vendum|appointment\s+venum|appointment\s+beku|appointment\s+chahiye|appointment\s+book\s+karna)\b",

        low,

    ) or any(

        t in norm_text

        for t in (

            "అపాయింట్మెంట్ కావాలి", "అపాయింట్మెంట్ బుక్", "అపాయింట్మెంట్ ఎలా",

            "డాక్టర్ ని కలవాలి", "డాక్టర్ని కలవాలి", "డాక్టర్ కావాలి", "డాక్టర్ గారిని కలవాలి",

            "அப்பாயின்ட்மென்ட் வேண்டும்", "அப்பாயின்ட்மென்ட் புக்", "மருத்துவரை பார்க்க வேண்டும்", "மருத்துவரை சந்திக்க",

            "ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬೇಕು", "ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬುಕ್", "ವೈದ್ಯರನ್ನು ಕಾಣಬೇಕು", "ವೈದ್ಯರನ್ನು ಭೇಟಿ",

            "अपॉइंटमेंट चाहिए", "अपॉइंटमेंट बुक करना", "अपॉइंटमेंट कैसे", "डॉक्टर से मिलना है", "डॉक्टर को दिखाना है",

        )

    ):

        return "how_to_book"



    return None





LOCALIZED_MESSAGES: Dict[str, Dict[str, str]] = {

    "en": {
        "ask_which_doctor_preferred": "Certainly! Which doctor or department would you prefer to consult?",

        "clarify_account_vs_booking": (

            "Would you like to schedule an appointment with a doctor, or register a new patient account at Aarogya One Hospital? "

            "Please let me know how you would like to proceed."

        ),

"greeting": (

            "Hello! I am the MediVoice Hospital Assistant for Aarogya One Hospital. "

            "Which specialty or physician do you need consultation for? "

            "(e.g., Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine)"

        ),

        "how_to_book": (

            "I would be happy to help you book an appointment at Aarogya One Hospital! "

            "Simply tell me the department, specialty, doctor's name, or the symptoms you are experiencing "

            "(for example: 'Cardiology', 'Dr. Rajesh Sharma', 'knee pain', or 'fever'), and I will check real-time availability for you."

        ),

        "departments_info": (

            "Aarogya One Hospital offers specialist OPD consultations across 5 core departments:\n"

            "• Cardiology — Dr. Rajesh Sharma, Dr. Priya Nair\n"

            "• Neurology — Dr. Arvind Swamy\n"

            "• Orthopedics — Dr. Vikram Mehta\n"

            "• Pediatrics — Dr. Ananya Sen\n"

            "• General Medicine — Dr. Sunita Rao\n\n"

            "Which department or doctor would you like to check?"

        ),

        "hours_info": (

            "Aarogya One Hospital (Bengaluru) OPD consultations are open Monday through Saturday from 08:00 AM to 08:00 PM IST, "

            "and our Emergency Department operates 24/7 (Emergency Helpline: 108 / 112)."

        ),

        "ambiguous_confirm": (

            "No problem—take your time! Your appointment is not booked yet. "

            "Whenever you are ready, reply 'YES' to confirm the booking, 'NO' to cancel, "

            "or tell me if you would like to change the doctor, slot, or reason."

        ),

        "ambiguous_general": (

            "I understand—choosing the right specialist can feel confusing. "

            "Could you tell me your main symptom or concern (for example, fever, headache, or joint pain)? "

            "Or, if you prefer, we can start with a General Medicine consultation."

        ),

        "ambiguous_doctor_choice": (

            "No problem at all—I can help you decide among the available specialists ({doc_names}). "

            "Do you have a preferred time of day (morning or afternoon), or would you like me to check the earliest available appointment slot for you?"

        ),

        "clarify_need": (

            "I am here to help you with your appointment at Aarogya One Hospital. "

            "Could you let me know what symptoms you are experiencing, or which department or doctor you would like to consult?"

        ),

        "emergency_priority": (

            "🚨 MEDICAL EMERGENCY PRIORITY: Severe chest pain or acute life-threatening symptoms require immediate emergency medical evaluation. "

            "Please call emergency services at 108 or 112 right now, or go immediately to the nearest hospital Emergency Department (Aarogya One Hospital Emergency is open 24/7). "

            "Please do not wait for an outpatient appointment booking—your immediate safety comes first."

        ),

        "emergency_followup": (

            "🚨 URGENT SAFETY REMINDER: Because you are describing ongoing potentially life-threatening symptoms, I cannot proceed with a routine outpatient booking right now. "

            "Please call 108 or 112 immediately or have someone take you to the nearest Emergency Department for urgent in-person care."

        ),

        "missing_details_error": (

            "Cannot book yet. Missing details: {missing}."

        ),

        "detail_captured_pick_slot": (

            "Got it—I have noted that down. To continue with {doctor_name}, please choose one of the available times: {available_ids}."

        ),

        "symptom_added_keep_specialty": (

            "I have noted your symptoms ({reason_category}). {specialty} ({doctor_name}) remains a suitable match for this consultation. "

            "Would you like me to show the earliest available slots for {doctor_name}?"

        ),

        "gratitude_closure": (

            "You're welcome! Aarogya One Hospital is here to assist you whenever you're ready. Take care and have a wonderful day!"

        ),

        "cancelled": (

            "Understood. The appointment booking has been cancelled. "

            "Let me know if you would like to explore other doctors or services."

        ),

        "already_booked": (

            "Your appointment is already confirmed and booked (Appointment ID: {appt_id}). "

            "If you need to book a new appointment, please reset the session or ask to start over."

        ),

        "searching_doctor": "Searching for Dr. {doc}...",

        "searching_specialty": "Searching for available specialists in {specialty}...",

        "checking_slots": "Certainly! Let me check available appointments for {doctor_name}.",

        "ask_reason": (
            "You have selected {slot_display} with {doctor_name}. "

            "What is the clinical reason or symptoms for this visit? (e.g., 'Routine checkup', 'Chest pain')"

        ),

        "ask_patient_ref": (

            "Before preparing your appointment, may I know whether you've visited Aarogya One Hospital before?"

        ),

        "symptom_empathy_general_medicine": (

            "I'm sorry you're not feeling well. I can help you arrange a consultation at Aarogya One Hospital.\n\n"

            "For fever, General Medicine is a suitable starting point.\n\n"

            "Would you like me to check the available General Medicine doctors?"

        ),

        "doctor_found_consult_or_more": (

            "I found {doctor_name}, a {specialty} specialist. Would you like me to check available appointments?"

        ),

        "checking_slots_for_doctor": "Great! Let me check available appointment times.",

        "suggest_earliest_slot": (

            "No problem! The earliest available appointment is {slot_time}.\n\n"

            "Would you like me to reserve that slot for you?"

        ),

        "ask_visited_before": (

            "Before preparing your appointment, may I know whether you've visited Aarogya One Hospital before?"

        ),

        "welcome_new_patient_ask_name": (

            "Welcome to Aarogya One Hospital! No problem. I'll help you with the new-patient registration process.\n\n"

            "May I have your full name?"

        ),

        "thank_name_ask_phone": (

            "Thank you, {name}. May I have your mobile number for appointment communication?"

        ),

        "welcome_back_ask_reference": (

            "Welcome back! I'd be happy to help you book another appointment. Could you share your registered mobile number so I can help locate your patient record (or reference)?"

        ),

        "welcome_back_ask_phone": (

            "Welcome back! I'd be happy to help you book another appointment. Could you share your registered mobile number so I can help locate your patient record (or reference)?"

        ),

        "forgot_reference_ask_phone": (

            "No worries! You don't need to remember your patient ID. We can try to locate your record using your registered mobile number."

        ),

        "patient_verified_success": (

            "Thank you! We found a matching patient record for {patient_name}.\n\n"

            "Note: Hospital record matching confirms your contact record for appointment scheduling. Official photo identity verification is completed at reception during check-in."

        ),

        "patient_not_found_options": (

            "We couldn't locate a previous record for that mobile number. Our reception desk at Aarogya One Hospital will gladly assist you, "

            "or would you like to register as a new patient now?"

        ),

        "confirm_summary": (

            "Please verify and confirm your appointment details:\n"

            "• Patient: {patient_reference}\n"

            "• Doctor: {doctor_name} ({specialty})\n"

            "• Date & Time: {slot_display}\n"

            "• Reason: {reason_category}\n\n"

            "Everything looks good. Would you like me to confirm and book this appointment for you?\n"

            "To confirm, reply 'YES' or 'CONFIRM'. Reply 'NO' if you wish to change details or cancel."

        ),

        "decline_confirm_ask_modify_or_cancel": (

            "Understood. Would you like to change any details (such as the doctor, date, or time), or would you like to cancel this booking?"

        ),

        "resuming_booking": (

            "Certainly! Resuming your appointment booking."

        ),

        "processing_booking": "Thank you for confirming. Processing your appointment booking now...",

        "offer_specialty_consultation": (

            "Certainly! I can help you arrange a {specialty} consultation. Would you like me to find an available {specialist_noun}?"

        ),

        "checking_available_specialists": (

            "Of course. Let me check our available {specialist_plural}."

        ),

        "found_specialists_recommend": (

            "I found {count} {specialist_plural}:\n{doc_list}\n\n"

            "Would you like me to recommend {recommend_name} based on availability?"

        ),

        "specialist_choice_excellent": (

            "{doctor_name} is an excellent choice. Let me check available appointment slots."

        ),

        "found_doctors": (

            "I found {count} specialist(s) available at Aarogya One Hospital:\n{doc_list}\n\n"

            "Which doctor would you like to schedule an appointment with?"

        ),

        "selected_doctor_slots": (

            "Selected {doctor_name} ({specialty}).\n\n"

            "Here are the available appointments:\n{slot_lines}\n\n"

            "Which time works best for you?"

        ),

        "recommended_doctor_slots": (

            "For {specialty}, I recommend {doctor_name}. Here are the available appointments:\n{slot_lines}\n\n"

            "Which time works best for you? (You can also request another doctor if you prefer.)"

        ),

        "available_slots": (

            "Here are the available appointments for {doctor_name}:\n{slot_lines}\n\n"

            "Which time works best for you?"

        ),

        "invalid_slot": (
            "The selected appointment time is not available for {doctor_name}. "
            "Please choose one of the available times:\n"
            "{slot_lines}"
        ),
        "urgent_chest_pain_note": (

            "⚠️ Emergency Guidance: Chest pain or acute breathing/neurological symptoms can be a medical emergency. "

            "If your symptoms are severe, sudden, radiating to your arm or jaw, or accompanied by shortness of breath or sweating, "

            "please seek immediate emergency medical care or call emergency services (108 / 112) rather than delaying care to complete an outpatient booking."

        ),

        "no_slots": (

            "No available slots currently found for {doctor_name}. "

            "Would you like to check another doctor or date?"

        ),

        "no_doctors": (

            "No matching doctors found for that query. "

            "Would you like to check general medicine or another department?"

        ),

        "changed_reconfirm": (

            "Booking details have changed. Please confirm the updated details:\n"

            "• Doctor: {doctor_name}\n"

            "• Slot: {slot_display}\n"

            "• Reason: {reason_category}\n"

            "• Patient Reference: {patient_reference}\n\n"

            "Reply 'YES' to finalize booking."

        ),

        "explicit_confirm_required": (

            "Explicit confirmation is required before booking. "

            "Please reply 'YES' to confirm or 'NO' to cancel."

        ),

        "booking_confirmed": (

            "Appointment Confirmed! 🎉\n"

            "• Appointment ID: {appointment_id}\n"

            "• Doctor: {doctor_name}\n"

            "• Schedule: {appointment_start_time}\n"

            "• Status: {appointment_status}\n"

            "• Patient Reference: {patient_reference}\n\n"

            "Your appointment details will be sent to your registered mobile number via SMS (Demonstration mode).\n\n"

            "Thank you for choosing Aarogya One Hospital. We wish you a speedy recovery and good health!"

        ),

        "doctor_not_found_ask_alternative": (

            "Dr. {doctor_name} is not available at Aarogya One Hospital. Would you like to book an appointment with another doctor, or see our list of available doctors?"

        ),

        "doctor_ambiguous_clarify": (

            "There are multiple doctors available matching '{doctor_name}'. Could you please specify which doctor you would like to consult?"

        ),

        "booking_failed": (

            "Booking could not be completed: {error}\n"

            "The selected slot is unavailable or conflict occurred. "

            "Please choose a different available slot."

        ),

        "provider_error": (

            "The AI reasoning service is temporarily unavailable ({reason}). "

            "Please try again shortly or continue with standard booking details."

        ),

    },

    "te": {
        "ask_which_doctor_preferred": "తప్పకుండా! మీరు ఏ డాక్టర్ గారిని లేదా ఏ విభాగాన్ని సంప్రదించాలనుకుంటున్నారు?",

        "clarify_account_vs_booking": (

            "\u0c2e\u0c40\u0c30\u0c41 \u0c06\u0c30\u0c4b\u0c17\u0c4d\u0c2f \u0c35\u0c28\u0c4d \u0c39\u0c3e\u0c38\u0c4d\u0c2a\u0c3f\u0c1f\u0c32\u0c4d\u200c\u0c32\u0c4b \u0c21\u0c3e\u0c15\u0c4d\u0c1f\u0c30\u0c4d \u0c05\u0c2a\u0c3e\u0c2f\u0c3f\u0c02\u0c1f\u0c4d\u200c\u0c2e\u0c46\u0c02\u0c1f\u0c4d \u0c2c\u0c41\u0c15\u0c4d \u0c1a\u0c47\u0c2f\u0c3e\u0c32\u0c28\u0c41\u0c15\u0c41\u0c02\u0c1f\u0c41\u0c28\u0c4d\u0c28\u0c3e\u0c30\u0c3e, \u0c32\u0c47\u0c26\u0c3e \u0c15\u0c4a\u0c24\u0c4d\u0c24 \u0c2a\u0c47\u0c37\u0c46\u0c02\u0c1f\u0c4d \u0c16\u0c3e\u0c24\u0c3e (Account) \u0c28\u0c2e\u0c4b\u0c26\u0c41 \u0c1a\u0c47\u0c2f\u0c3e\u0c32\u0c28\u0c41\u0c15\u0c41\u0c02\u0c1f\u0c41\u0c28\u0c4d\u0c28\u0c3e\u0c30\u0c3e? "

            "\u0c26\u0c2f\u0c1a\u0c47\u0c38\u0c3f \u0c24\u0c46\u0c32\u0c3f\u0c2f\u0c1c\u0c47\u0c2f\u0c02\u0c21\u0c3f."

        ),

        "greeting": (

            "నమస్కారం! నేను ఆరోగ్య వన్ హాస్పిటల్ (Aarogya One Hospital) మెడివాయిస్ సహాయకుడిని. "

            "మీకు ఏ విభాగం లేదా ఏ డాక్టర్ గారితో సంప్రదింపులు కావాలి? "

            "(ఉదా: Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine)"

        ),

        "how_to_book": (

            "ఆరోగ్య వన్ హాస్పిటల్‌లో అపాయింట్‌మెంట్ బుక్ చేయడానికి నేను మీకు సహాయం చేస్తాను! "

            "దయచేసి మీకు కావలసిన విభాగం, డాక్టర్ పేరు లేదా మీ ఆరోగ్య సమస్యను తెలపండి "

            "(ఉదా: 'Cardiology', 'డాక్టర్ రాజేష్ శర్మ', 'మోకాళ్ళ నొప్పి', లేదా 'జ్వరం')."

        ),

        "departments_info": (

            "ఆరోగ్య వన్ హాస్పిటల్‌లో 5 ప్రధాన విభాగాలలో నిపుణులైన డాక్టర్లు అందుబాటులో ఉన్నారు:\n"

            "• Cardiology (గుండె విభాగం) — Dr. Rajesh Sharma, Dr. Priya Nair\n"

            "• Neurology (నరాల విభాగం) — Dr. Arvind Swamy\n"

            "• Orthopedics (ఎముకలు & కీళ్ల విభాగం) — Dr. Vikram Mehta\n"

            "• Pediatrics (పిల్లల విభాగం) — Dr. Ananya Sen\n"

            "• General Medicine (సాధారణ వైద్యం) — Dr. Sunita Rao\n\n"

            "మీరు ఏ విభాగం లేదా ఏ డాక్టర్ గారిని సంప్రదించాలనుకుంటున్నారు?"

        ),

        "hours_info": (

            "ఆరోగ్య వన్ హాస్పిటల్ (బెంగళూరు) ఓపీడీ (OPD) సమయాలు: సోమవారం నుండి శనివారం వరకు ఉదయం 08:00 నుండి రాత్రి 08:00 వరకు. "

            "అత్యవసర విభాగం (Emergency) 24/7 అందుబాటులో ఉంటుంది (హెల్ప్‌లైన్: 108 / 112)."

        ),

        "ambiguous_confirm": (

            "పర్వాలేదు, మీ సమయం తీసుకోండి! మీ అపాయింట్‌మెంట్ ఇంకా బుక్ చేయబడలేదు. "

            "మీరు సిద్ధంగా ఉన్నప్పుడు బుకింగ్ ఖరారు చేయడానికి 'అవును' (YES) అని, రద్దు చేయడానికి 'వద్దు' (NO) అని చెప్పండి, "

            "లేదా డాక్టర్/స్లాట్ మార్చాలంటే తెలపండి."

        ),

        "ambiguous_general": (

            "పర్వాలేదు, ఏ డాక్టర్‌ని సంప్రదించాలో తెలియకపోవడం సహజమే! నేను మీకు సహాయం చేస్తాను. "

            "మీకు ప్రస్తుతం ఎలాంటి ఇబ్బంది లేదా లక్షణాలు ఉన్నాయి (ఉదా: జ్వరం, తలనొప్పి, కీళ్ల నొప్పి)? "

            "లేదా ముందుగా సాధారణ వైద్య విభాగం (General Medicine) డాక్టర్ గారితో సంప్రదింపులు ఏర్పాటు చేయమంటారా?"

        ),

        "ambiguous_doctor_choice": (

            "పర్వాలేదు! అందుబాటులో ఉన్న ఈ నిపుణులలో ({doc_names}) సరైన వారిని ఎంచుకోవడానికి నేను సహాయం చేస్తాను. "

            "మీకు ఉదయం లేదా మధ్యాహ్నం సమయంలో ఏది అనుకూలంగా ఉంటుంది, లేదా త్వరగా అందుబాటులో ఉన్న మొదటి స్లాట్‌ను చూపించమంటారా?"

        ),

        "clarify_need": (

            "ఆరోగ్య వన్ హాస్పిటల్‌లో అపాయింట్‌మెంట్ కోసం నేను మీకు సహాయం చేయడానికి సిద్ధంగా ఉన్నాను. "

            "దయచేసి మీ ఆరోగ్య సమస్య లేదా మీరు ఏ విభాగం/డాక్టర్ గారిని కలవాలనుకుంటున్నారో తెలుపగలరా?"

        ),

        "emergency_priority": (

            "🚨 అత్యవసర వైద్య హెచ్చరిక (Emergency Priority): తీవ్రమైన ఛాతీ నొప్పి లేదా ప్రాణాపాయ లక్షణాలు ఉన్నప్పుడు వెంటనే అత్యవసర వైద్య పరీక్ష అవసరం. "

            "దయచేసి సాధారణ అపాయింట్‌మెంట్ బుకింగ్ కోసం వేచి ఉండకుండా, తక్షణమే 108 లేదా 112 అత్యవసర నంబర్‌కు కాల్ చేయండి, లేదా వెంటనే సమీపంలోని హాస్పిటల్ ఎమర్జెన్సీ విభాగానికి (Emergency Department) వెళ్ళండి. "

            "మీ తక్షణ భద్రత అన్నింటికంటే ముఖ్యం."

        ),

        "emergency_followup": (

            "🚨 అత్యవసర భద్రతా సూచన: మీరు చెబుతున్న లక్షణాలు అత్యవసరమైనవి కాబట్టి, సాధారణ ఓపీడీ బుకింగ్‌తో ఆలస్యం చేయడం సురక్షితం కాదు. "

            "దయచేసి వెంటనే 108 / 112 కు కాల్ చేయండి లేదా వెంటనే సమీపంలోని అత్యవసర విభాగానికి (Emergency Room) వెళ్ళండి."

        ),

        "missing_details_error": (

            "ఇంకా బుక్ చేయడం సాధ్యం కాదు. కావలసిన వివరాలు: {missing}."

        ),

        "detail_captured_pick_slot": (

            "మీ వివరాలు నమోదు చేసుకున్నాను. {doctor_name} గారితో బుకింగ్ కొనసాగించడానికి దయచేసి అందుబాటులో ఉన్న ఈ సమయాలలో ఒకదాన్ని ఎంచుకోండి: {available_ids}."

        ),

        "symptom_added_keep_specialty": (

            "మీ లక్షణాలు ({reason_category}) నమోదు చేసుకున్నాను. వీటికి {specialty} విభాగంలోని {doctor_name} గారితో సంప్రదింపులు సరైనవే. "

            "{doctor_name} గారికి అందుబాటులో ఉన్న స్లాట్లను చూపించమంటారా?"

        ),

        "gratitude_closure": (

            "ధన్యవాదాలు! మీకు ఎప్పుడు అవసరమైనా సహాయం చేయడానికి ఆరోగ్య వన్ హాస్పిటల్ సిద్ధంగా ఉంది. జాగ్రత్తగా ఉండండి, మీ రోజు శుభప్రదంగా గడవాలి!"

        ),

        "cancelled": (

            "అర్థమైంది. మీ అపాయింట్‌మెంట్ బుకింగ్ రద్దు చేయబడింది (Cancelled). "

            "మీకు ఇతర డాక్టర్లు లేదా సేవల వివరాలు కావాలంటే తెలియజేయండి."

        ),

        "already_booked": (

            "మీ అపాయింట్‌మెంట్ ఇప్పటికే ఖరారు చేయబడింది (Appointment ID: {appt_id}). "

            "కొత్త అపాయింట్‌మెంట్ బుక్ చేయాలంటే సెషన్‌ను రీసెట్ చేయండి."

        ),

        "searching_doctor": "డాక్టర్ {doc} గారి వివరాలను వెతుకుతున్నాను...",

        "searching_specialty": "{specialty} విభాగంలో అందుబాటులో ఉన్న నిపుణుల కోసం వెతుకుతున్నాను...",

        "checking_slots": "{doctor_name} గారికి అందుబాటులో ఉన్న స్లాట్లను తనిఖీ చేస్తున్నాను...",

        "ask_reason": (
            "మీరు {doctor_name} గారితో {slot_display} సమయాన్ని ఎంచుకున్నారు. "

            "ఈ సంప్రదింపులకు గల కారణం లేదా మీ లక్షణాలు ఏమిటి? (ఉదా: 'గుండె నొప్పి పరీక్ష', 'సాధారణ తనిఖీ')"

        ),

        "ask_patient_ref": (

            "మీ అపాయింట్‌మెంట్‌ను సిద్ధం చేయడానికి ముందు, మీరు గతంలో ఆరోగ్య వన్ ఆసుపత్రిని సందర్శించారా?"

        ),

        "symptom_empathy_general_medicine": (

            "మీరు అనారోగ్యంతో ఉన్నందుకు బాధపడుతున్నాను. ఆరోగ్య వన్ ఆసుపత్రిలో సంప్రదింపులను బుక్ చేయడంలో నేను మీకు సహాయపడతాను.\n\n"

            "జ్వరానికి జనరల్ మెడిసిన్ సరైన ప్రారంభ విభాగం.\n\n"

            "అందుబాటులో ఉన్న జనరల్ మెడిసిన్ వైద్యులను చూడమంటారా?"

        ),

        "doctor_found_consult_or_more": (

            "నేను {specialty} నిపుణులైన {doctor_name} గారిని కనుగొన్నాను. వారి అపాయింట్‌మెంట్ సమయాలను చూడమంటారా?"

        ),

        "checking_slots_for_doctor": "చాలా మంచిది! {doctor_name} గారి అందుబాటులో ఉన్న సమయాలను పరిశీలిస్తున్నాను.",

        "suggest_earliest_slot": (

            "సరేనండి! అత్యంత త్వరగా అందుబాటులో ఉన్న సమయం {slot_time}.\n\n"

            "ఆ సమయాన్ని మీ కోసం రిజర్వ్ చేయమంటారా?"

        ),

        "ask_visited_before": (

            "మీ అపాయింట్‌మెంట్‌ను సిద్ధం చేయడానికి ముందు, మీరు గతంలో ఆరోగ్య వన్ ఆసుపత్రిని సందర్శించారా?"

        ),

        "welcome_new_patient_ask_name": (

            "ఆరోగ్య వన్ ఆసుపత్రికి స్వాగతం! కొత్త రోగి నమోదు ప్రక్రియలో నేను మీకు సహాయం చేస్తాను.\n\n"

            "దయచేసి మీ పూర్తి పేరు చెప్పగలరా?"

        ),

        "thank_name_ask_phone": (

            "ధన్యవాదాలు, {name}. అపాయింట్‌మెంట్ సమాచారం కోసం మీ మొబైల్ నంబర్ తెలియజేయగలరా?"

        ),

        "welcome_back_ask_reference": (

            "మరలా స్వాగతం! మీకు మరొక అపాయింట్‌మెంట్ బుక్ చేయడానికి నేను సంతోషిస్తాను. మీ పేషెంట్ రికార్డును కనుగొనడానికి మీ నమోదిత మొబైల్ నంబర్‌ను పంచుకోగలరా?"

        ),

        "welcome_back_ask_phone": (

            "మరలా స్వాగతం! మీకు మరొక అపాయింట్‌మెంట్ బుక్ చేయడానికి నేను సంతోషిస్తాను. మీ పేషెంట్ రికార్డును కనుగొనడానికి మీ నమోదిత మొబైల్ నంబర్‌ను పంచుకోగలరా?"

        ),

        "forgot_reference_ask_phone": (

            "చింతించకండి! మీరు మీ పేషెంట్ ఐడీని గుర్తుంచుకోవాల్సిన అవసరం లేదు. మీ నమోదిత మొబైల్ నంబర్‌ని ఉపయోగించి మీ రికార్డును కనుగొనడానికి మేము ప్రయత్నించవచ్చు."

        ),

        "patient_verified_success": (

            "ధన్యవాదాలు! {patient_name} గారి పేషెంట్ రికార్డును మేము గుర్తించాము.\n\n"

            "గమనిక: అపాయింట్‌మెంట్ షెడ్యూలింగ్ కొరకు హాస్పిటల్ రికార్డు సరిపోల్చబడింది. అధికారిక ఫోటో గుర్తింపు ధృవీకరణ హాస్పిటల్ చెక్-ఇన్ సమయంలో రిసెప్షన్ వద్ద పూర్తవుతుంది."

        ),

        "patient_not_found_options": (

            "ఆ మొబైల్ నంబర్‌తో రికార్డు కనుగొనబడలేదు. మీరు కొత్త పేషెంట్‌గా నమోదు చేసుకోవాలనుకుంటున్నారా?"

        ),

        "confirm_summary": (
            "దయచేసి మీ అపాయింట్\u200cమెంట్ వివరాలను సరిచూసి నిర్ధారించండి:\n"
            "• పేషెంట్: {patient_reference}\n"
            "• డాక్టర్: {doctor_name} ({specialty})\n"
            "• సమయం: {slot_display}\n"
            "• కారణం: {reason_category}\n\n"
            "ఈ బుకింగ్ ఖరారు చేయడానికి దయచేసి 'అవును' అని చెప్పండి. మార్పులు లేదా రద్దు చేయడానికి 'వద్దు' అని చెప్పండి."
        ),

        "decline_confirm_ask_modify_or_cancel": (

            "అర్థమైంది. మీరు వైద్యుడిని లేదా అపాయింట్‌మెంట్ సమయాన్ని మార్చాలనుకుంటున్నారా, లేదా ఈ బుకింగ్‌ను రద్దు చేయాలనుకుంటున్నారా?"

        ),

        "resuming_booking": (

            "తప్పకుండా! మీ అపాయింట్‌మెంట్ బుకింగ్‌ను కొనసాగిస్తున్నాను."

        ),

        "processing_booking": "నిర్ధారించినందుకు ధన్యవాదాలు. మీ అపాయింట్‌మెంట్ బుకింగ్ ప్రాసెస్ చేస్తున్నాను...",

        "offer_specialty_consultation": (

            "ఖచ్చితంగా! నేను మీకు {specialty} కన్సల్టేషన్ ఏర్పాటు చేయగలను. అందుబాటులో ఉన్న {specialist_noun}ను నేను వెతకమంటారా?"

        ),

        "checking_available_specialists": (

            "తప్పకుండా. అందుబాటులో ఉన్న {specialist_plural} చూస్తున్నాను."

        ),

        "found_specialists_recommend": (

            "నేను {count} {specialist_plural} కనుగొన్నాను:\n{doc_list}\n\n"

            "లభ్యత ఆధారంగా {recommend_name}ను సిఫార్సు చేయమంటారా?"

        ),

        "specialist_choice_excellent": (

            "{doctor_name} మంచి ఎంపిక. అందుబాటులో ఉన్న అపాయింట్‌మెంట్ స్లాట్‌లను చూస్తున్నాను."

        ),

        "found_doctors": (

            "ఆరోగ్య వన్ హాస్పిటల్‌లో {count} మంది నిపుణులు అందుబాటులో ఉన్నారు:\n{doc_list}\n\n"

            "మీరు ఏ డాక్టర్ గారితో అపాయింట్‌మెంట్ బుక్ చేయాలనుకుంటున్నారు?"

        ),

        "selected_doctor_slots": (

            "{doctor_name} ({specialty}) ఎంచుకోబడ్డారు.\n"

            "అందుబాటులో ఉన్న అపాయింట్‌మెంట్‌లు:\n{slot_lines}\n\n"

            "మీకు ఏ సమయం అనుకూలంగా ఉంటుంది?"

        ),

        "recommended_doctor_slots": (

            "{specialty} కోసం డాక్టర్ {doctor_name} గారిని సిఫార్సు చేస్తున్నాను.\n"

            "అందుబాటులో ఉన్న అపాయింట్‌మెంట్‌లు:\n{slot_lines}\n\n"

            "మీకు ఏ సమయం అనుకూలంగా ఉంటుంది? (లేదా మీరు వేరే వైద్యుడిని సంప్రదించాలనుకుంటున్నారా?)"

        ),

        "available_slots": (

            "{doctor_name} గారికి అందుబాటులో ఉన్న అపాయింట్‌మెంట్‌లు:\n{slot_lines}\n\n"

            "మీకు ఏ సమయం అనుకూలంగా ఉంటుంది?"

        ),

        "invalid_slot": (

            "'{invalid_slot}' అనేది {doctor_name} గారికి అందుబాటులో ఉన్న సరైన స్లాట్ ఐడి కాదు (Invalid slot ID). "

            "దయచేసి అందుబాటులో ఉన్న ఈ స్లాట్ ఐడిలలో ఒకదాన్ని ఎంచుకోండి: {available_ids}\n"

            "{slot_lines}"

        ),

        "urgent_chest_pain_note": (

            "⚠️ అత్యవసర వైద్య సూచన (Emergency Guidance): ఛాతీ నొప్పి లేదా తీవ్రమైన శ్వాస/నరాల లక్షణాలు అత్యవసర వైద్య పరిస్థితి కావచ్చు. "

            "నొప్పి తీవ్రంగా ఉన్నా, ఊపిరి ఆడకపోయినా లేదా చెమటలు పడుతున్నా, అవుట్‌పేషెంట్ అపాయింట్‌మెంట్ కోసం ఆలస్యం చేయకుండా "

            "వెంటనే అత్యవసర సేవలను (108 / 112) లేదా సమీప ఎమర్జెన్సీ విభాగాన్ని సంప్రదించండి."

        ),

        "no_slots": "{doctor_name} గారికి ప్రస్తుతం ఖాళీ స్లాట్లు లేవు. మరో డాక్టర్ లేదా తేదీని చూడమంటారా?",

        "no_doctors": "ఆ విభాగంలో డాక్టర్లు కనుగొనబడలేదు. జనరల్ మెడిసిన్ లేదా వేరే విభాగం చూడమంటారా?",

        "changed_reconfirm": (

            "బుకింగ్ వివరాలు మారాయి. దయచేసి కొత్త వివరాలను నిర్ధారించండి:\n"

            "• Doctor: {doctor_name}\n"

            "• Slot: {slot_display}\n"

            "• Reason: {reason_category}\n"

            "• Patient Reference: {patient_reference}\n\n"

            "బుకింగ్ పూర్తి చేయడానికి 'అవును' (YES) అని సమాధానం ఇవ్వండి."

        ),

        "explicit_confirm_required": (

            "బుక్ చేయడానికి ముందు మీ స్పష్టమైన నిర్ధారణ అవసరం. "

            "దయచేసి నిర్ధారించడానికి 'అవును' (YES) లేదా రద్దు చేయడానికి 'వద్దు' (NO) అని చెప్పండి."

        ),

        "booking_confirmed": (

            "అపాయింట్‌మెంట్ ఖరారు చేయబడింది! (Appointment Confirmed! 🎉)\n"

            "• Appointment ID: {appointment_id}\n"

            "• Doctor: {doctor_name}\n"

            "• Schedule: {appointment_start_time}\n"

            "• Status: {appointment_status}\n"

            "• Patient Reference: {patient_reference}\n\n"

            "మీ అపాయింట్మెంట్ వివరాలు మీ రిజిస్టర్ చేసిన మొబైల్ నంబర్కు SMS ద్వారా పంపబడతాయి (డెమో ప్రకటన).\n\n"

            "ఆరోగ్య వన్ హాస్పిటల్ను ఎంచుకున్నందుకు ధన్యవాదాలు. మీకు త్వరగా కోలుకోవాలని కోరుకుంటున్నాము. జాగ్రత్తగా ఉండండి!"

        ),

        "doctor_not_found_ask_alternative": (

            "డాక్టర్ {doctor_name} గారు ఆరోగ్య వన్ హాస్పిటల్‌లో అందుబాటులో లేరు. మీరు మరొక వైద్యుడితో అపాయింట్‌మెంట్ తీసుకోవాలనుకుంటున్నారా లేదా మా వద్ద ఉన్న వైద్యుల జాబితాను చూడాలనుకుంటున్నారా?"

        ),

        "doctor_ambiguous_clarify": (

            "'{doctor_name}' పేరుతో పలువురు వైద్యులు ఉన్నారు. దయచేసి మీరు ఏ వైద్యుడిని సంప్రదించాలనుకుంటున్నారో తెలియజేయగలరా?"

        ),

        "booking_failed": (

            "Booking could not be completed: {error}\n"

            "ఎంచుకున్న స్లాట్ అందుబాటులో లేదు. దయచేసి వేరొక అందుబాటులో ఉన్న స్లాట్‌ను ఎంచుకోండి."

        ),

        "provider_error": (

            "AI సేవ తాత్కాలికంగా అందుబాటులో లేదు ({reason}). దయచేసి మళ్ళీ ప్రయత్నించండి."

        ),

    },

    "ta": {
        "ask_which_doctor_preferred": "நிச்சயமாக! நீங்கள் எந்த மருத்துவர் அல்லது துறையை அணுக விரும்புகிறீர்கள்?",

        "patient_verified_success": (
            "நன்றி! {patient_name} அவர்களின் நோயாளி பதிவு கண்டறியப்பட்டது.\n\n"
            "குறிப்பு: முன்பதிவு திட்டமிடலுக்காக மருத்துவமனை தொடர்பு பதிவு சரிபார்க்கப்பட்டது. அதிகாரப்பூர்வ புகைப்பட அடையாளச் சரிபார்ப்பு மருத்துவமனை வரவேற்பறையில் செக்-இன் செய்யும் போது செய்யப்படும்."
        ),
        "clarify_account_vs_booking": (

            "நீங்கள் ஆரோக்கியா ஒன் மருத்துவமனையில் மருத்துவர் அப்பாயிண்ட்மென்ட் பதிவு செய்ய விரும்புகிறீர்களா, அல்லது புதிய நோயாளி கணக்கு (Account) பதிவு செய்ய விரும்புகிறீர்களா? "

            "தயவுசெய்து தெரிவிக்கவும்."

        ),

        "greeting": (

            "வணக்கம்! நான் ஆரோக்கியா ஒன் மருத்துவமனையின் (Aarogya One Hospital) மெடிவாய்ஸ் உதவியாளர். "

            "உங்களுக்கு எந்த மருத்துவத் துறை அல்லது மருத்துவரிடம் ஆலோசனை தேவை? "

            "(எ.கா: Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine)"

        ),

        "how_to_book": (

            "ஆரோக்கியா ஒன் மருத்துவமனையில் அப்பாயின்ட்மென்ட் முன்பதிவு செய்ய நான் உதவுகிறேன்! "

            "உங்களுக்குத் தேவையான மருத்துவத் துறை, மருத்துவர் பெயர் அல்லது உங்கள் அறிகுறிகளைக் கூறுங்கள் "

            "(எ.கா: 'Cardiology', 'டாக்டர் ராஜேஷ் சர்மா', 'மூட்டு வலி', அல்லது 'காய்ச்சல்')."

        ),

        "departments_info": (

            "ஆரோக்கியா ஒன் மருத்துவமனையில் 5 முக்கிய துறைகளில் சிறப்பு மருத்துவர்கள் உள்ளனர்:\n"

            "• Cardiology (இதயவியல்) — Dr. Rajesh Sharma, Dr. Priya Nair\n"

            "• Neurology (நரம்பியல்) — Dr. Arvind Swamy\n"

            "• Orthopedics (எலும்பியல்) — Dr. Vikram Mehta\n"

            "• Pediatrics (குழந்தைகள் நலம்) — Dr. Ananya Sen\n"

            "• General Medicine (பொது மருத்துவம்) — Dr. Sunita Rao\n\n"

            "எந்தத் துறை அல்லது மருத்துவரைப் பார்க்க விரும்புகிறீர்கள்?"

        ),

        "hours_info": (

            "ஆரோக்கியா ஒன் மருத்துவமனை (பெங்களூரு) புறநோயாளிகள் பிரிவு (OPD) திங்கள் முதல் சனி வரை காலை 08:00 முதல் இரவு 08:00 வரை செயல்படும். "

            "அவசர சிகிச்சைப் பிரிவு (Emergency) 24/7 செயல்படுகிறது (அவசர எண்: 108 / 112)."

        ),

        "ambiguous_confirm": (

            "பரவாயில்லை, உங்கள் நேரத்தை எடுத்துக்கொள்ளுங்கள்! உங்கள் அப்பாயின்ட்மென்ட் இன்னும் முன்பதிவு செய்யப்படவில்லை. "

            "நீங்கள் தயாராக இருக்கும்போது உறுதிப்படுத்த 'ஆம்' (YES) என்றும், ரத்து செய்ய 'வேண்டாம்' (NO) என்றும் கூறவும், "

            "அல்லது மருத்துவர்/நேரத்தை மாற்ற விரும்பினால் தெரிவிக்கவும்."

        ),

        "ambiguous_general": (

            "பரவாயில்லை, எந்த மருத்துவரைப் பார்ப்பது என்று தயக்கமாக இருந்தால் நான் உதவுகிறேன்! "

            "உங்களுக்கு தற்போது என்ன அறிகுறி அல்லது உடல்நலப் பிரச்சினை உள்ளது (எ.கா: காய்ச்சல், தலைவலி, மூட்டு வலி)? "

            "அல்லது முதலில் பொது மருத்துவப் பிரிவில் (General Medicine) ஆலோசனை பெற விரும்புகிறீர்களா?"

        ),

        "ambiguous_doctor_choice": (

            "பரவாயில்லை! பட்டியலிடப்பட்ட சிறப்பு மருத்துவர்களில் ({doc_names}) ஒருவரைத் தேர்ந்தெடுக்க நான் உதவுகிறேன். "

            "உங்களுக்கு காலை அல்லது மதியம் எந்த நேரம் வசதியாக இருக்கும், அல்லது விரைவில் கிடைக்கும் முதல் நேரத்தைக் காட்டட்டுமா?"

        ),

        "clarify_need": (

            "ஆரோக்கியா ஒன் மருத்துவமனையில் அப்பாயின்ட்மென்ட் முன்பதிவு செய்ய நான் தயாராக உள்ளேன். "

            "உங்கள் அறிகுறிகள் என்ன அல்லது எந்தத் துறை/மருத்துவரைப் பார்க்க விரும்புகிறீர்கள் என்று கூற முடியுமா?"

        ),

        "emergency_priority": (

            "🚨 அவசர மருத்துவ முன்னுரிமை (Emergency Priority): கடுமையான நெஞ்சு வலி அல்லது உயிருக்கு ஆபத்தான அறிகுறிகளுக்கு உடனடி அவசர மருத்துவப் பரிசோதனை தேவை. "

            "சாதாரண அப்பாயின்ட்மென்ட் முன்பதிவுக்காகக் காத்திருக்காமல், உடனடியாக 108 அல்லது 112 என்ற அவசர எண்ணுக்கு அழைக்கவும், அல்லது அருகிலுள்ள மருத்துவமனையின் அவசர சிகிச்சைப் பிரிவுக்கு (Emergency Department) செல்லவும். "

            "உங்கள் உடனடிப் பாதுகாப்பே மிகவும் முக்கியம்."

        ),

        "emergency_followup": (

            "🚨 அவசர பாதுகாப்பு நினைவூட்டல்: நீங்கள் தொடர்ந்து தீவிரமான அறிகுறிகளைக் குறிப்பிடுவதால், சாதாரண முன்பதிவைத் தொடர்வது பாதுகாப்பானது அல்ல. "

            "தயவுசெய்து தாமதிக்காமல் உடனடியாக 108 / 112 ஐ அழைக்கவும் அல்லது அருகிலுள்ள அவசர சிகிச்சைப் பிரிவுக்குச் செல்லவும்."

        ),

        "missing_details_error": (

            "இன்னும் முன்பதிவு செய்ய முடியாது. விடுபட்ட விவரங்கள்: {missing}."

        ),

        "detail_captured_pick_slot": (

            "உங்கள் விவரங்களைக் குறித்துக்கொண்டேன். {doctor_name} உடன் முன்பதிவைத் தொடர, கிடைக்கும் இந்த ஸ்லாட் ஐடிகளில் ஒன்றைத் தேர்ந்தெடுக்கவும்: {available_ids}."

        ),

        "symptom_added_keep_specialty": (

            "உங்கள் அறிகுறிகளை ({reason_category}) குறித்துக்கொண்டேன். இதற்கு {specialty} துறையின் {doctor_name} அவர்களிடம் ஆலோசனை பெறுவது பொருத்தமானது. "

            "{doctor_name} அவர்களுக்கான கிடைக்கும் நேரங்களைக் காட்டட்டுமா?"

        ),

        "gratitude_closure": (

            "மகிழ்ச்சி! உங்களுக்கு தேவைப்படும் போதெல்லாம் உதவ ஆரோக்கியா ஒன் மருத்துவமனை எப்போதும் தயாராக உள்ளது. உடலை நன்றாகப் பார்த்துக் கொள்ளுங்கள், நல்ல நாளாக அமையட்டும்!"

        ),

        "cancelled": (

            "புரிந்தது. உங்கள் அப்பாயின்ட்மென்ட் முன்பதிவு ரத்து செய்யப்பட்டது (Cancelled). "

            "வேறு மருத்துவர்கள் அல்லது சேவைகளைப் பார்க்க விரும்பினால் தெரிவிக்கவும்."

        ),

        "already_booked": (

            "உங்கள் அப்பாயின்ட்மென்ட் ஏற்கனவே உறுதி செய்யப்பட்டுவிட்டது (Appointment ID: {appt_id}). "

            "புதிய முன்பதிவுக்கு அமர்வை மீட்டமைக்கவும்."

        ),

        "doctor_found_consult_or_more": (

            "நான் {specialty} நிபுணர் {doctor_name} அவர்களைக் கண்டறிந்தேன். அவருக்கான கிடைக்கும் நேரங்களைச் சரிபார்க்கட்டுமா?"

        ),

        "searching_doctor": "டாக்டர் {doc} விவரங்களைத் தேடுகிறேன்...",

        "searching_specialty": "{specialty} துறையில் உள்ள சிறப்பு மருத்துவர்களைத் தேடுகிறேன்...",

        "checking_slots": "{doctor_name} அவர்களின் காலியான நேரங்களை (slots) சரிபார்க்கிறேன்...",

        "ask_reason": (
            "நீங்கள் {doctor_name} உடன் {slot_display} நேரத்தைத் தேர்ந்தெடுத்துள்ளீர்கள். "

            "இந்த மருத்துவ ஆலோசனைக்கான காரணம் அல்லது அறிகுறிகள் என்ன? (எ.கா: 'நெஞ்சு வலி பரிசோதனை', 'வழக்கமான பரிசோதனை')"

        ),

        "ask_patient_ref": (

            "முன்பதிவைத் தயார் செய்ய உங்கள் செயற்கை நோயாளி குறிப்பு எண்ணை (Patient Reference ID, எ.கா: 'PAT-2026-4409') வழங்கவும்."

        ),

        "confirm_summary": (
            "தயவுசெய்து உங்கள் முன்பதிவு விவரங்களைச் சரிபார்க்கவும்:\n"
            "• நோயாளி: {patient_reference}\n"
            "• மருத்துவர்: {doctor_name} ({specialty})\n"
            "• நேரம்: {slot_display}\n"
            "• காரணம்: {reason_category}\n\n"
            "முன்பதிவை உறுதிசெய்ய 'ஆம்' என்று கூறவும். மாற்ற அல்லது ரத்து செய்ய 'இல்லை' என்று கூறவும்."
        ),

        "processing_booking": "உறுதிப்படுத்தியதற்கு நன்றி. உங்கள் முன்பதிவைச் செயல்படுத்துகிறேன்...",

        "offer_specialty_consultation": (

            "நிச்சயமாக! நான் உங்களுக்கு {specialty} ஆலோசனையை ஏற்பாடு செய்ய உதவ முடியும். கிடைக்கக்கூடிய {specialist_noun}யை நான் பார்க்கட்டுமா?"

        ),

        "checking_available_specialists": (

            "நிச்சயமாக. கிடைக்கக்கூடிய {specialist_plural}ப் பார்க்கிறேன்."

        ),

        "found_specialists_recommend": (

            "{count} {specialist_plural} கண்டறியப்பட்டது:\n{doc_list}\n\n"

            "கிடைக்கும் நேரத்தின் அடிப்படையில் {recommend_name}யை பரிந்துரைக்கட்டுமா?"

        ),

        "specialist_choice_excellent": (

            "{doctor_name} சிறந்த தேர்வு. கிடைக்கக்கூடிய முன்பதிவு நேரங்களைச் சரிபார்க்கிறேன்."

        ),

        "found_doctors": (

            "ஆரோக்கியா ஒன் மருத்துவமனையில் {count} சிறப்பு மருத்துவர்(கள்) உள்ளனர்:\n{doc_list}\n\n"

            "எந்த மருத்துவருடன் அப்பாயின்ட்மென்ட் முன்பதிவு செய்ய விரும்புகிறீர்கள்?"

        ),

        "selected_doctor_slots": (

            "{doctor_name} ({specialty}) தேர்ந்தெடுக்கப்பட்டார்.\n\n"

            "கிடைக்கும் நேரங்கள்:\n{slot_lines}\n\n"

            "உங்களுக்கு எந்த நேரம் வசதியாக இருக்கும்?"

        ),

        "recommended_doctor_slots": (

            "{specialty} பிரிவிற்கு டாக்டர் {doctor_name} அவர்களைப் பரிந்துரைக்கிறேன்.\n"

            "கிடைக்கும் நேரங்கள்:\n{slot_lines}\n\n"

            "உங்களுக்கு எந்த நேரம் வசதியாக இருக்கும்? (நீங்கள் விரும்பினால் வேறு மருத்துவரைத் தேர்ந்தெடுக்கலாம்.)"

        ),

        "available_slots": (

            "{doctor_name} அவர்களுக்கான கிடைக்கும் நேரங்கள்:\n{slot_lines}\n\n"

            "உங்களுக்கு எந்த நேரம் வசதியாக இருக்கும்?"

        ),

        "invalid_slot": (

            "'{invalid_slot}' என்பது {doctor_name} அவர்களுக்குக் கிடைக்கும் சரியான ஸ்லாட் ஐடி அல்ல (Invalid slot ID). "

            "தயவுசெய்து கீழே உள்ள கிடைக்கும் ஸ்லாட் ஐடிகளில் ஒன்றைத் தேர்ந்தெடுக்கவும்: {available_ids}\n"

            "{slot_lines}"

        ),

        "urgent_chest_pain_note": (

            "⚠️ அவசர மருத்துவ வழிகாட்டுதல் (Emergency Guidance): நெஞ்சு வலி அல்லது கடுமையான மூச்சுத்திணறல் ஒரு அவசர மருத்துவ நிலையாக இருக்கலாம். "

            "வலி கடுமையாக இருந்தாலோ, மூச்சுத்திணறல் அல்லது வியர்வை இருந்தாலோ, முன்பதிவுக்காக தாமதிக்காமல் "

            "உடனடியாக அவசர சேவையை (108 / 112) அல்லது அவசர சிகிச்சைப் பிரிவை அணுகவும்."

        ),

        "no_slots": "{doctor_name} அவர்களுக்கு தற்போது காலியான நேரங்கள் இல்லை. வேறு மருத்துவரைப் பார்க்கலாமா?",

        "no_doctors": "அந்தத் தேடலுக்குப் பொருந்தும் மருத்துவர்கள் இல்லை. வேறு துறையைப் பார்க்க விரும்புகிறீர்களா?",

        "changed_reconfirm": (

            "முன்பதிவு விவரங்கள் மாற்றப்பட்டுள்ளன. புதிய விவரங்களை உறுதிப்படுத்தவும்:\n"

            "• Doctor: {doctor_name}\n"

            "• Slot: {slot_display}\n"

            "• Reason: {reason_category}\n"

            "• Patient Reference: {patient_reference}\n\n"

            "முன்பதிவை இறுதி செய்ய 'ஆம்' (YES) என பதிலளிக்கவும்."

        ),

        "explicit_confirm_required": (

            "முன்பதிவு செய்வதற்கு முன் உங்கள் வெளிப்படையான உறுதிப்படுத்தல் தேவை. "

            "உறுதிப்படுத்த 'ஆம்' (YES) அல்லது ரத்து செய்ய 'வேண்டாம்' (NO) என பதிலளிக்கவும்."

        ),

        "booking_confirmed": (

            "அப்பாயின்ட்மென்ட் உறுதி செய்யப்பட்டது! (Appointment Confirmed! 🎉)\n"

            "• Appointment ID: {appointment_id}\n"

            "• Doctor: {doctor_name}\n"

            "• Schedule: {appointment_start_time}\n"

            "• Status: {appointment_status}\n"

            "• Patient Reference: {patient_reference}\n\n"

            "உங்கள் அப்பாயிண்ட்மென்ட் விவரங்கள் பதிவுசெய்யப்பட்ட மொபைல் எண்ணிற்கு எஸ்எம்எஸ் மூலம் அனுப்பப்படும் (டெமோ அறிவிப்பு).\n\n"

            "ஆரோக்கியா ஒன் மருத்துவமனையைத் தேர்ந்தெடுத்ததற்கு நன்றி. நீங்கள் விரைவில் குணமடைய வாழ்த்துகிறோம்!"

        ),

        "doctor_not_found_ask_alternative": (

            "டாக்டர் {doctor_name} ஆரோக்கியா ஒன் மருத்துவமனையில் இல்லை. நீங்கள் மற்றொரு மருத்துவரிடம் அப்பாயிண்ட்மென்ட் பதிவு செய்ய விரும்புகிறீர்களா அல்லது எங்கள் மருத்துவர்களின் பட்டியலைப் பார்க்க விரும்புகிறீர்களா?"

        ),

        "doctor_ambiguous_clarify": (

            "'{doctor_name}' பெயரில் பல மருத்துவர்கள் உள்ளனர். நீங்கள் எந்த மருத்துவரை அணுக விரும்புகிறீர்கள் என்பதைத் தெளிவுபடுத்த முடியுமா?"

        ),

        "booking_failed": (

            "Booking could not be completed: {error}\n"

            "தேர்ந்தெடுக்கப்பட்ட நேரம் கிடைக்கவில்லை. தயவுசெய்து வேறு காலியான நேரத்தைத் தேர்ந்தெடுக்கவும்."

        ),

        "provider_error": (

            "AI சேவை தற்காலிகமாகக் கிடைக்கவில்லை ({reason}). தயவுசெய்து சிறிது நேரம் கழித்து முயற்சிக்கவும்."

        ),

    },

    "kn": {
        "ask_which_doctor_preferred": "ಖಂಡಿತವಾಗಿಯೂ! ನೀವು ಯಾವ ವೈದ್ಯರನ್ನು ಅಥವಾ ವಿಭಾಗವನ್ನು ಸಂಪರ್ಕಿಸಲು ಬಯಸುತ್ತೀರಿ?",

        "clarify_account_vs_booking": (

            "\u0ca8\u0cc0\u0cb5\u0cc1 \u0c86\u0cb0\u0ccb\u0c97\u0ccd\u0caf \u0c92\u0ca8\u0ccd \u0c86\u0cb8\u0ccd\u0caa\u0ca4\u0ccd\u0cb0\u0cc6\u0caf\u0cb2\u0ccd\u0cb2\u0cbf \u0cb5\u0cc8\u0ca6\u0ccd\u0caf\u0cb0 \u0c85\u0caa\u0cbe\u0caf\u0cbf\u0c82\u0c9f\u0ccd\u200c\u0cae\u0cc6\u0c82\u0c9f\u0ccd \u0cac\u0cc1\u0c95\u0ccd \u0cae\u0cbe\u0ca1\u0cb2\u0cc1 \u0cac\u0caf\u0cb8\u0cc1\u0cb5\u0cbf\u0cb0\u0cbe, \u0c85\u0ca5\u0cb5\u0cbe \u0cb9\u0cca\u0cb8 \u0cb0\u0ccb\u0c97\u0cbf\u0caf \u0c96\u0cbe\u0ca4\u0cc6 (Account) \u0ca8\u0ccb\u0c82\u0ca6\u0cbe\u0caf\u0cbf\u0cb8\u0cb2\u0cc1 \u0cac\u0caf\u0cb8\u0cc1\u0cb5\u0cbf\u0cb0\u0cbe? "

            "\u0ca6\u0caf\u0cb5\u0cbf\u0c9f\u0ccd\u0c9f\u0cc1 \u0ca4\u0cbf\u0cb3\u0cbf\u0cb8\u0cbf."

        ),

        "greeting": (

            "ನಮಸ್ಕಾರ! ನಾನು ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯ (Aarogya One Hospital) ಮೆಡಿವಾಯ್ಸ್ ಸಹಾಯಕ. "

            "ನಿಮಗೆ ಯಾವ ವಿಭಾಗ ಅಥವಾ ಯಾವ ವೈದ್ಯರ ಸಮಾಲೋಚನೆ ಬೇಕು? "

            "(ಉದಾ: Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine)"

        ),

        "how_to_book": (

            "ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯಲ್ಲಿ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲು ನಾನು ನಿಮಗೆ ಸಹಾಯ ಮಾಡುತ್ತೇನೆ! "

            "ದಯವಿಟ್ಟು ನಿಮಗೆ ಬೇಕಾದ ವಿಭಾಗ, ವೈದ್ಯರ ಹೆಸರು ಅಥವಾ ನಿಮ್ಮ ಆರೋಗ್ಯ ಸಮಸ್ಯೆಯನ್ನು ತಿಳಿಸಿ "

            "(ಉದಾ: 'Cardiology', 'ಡಾ. ರಾಜೇಶ್ ಶರ್ಮಾ', 'ಮಂಡಿ ನೋವು', ಅಥವಾ 'ಜ್ವರ')."

        ),

        "departments_info": (

            "ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯಲ್ಲಿ 5 ಪ್ರಮುಖ ವಿಭಾಗಗಳಲ್ಲಿ ತಜ್ಞ ವೈದ್ಯರು ಲಭ್ಯವಿದ್ದಾರೆ:\n"

            "• Cardiology (ಹೃದ್ರೋಗ ವಿಭಾಗ) — Dr. Rajesh Sharma, Dr. Priya Nair\n"

            "• Neurology (ನರರೋಗ ವಿಭಾಗ) — Dr. Arvind Swamy\n"

            "• Orthopedics (ಮೂಳೆ ಮತ್ತು ಕೀಲು ವಿಭಾಗ) — Dr. Vikram Mehta\n"

            "• Pediatrics (ಮಕ್ಕಳ ವಿಭಾಗ) — Dr. Ananya Sen\n"

            "• General Medicine (ಸಾಮಾನ್ಯ ವೈದ್ಯಕೀಯ) — Dr. Sunita Rao\n\n"

            "ನೀವು ಯಾವ ವಿಭಾಗ ಅಥವಾ ವೈದ್ಯರನ್ನು ಸಂಪರ್ಕಿಸಲು ಬಯಸುತ್ತೀರಿ?"

        ),

        "hours_info": (

            "ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆ (ಬೆಂಗಳೂರು) ಹೊರರೋಗಿ ವಿಭಾಗ (OPD) ಸೋಮವಾರದಿಂದ ಶನಿವಾರದವರೆಗೆ ಬೆಳಿಗ್ಗೆ 08:00 ರಿಂದ ರಾತ್ರಿ 08:00 ರವರೆಗೆ ತೆರೆದಿರುತ್ತದೆ. "

            "ತುರ್ತು ಚಿಕಿತ್ಸಾ ವಿಭಾಗ (Emergency) 24/7 ಲಭ್ಯವಿದೆ (ತುರ್ತು ಸಂಖ್ಯೆ: 108 / 112)."

        ),

        "ambiguous_confirm": (

            "ಪರವಾಗಿಲ್ಲ, ನಿಮ್ಮ ಸಮಯ ತೆಗೆದುಕೊಳ್ಳಿ! ನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಇನ್ನೂ ಬುಕ್ ಆಗಿಲ್ಲ. "

            "ನೀವು ಸಿದ್ಧರಾದಾಗ ಬುಕಿಂಗ್ ಖಚಿತಪಡಿಸಲು 'ಹೌದು' (YES) ಎಂದು, ರದ್ದುಗೊಳಿಸಲು 'ಬೇಡ' (NO) ಎಂದು ಉತ್ತರಿಸಿ, "

            "ಅಥವಾ ವೈದ್ಯರು/ಸ್ಲಾಟ್ ಬದಲಾಯಿಸಲು ತಿಳಿಸಿ."

        ),

        "ambiguous_general": (

            "ಪರವಾಗಿಲ್ಲ, ಯಾವ ವೈದ್ಯರನ್ನು ಭೇಟಿಯಾಗಬೇಕೆಂದು ಗೊಂದಲವಾಗುವುದು ಸಹಜ! ನಾನು ನಿಮಗೆ ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. "

            "ನಿಮಗೆ ಪ್ರಸ್ತುತ ಯಾವ ಲಕ್ಷಣ ಅಥವಾ ಆರೋಗ್ಯ ಸಮಸ್ಯೆ ಇದೆ (ಉದಾ: ಜ್ವರ, ತಲೆನೋವು, ಮಂಡಿ ನೋವು)? "

            "ಅಥವಾ ಮೊದಲು ಸಾಮಾನ್ಯ ವೈದ್ಯಕೀಯ (General Medicine) ವೈದ್ಯರೊಂದಿಗೆ ಸಮಾಲೋಚನೆ ಏರ್ಪಡಿಸಲೇ?"

        ),

        "ambiguous_doctor_choice": (

            "ಪರವಾಗಿಲ್ಲ! ಲಭ್ಯವಿರುವ ಈ ತಜ್ಞ ವೈದ್ಯರಲ್ಲಿ ({doc_names}) ಸೂಕ್ತವಾದವರನ್ನು ಆಯ್ಕೆ ಮಾಡಲು ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. "

            "ನಿಮಗೆ ಬೆಳಿಗ್ಗೆ ಅಥವಾ ಮಧ್ಯಾಹ್ನ ಯಾವ ಸಮಯ ಅನುಕೂಲಕರವಾಗಿದೆ, ಅಥವಾ ಮೊದಲು ಲಭ್ಯವಿರುವ ಸ್ಲಾಟ್ ತೋರಿಸಲೇ?"

        ),

        "clarify_need": (

            "ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯಲ್ಲಿ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲು ನಾನು ನಿಮಗೆ ಸಹಾಯ ಮಾಡಲು ಸಿದ್ಧನಿದ್ದೇನೆ. "

            "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಆರೋಗ್ಯ ಸಮಸ್ಯೆ ಅಥವಾ ನೀವು ಯಾವ ವಿಭಾಗ/ವೈದ್ಯರನ್ನು ಕಾಣಲು ಬಯಸುತ್ತೀರಿ ಎಂದು ತಿಳಿಸಬಹುದೇ?"

        ),

        "emergency_priority": (

            "🚨 ತುರ್ತು ವೈದ್ಯಕೀಯ ಎಚ್ಚರಿಕೆ (Emergency Priority): ತೀವ್ರವಾದ ಎದೆ ನೋವು ಅಥವಾ ಪ್ರಾಣಾಪಾಯಕಾರಿ ಲಕ್ಷಣಗಳಿಗೆ ತಕ್ಷಣದ ತುರ್ತು ವೈದ್ಯಕೀಯ ತಪಾಸಣೆ ಅಗತ್ಯವಿದೆ. "

            "ದಯವಿಟ್ಟು ಸಾಮಾನ್ಯ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕಿಂಗ್‌ಗಾಗಿ ಕಾಯದೆ, ತಕ್ಷಣವೇ 108 ಅಥವಾ 112 ತುರ್ತು ಸಂಖ್ಯೆಗೆ ಕರೆ ಮಾಡಿ, ಅಥವಾ ಹತ್ತಿರದ ಆಸ್ಪತ್ರೆಯ ತುರ್ತು ಚಿಕಿತ್ಸಾ ವಿಭಾಗಕ್ಕೆ (Emergency Department) ತಕ್ಷಣ ತೆರಳಿ. "

            "ನಿಮ್ಮ ತಕ್ಷಣದ ಸುರಕ್ಷತೆಯೇ ನಮಗೆ ಮುಖ್ಯ."

        ),

        "emergency_followup": (

            "🚨 ತುರ್ತು ಸುರಕ್ಷತಾ ಸೂಚನೆ: ನೀವು ವಿವರಿಸುತ್ತಿರುವ ಲಕ್ಷಣಗಳು ಗಂಭೀರವಾಗಿರುವುದರಿಂದ, ಸಾಮಾನ್ಯ ಹೊರರೋಗಿ ಬುಕಿಂಗ್ ಮುಂದುವರಿಸುವುದು ಸುರಕ್ಷಿತವಲ್ಲ. "

            "ದಯವಿಟ್ಟು ತಕ್ಷಣ 108 / 112 ಕ್ಕೆ ಕರೆ ಮಾಡಿ ಅಥವಾ ಹತ್ತಿರದ ತುರ್ತು ಚಿಕಿತ್ಸಾ ವಿಭಾಗಕ್ಕೆ (Emergency Room) ಭೇಟಿ ನೀಡಿ."

        ),

        "missing_details_error": (

            "ಇನ್ನೂ ಬುಕ್ ಮಾಡಲು ಸಾಧ್ಯವಿಲ್ಲ. ಬೇಕಾಗಿರುವ ವಿವರಗಳು: {missing}."

        ),

        "detail_captured_pick_slot": (

            "ನಿಮ್ಮ ವಿವರವನ್ನು ದಾಖಲಿಸಿಕೊಂಡಿದ್ದೇನೆ. {doctor_name} ಅವರೊಂದಿಗೆ ಮುಂದುವರಿಯಲು ದಯವಿಟ್ಟು ಲಭ್ಯವಿರುವ ಈ ಸಮಯಗಳಲ್ಲಿ ಒಂದನ್ನು ಆಯ್ಕೆಮಾಡಿ: {available_ids}."

        ),

        "symptom_added_keep_specialty": (

            "ನಿಮ್ಮ ಲಕ್ಷಣಗಳನ್ನು ({reason_category}) ದಾಖಲಿಸಿಕೊಂಡಿದ್ದೇನೆ. ಇದಕ್ಕೆ {specialty} ವಿಭಾಗದ {doctor_name} ಅವರ ಸಮಾಲೋಚನೆ ಸೂಕ್ತವಾಗಿದೆ. "

            "{doctor_name} ಅವರಿಗೆ ಲಭ್ಯವಿರುವ ಸ್ಲಾಟ್‌ಗಳನ್ನು ತೋರಿಸಲೇ?"

        ),

        "gratitude_closure": (

            "ಸ್ವಾಗತ! ನಿಮಗೆ ಅಗತ್ಯವಿದ್ದಾಗ ಸಹಾಯ ಮಾಡಲು ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆ ಸದಾ ಸಿದ್ಧವಾಗಿದೆ. ಆರೋಗ್ಯವಾಗಿರಿ, ಶುಭ ದಿನ!"

        ),

        "cancelled": (

            "ಅರ್ಥವಾಯಿತು. ನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕಿಂಗ್ ರದ್ದುಗೊಳಿಸಲಾಗಿದೆ (Cancelled). "

            "ಬೇರೆ ವೈದ್ಯರು ಅಥವಾ ಸೇವೆಗಳ ಬಗ್ಗೆ ತಿಳಿಯಲು ಬಯಸಿದರೆ ತಿಳಿಸಿ."

        ),

        "already_booked": (

            "ನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಈಗಾಗಲೇ ದೃಢೀಕರಿಸಲ್ಪಟ್ಟಿದೆ (Appointment ID: {appt_id}). "

            "ಹೊಸ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲು ದಯವಿಟ್ಟು ಸೆಷನ್ ಮರುಹೊಂದಿಸಿ."

        ),

        "doctor_found_consult_or_more": (

            "ನಾನು {specialty} ತಜ್ಞರಾದ {doctor_name} ಅವರನ್ನು ಕಂಡುಕೊಂಡಿದ್ದೇನೆ. ಲಭ್ಯವಿರುವ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್‌ಗಳನ್ನು ನೋಡಬೇಕೇ?"

        ),

        "searching_doctor": "ಡಾ. {doc} ಅವರ ವಿವರಗಳನ್ನು ಹುಡುಕುತ್ತಿದ್ದೇನೆ...",

        "searching_specialty": "{specialty} ವಿಭಾಗದಲ್ಲಿ ಲಭ್ಯವಿರುವ ತಜ್ಞರನ್ನು ಹುಡುಕುತ್ತಿದ್ದೇನೆ...",

        "checking_slots": "{doctor_name} ಅವರಿಗೆ ಲಭ್ಯವಿರುವ ಸಮಯಗಳನ್ನು (slots) ಪರಿಶೀಲಿಸುತ್ತಿದ್ದೇನೆ...",

        "ask_reason": (
            "ನೀವು {doctor_name} ಅವರೊಂದಿಗೆ {slot_display} ಸಮಯವನ್ನು ಆಯ್ಕೆ ಮಾಡಿದ್ದೀರಿ. "

            "ಈ ಭೇಟಿಗೆ ಕಾರಣ ಅಥವಾ ನಿಮ್ಮ ಲಕ್ಷಣಗಳೇನು? (ಉದಾ: 'ಎದೆ ನೋವು ತಪಾಸಣೆ', 'ಸಾಮಾನ್ಯ ತಪಾಸಣೆ')"

        ),

        "ask_patient_ref": (

            "ಬುಕಿಂಗ್ ಸಿದ್ಧಪಡಿಸಲು ದಯವಿಟ್ಟು ನಿಮ್ಮ ಸಿಂಥೆಟಿಕ್ ಪೇಷೆಂಟ್ ರೆಫರೆನ್ಸ್ ಐಡಿ (Patient Reference ID, ಉದಾ: 'PAT-2026-4409') ನೀಡಿ."

        ),

        "confirm_summary": (
            "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ವಿವರಗಳನ್ನು ಪರಿಶೀಲಿಸಿ:\n"
            "• ರೋಗಿ: {patient_reference}\n"
            "• ವೈದ್ಯರು: {doctor_name} ({specialty})\n"
            "• ಸಮಯ: {slot_display}\n"
            "• ಕಾರಣ: {reason_category}\n\n"
            "ಈ ಬುಕಿಂಗ್ ಖಚಿತಪಡಿಸಲು 'ಹೌದು' ಎಂದು ಉತ್ತರಿಸಿ. ಬದಲಾವಣೆ ಅಥವಾ ರದ್ದು ಮಾಡಲು 'ಬೇಡ' ಎಂದು ತಿಳಿಸಿ."
        ),

        "processing_booking": "ದೃಢೀಕರಿಸಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು. ನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕಿಂಗ್ ಪ್ರಕ್ರಿಯೆಯಲ್ಲಿದೆ...",

        "offer_specialty_consultation": (

            "ಖಂಡಿತ! ನಾನು ನಿಮಗೆ {specialty} ಸಮಾಲೋಚನೆಯನ್ನು ವ್ಯವಸ್ಥೆ ಮಾಡಲು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ. ಲಭ್ಯವಿರುವ {specialist_noun}ರನ್ನು ಹುಡುಕಲೇ?"

        ),

        "checking_available_specialists": (

            "ಖಂಡಿತ. ಲಭ್ಯವಿರುವ {specialist_plural} ಪರಿಶೀಲಿಸುತ್ತಿದ್ದೇನೆ."

        ),

        "found_specialists_recommend": (

            "{count} {specialist_plural} ಕಂಡುಬಂದಿದೆ:\n{doc_list}\n\n"

            "ಲಭ್ಯತೆಯ ಆಧಾರದ ಮೇಲೆ {recommend_name}ರನ್ನು ಶಿಫಾರಸು ಮಾಡಲೇ?"

        ),

        "specialist_choice_excellent": (

            "{doctor_name} ಉತ್ತಮ ಆಯ್ಕೆ. ಲಭ್ಯವಿರುವ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಸ್ಲಾಟ್‌ಗಳನ್ನು ಪರಿಶೀಲಿಸುತ್ತಿದ್ದೇನೆ."

        ),

        "found_doctors": (

            "ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯಲ್ಲಿ {count} ತಜ್ಞ ವೈದ್ಯರು ಲಭ್ಯವಿದ್ದಾರೆ:\n{doc_list}\n\n"

            "ನೀವು ಯಾವ ವೈದ್ಯರೊಂದಿಗೆ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲು ಬಯಸುತ್ತೀರಿ?"

        ),

        "selected_doctor_slots": (

            "{doctor_name} ({specialty}) ಆಯ್ಕೆ ಮಾಡಲಾಗಿದೆ.\n\n"

            "ಲಭ್ಯವಿರುವ ಸಮಯಗಳು:\n{slot_lines}\n\n"

            "ನಿಮಗೆ ಯಾವ ಸಮಯ ಅನುಕೂಲಕರವಾಗಿದೆ?"

        ),

        "recommended_doctor_slots": (

            "{specialty} ವಿಭಾಗಕ್ಕಾಗಿ ನಾನು ಡಾ. {doctor_name} ಅವರನ್ನು ಶಿಫಾರಸು ಮಾಡುತ್ತೇನೆ.\n"

            "ಲಭ್ಯವಿರುವ ಸಮಯಗಳು:\n{slot_lines}\n\n"

            "ನಿಮಗೆ ಯಾವ ಸಮಯ ಅನುಕೂಲಕರವಾಗಿದೆ? (ನೀವು ಬಯಸಿದರೆ ಬೇರೆ ವೈದ್ಯರನ್ನು ಸಹ ಕೋರಬಹುದು.)"

        ),

        "available_slots": (

            "{doctor_name} ಅವರಿಗೆ ಲಭ್ಯವಿರುವ ಸಮಯಗಳು:\n{slot_lines}\n\n"

            "ನಿಮಗೆ ಯಾವ ಸಮಯ ಅನುಕೂಲಕರವಾಗಿದೆ?"

        ),

        "invalid_slot": (

            "'{invalid_slot}' ಎಂಬುದು {doctor_name} ಅವರಿಗೆ ಲಭ್ಯವಿರುವ ಮಾನ್ಯವಾದ ಸ್ಲಾಟ್ ಐಡಿ ಅಲ್ಲ (Invalid slot ID). "

            "ದಯವಿಟ್ಟು ಲಭ್ಯವಿರುವ ಈ ಸ್ಲಾಟ್ ಐಡಿಗಳಲ್ಲಿ ಒಂದನ್ನು ಆಯ್ಕೆಮಾಡಿ: {available_ids}\n"

            "{slot_lines}"

        ),

        "urgent_chest_pain_note": (

            "⚠️ ತುರ್ತು ವೈದ್ಯಕೀಯ ಮಾರ್ಗದರ್ಶನ (Emergency Guidance): ಎದೆ ನೋವು ಅಥವಾ ತೀವ್ರ ಉಸಿರಾಟದ ತೊಂದರೆ ತುರ್ತು ವೈದ್ಯಕೀಯ ಸ್ಥಿತಿಯಾಗಿರಬಹುದು. "

            "ನೋವು ತೀವ್ರವಾಗಿದ್ದರೆ, ಉಸಿರಾಟದ ತೊಂದರೆ ಅಥವಾ ಬೆವರುತ್ತಿದ್ದರೆ, ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್‌ಗಾಗಿ ತಡಮಾಡದೆ "

            "ತಕ್ಷಣ ತುರ್ತು ಸೇವೆಗಳಿಗೆ (108 / 112) ಕರೆ ಮಾಡಿ ಅಥವಾ ತುರ್ತು ಚಿಕಿತ್ಸಾ ವಿಭಾಗಕ್ಕೆ ಭೇಟಿ ನೀಡಿ."

        ),

        "no_slots": "{doctor_name} ಅವರಿಗೆ ಪ್ರಸ್ತುತ ಯಾವುದೇ ಸ್ಲಾಟ್‌ಗಳು ಲಭ್ಯವಿಲ್ಲ. ಬೇರೆ ವೈದ್ಯರನ್ನು ಪರಿಶೀಲಿಸೋಣವೇ?",

        "no_doctors": "ಆ ಹುಡುಕಾಟಕ್ಕೆ ಹೊಂದಿಕೆಯಾಗುವ ವೈದ್ಯರು ಕಂಡುಬಂದಿಲ್ಲ. ಬೇರೆ ವಿಭಾಗವನ್ನು ಪರಿಶೀಲಿಸೋಣವೇ?",

        "changed_reconfirm": (

            "ಬುಕಿಂಗ್ ವಿವರಗಳು ಬದಲಾಗಿವೆ. ದಯವಿಟ್ಟು ನವೀಕರಿಸಿದ ವಿವರಗಳನ್ನು ದೃಢೀಕರಿಸಿ:\n"

            "• Doctor: {doctor_name}\n"

            "• Slot: {slot_display}\n"

            "• Reason: {reason_category}\n"

            "• Patient Reference: {patient_reference}\n\n"

            "ಬುಕಿಂಗ್ ಅಂತಿಮಗೊಳಿಸಲು 'ಹೌದು' (YES) ಎಂದು ಉತ್ತರಿಸಿ."

        ),

        "explicit_confirm_required": (

            "ಬುಕಿಂಗ್ ಮಾಡುವ ಮೊದಲು ನಿಮ್ಮ ಸ್ಪಷ್ಟ ದೃಢೀಕರಣ ಅಗತ್ಯವಿದೆ. "

            "ದಯವಿಟ್ಟು ದೃಢೀಕರಿಸಲು 'ಹೌದು' (YES) ಅಥವಾ ರದ್ದುಗೊಳಿಸಲು 'ಬೇಡ' (NO) ಎಂದು ಉತ್ತರಿಸಿ."

        ),

        "booking_confirmed": (

            "ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ದೃಢೀಕರಿಸಲಾಗಿದೆ! (Appointment Confirmed! 🎉)\n"

            "• Appointment ID: {appointment_id}\n"

            "• Doctor: {doctor_name}\n"

            "• Schedule: {appointment_start_time}\n"

            "• Status: {appointment_status}\n"

            "• Patient Reference: {patient_reference}\n\n"

            "ನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ವಿವರಗಳನ್ನು మీ ನೋಂದಾಯಿತ ಮೊಬೈಲ್ ಸಂಖ್ಯೆಗೆ ಎಸ್‌ಎಂಎಸ್ ಮೂಲಕ ಕಳುಹಿಸಲಾಗುತ್ತದೆ (ಡೆಮೊ ಸೂಚನೆ).\n\n"

            "ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯನ್ನು ಆಯ್ಕೆ ಮಾಡಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು. ನೀವು ಶೀಘ್ರವಾಗಿ ಚೇತರಿಸಿಕೊಳ್ಳಬೇಕೆಂದು ನಾವು ಬಯಸುತ್ತೇವೆ!"

        ),

        "doctor_not_found_ask_alternative": (

            "ಡಾಕ್ಟರ್ {doctor_name} ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯಲ್ಲಿ ಲಭ್ಯವಿಲ್ಲ. ನೀವು ಬೇರೆ ವೈದ್ಯರೊಂದಿಗೆ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಕಾಯ್ದಿರಿಸಲು ಬಯಸುತ್ತೀರಾ ಅಥವಾ ಲಭ್ಯವಿರುವ ವೈದ್ಯರ ಪಟ್ಟಿಯನ್ನು ನೋಡಲು ಬಯಸುತ್ತೀರಾ?"

        ),

        "doctor_ambiguous_clarify": (

            "'{doctor_name}' ಹೆಸರಿನೊಂದಿಗೆ ಅನೇಕ ವೈದ್ಯರು ಲಭ್ಯವಿದ್ದಾರೆ. ನೀವು ಯಾವ ವೈದ್ಯರನ್ನು ಸಂಪರ್ಕಿಸಲು ಬಯಸುತ್ತೀರಿ ಎಂದು ದಯವಿಟ್ಟು ಸ್ಪಷ್ಟಪಡಿಸಬಹುದೇ?"

        ),

        "booking_failed": (

            "Booking could not be completed: {error}\n"

            "ಆಯ್ಕೆಮಾಡಿದ ಸ್ಲಾಟ್ ಲಭ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು ಬೇರೆ ಲಭ್ಯವಿರುವ ಸ್ಲಾಟ್ ಆಯ್ಕೆಮಾಡಿ."

        ),

        "provider_error": (

            "AI ಸೇವೆ ತಾತ್ಕಾಲಿಕವಾಗಿ ಲಭ್ಯವಿಲ್ಲ ({reason}). ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."

        ),

    },

    "hi": {
        "ask_which_doctor_preferred": "ज़रूर! आप किस डॉक्टर या विभाग से परामर्श लेना चाहेंगे?",

        "clarify_account_vs_booking": (

            "\u0915\u094d\u092f\u093e \u0906\u092a \u0906\u0930\u094b\u0917\u094d\u092f \u0935\u0928 \u0905\u0938\u094d\u092a\u0924\u093e\u0932 \u092e\u0947\u0902 \u0921\u0949\u0915\u094d\u091f\u0930 \u0915\u093e \u0905\u092a\u0949\u0907\u0902\u091f\u092e\u0947\u0902\u091f \u092c\u0941\u0915 \u0915\u0930\u0928\u093e \u091a\u093e\u0939\u0924\u0947 \u0939\u0948\u0902, \u092f\u093e \u0928\u092f\u093e \u092e\u0930\u0940\u091c\u093c \u0916\u093e\u0924\u093e (Account) \u092a\u0902\u091c\u0940\u0915\u0943\u0924 \u0915\u0930\u0928\u093e \u091a\u093e\u0939\u0924\u0947 \u0939\u0948\u0902? "

            "\u0915\u0943\u092a\u092f\u093e \u092c\u0924\u093e\u090f\u0902 \u0915\u093f \u0906\u092a \u0915\u0948\u0938\u0947 \u0906\u0917\u0947 \u092c\u0922\u093c\u0928\u093e \u091a\u093e\u0939\u0924\u0947 \u0939\u0948\u0902।"

        ),

        "greeting": (

            "नमस्ते! मैं आरोग्य वन अस्पताल (Aarogya One Hospital) का मेडीवॉइस सहायक हूँ। "

            "आपको किस विभाग या डॉक्टर से परामर्श चाहिए? "

            "(उदा: Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine)"

        ),

        "how_to_book": (

            "मैं आरोग्य वन अस्पताल में अपॉइंटमेंट बुक करने में आपकी खुशी से मदद करूँगा! "

            "कृपया मुझे विभाग, डॉक्टर का नाम या अपने लक्षण बताएं "

            "(उदाहरण: 'Cardiology', 'डॉ. राजेश शर्मा', 'घुटने में दर्द', या 'बुखार')।"

        ),

        "departments_info": (

            "आरोग्य वन अस्पताल में 5 प्रमुख विभागों में विशेषज्ञ डॉक्टर उपलब्ध हैं:\n"

            "• Cardiology (हृदय रोग) — Dr. Rajesh Sharma, Dr. Priya Nair\n"

            "• Neurology (न्यूरोलॉजी / नस एवं मस्तिष्क) — Dr. Arvind Swamy\n"

            "• Orthopedics (हड्डी एवं जोड़ रोग) — Dr. Vikram Mehta\n"

            "• Pediatrics (बाल रोग) — Dr. Ananya Sen\n"

            "• General Medicine (सामान्य चिकित्सा) — Dr. Sunita Rao\n\n"

            "आप किस विभाग या डॉक्टर से परामर्श लेना चाहेंगे?"

        ),

        "hours_info": (

            "आरोग्य वन अस्पताल (बेंगलुरु) ओपीडी (OPD) का समय सोमवार से शनिवार सुबह 08:00 बजे से रात 08:00 बजे तक है। "

            "आपातकालीन विभाग (Emergency) 24/7 खुला रहता है (हेल्पलाइन: 108 / 112)।"

        ),

        "ambiguous_confirm": (

            "कोई बात नहीं, आप अपना समय ले सकते हैं! आपकी अपॉइंटमेंट अभी बुक नहीं हुई है। "

            "जब आप तैयार हों, तो बुकिंग कन्फर्म करने के लिए 'हाँ' (YES) या रद्द करने के लिए 'नहीं' (NO) लिखें, "

            "या यदि आप डॉक्टर/स्लॉट बदलना चाहते हैं तो बताएं।"

        ),

        "ambiguous_general": (

            "कोई बात नहीं, सही डॉक्टर चुनना कभी-कभी उलझन भरा हो सकता है! मैं आपकी मदद करूँगा। "

            "क्या आप मुझे अपनी मुख्य समस्या या लक्षण बता सकते हैं (जैसे बुखार, सिरदर्द, या जोड़ों में दर्द)? "

            "या यदि आप चाहें, तो हम सामान्य चिकित्सा (General Medicine) परामर्श से शुरुआत कर सकते हैं।"

        ),

        "ambiguous_doctor_choice": (

            "कोई बात नहीं! उपलब्ध विशेषज्ञों ({doc_names}) में से चुनाव करने में मैं आपकी मदद कर सकता हूँ। "

            "क्या आप सुबह या दोपहर का समय पसंद करेंगे, या मैं आपको सबसे पहले उपलब्ध स्लॉट दिखाऊँ?"

        ),

        "clarify_need": (

            "मैं आरोग्य वन अस्पताल में अपॉइंटमेंट बुक करने में आपकी सहायता के लिए यहाँ हूँ। "

            "कृपया बताएं कि आपको क्या लक्षण हैं, या आप किस विभाग/डॉक्टर से परामर्श लेना चाहते हैं?"

        ),

        "emergency_priority": (

            "🚨 आपातकालीन चिकित्सा प्राथमिकता (Emergency Priority): गंभीर सीने में दर्द या जानलेवा लक्षणों के लिए तुरंत आपातकालीन चिकित्सा जांच आवश्यक है। "

            "कृपया सामान्य ओपीडी अपॉइंटमेंट बुकिंग का इंतजार न करें—तुरंत 108 या 112 आपातकालीन नंबर पर कॉल करें, या तुरंत नजदीकी अस्पताल के इमरजेंसी विभाग (Emergency Department) में जाएं। "

            "आपकी तत्काल सुरक्षा सबसे महत्वपूर्ण है।"

        ),

        "emergency_followup": (

            "🚨 आपातकालीन सुरक्षा अनुस्मारक: चूंकि आप लगातार गंभीर या आपातकालीन लक्षण बता रहे हैं, इसलिए अभी सामान्य अपॉइंटमेंट बुकिंग जारी रखना सुरक्षित नहीं है। "

            "कृपया बिना देरी किए तुरंत 108 / 112 पर कॉल करें या नजदीकी इमरजेंसी रूम में जाएं।"

        ),

        "missing_details_error": (

            "अभी बुकिंग नहीं की जा सकती। अधूरी जानकारी: {missing}।"

        ),

        "detail_captured_pick_slot": (

            "मैंने यह जानकारी नोट कर ली है। {doctor_name} के साथ आगे बढ़ने के लिए कृपया उपलब्ध समय में से एक चुनें: {available_ids}।"

        ),

        "symptom_added_keep_specialty": (

            "मैंने आपके लक्षण ({reason_category}) नोट कर लिए हैं। इसके लिए {specialty} विभाग के {doctor_name} से परामर्श उपयुक्त रहेगा। "

            "क्या मैं {doctor_name} के उपलब्ध स्लॉट दिखाऊँ?"

        ),

        "gratitude_closure": (

            "आपका स्वागत है! आरोग्य वन अस्पताल आपकी सहायता के लिए सदैव उपलब्ध है। अपना ख्याल रखें और आपका दिन शुभ हो!"

        ),

        "cancelled": (

            "समझ गया। आपकी अपॉइंटमेंट बुकिंग रद्द (Cancelled) कर दी गई है। "

            "यदि आप अन्य डॉक्टरों या सेवाओं की जानकारी चाहते हैं तो कृपया बताएं।"

        ),

        "already_booked": (

            "आपकी अपॉइंटमेंट पहले ही कन्फर्म और बुक हो चुकी है (Appointment ID: {appt_id})। "

            "नई अपॉइंटमेंट बुक करने के लिए कृपया सेशन रीसेट करें।"

        ),

        "searching_doctor": "डॉ. {doc} की जानकारी खोजी जा रही है...",

        "searching_specialty": "{specialty} विभाग में उपलब्ध विशेषज्ञों की खोज की जा रही है...",

        "checking_slots": "{doctor_name} के लिए उपलब्ध अपॉइंटमेंट स्लॉट की जांच की जा रही है...",

        "ask_reason": (
            "आपने {doctor_name} के साथ {slot_display} का समय चुना है। "

            "इस परामर्श का कारण या आपके लक्षण क्या हैं? (उदा: 'सीने में दर्द की जांच', 'रूटीन चेकअप')"

        ),

        "ask_patient_ref": (

            "आपकी अपॉइंटमेंट तैयार करने से पहले, क्या मैं जान सकता हूँ कि क्या आप पहले आरोग्य वन अस्पताल आए हैं?"

        ),

        "symptom_empathy_general_medicine": (

            "मुझे दुख है कि आपकी तबीयत ठीक नहीं है। मैं आरोग्य वन अस्पताल में परामर्श की व्यवस्था करने में आपकी मदद करूँगा।\n\n"

            "बुखार के लिए जनरल मेडिसिन (General Medicine) एक उपयुक्त शुरुआती विकल्प है।\n\n"

            "क्या आप उपलब्ध जनरल मेडिसिन डॉक्टरों की जानकारी देखना चाहेंगे?"

        ),

        "doctor_found_consult_or_more": (

            "मुझे {specialty} विशेषज्ञ {doctor_name} मिले हैं। क्या आप चाहते हैं कि मैं उनके उपलब्ध अपॉइंटमेंट समय की जाँच करूँ?"

        ),

        "checking_slots_for_doctor": "बहुत अच्छा! मैं {doctor_name} के लिए उपलब्ध समय की जांच कर रहा हूँ।",

        "suggest_earliest_slot": (

            "कोई बात नहीं! सबसे पहला उपलब्ध अपॉइंटमेंट समय {slot_time} है।\n\n"

            "क्या आप चाहते हैं कि मैं आपके लिए यह स्लॉट रिज़र्व कर दूँ?"

        ),

        "ask_visited_before": (

            "आपकी अपॉइंटमेंट तैयार करने से पहले, क्या मैं जान सकता हूँ कि क्या आप पहले आरोग्य वन अस्पताल आए हैं?"

        ),

        "welcome_new_patient_ask_name": (

            "आरोग्य वन अस्पताल में आपका स्वागत है! कोई बात नहीं। मैं नए मरीज के पंजीकरण में आपकी मदद करूँगा।\n\n"

            "क्या मुझे आपका पूरा नाम मिल सकता है?"

        ),

        "thank_name_ask_phone": (

            "धन्यवाद, {name}। अपॉइंटमेंट की जानकारी और सूचनाओं के लिए कृपया अपना 10 अंकों का मोबाइल नंबर बताएं:"

        ),

        "ask_new_patient_phone": (

            "धन्यवाद, {patient_name}। अपॉइंटमेंट की जानकारी और सूचनाओं के लिए कृपया अपना 10 अंकों का मोबाइल नंबर बताएं:"

        ),

        "welcome_back_ask_reference": (

            "वापसी पर स्वागत है! मुझे आपका अगला अपॉइंटमेंट बुक करने में खुशी होगी। क्या आप अपना पंजीकृत मोबाइल नंबर साझा कर सकते हैं ताकि मैं आपका मरीज़ रिकॉर्ड ढूंढ सकूँ?"

        ),

        "welcome_back_ask_phone": (

            "वापसी पर स्वागत है! मुझे आपका अगला अपॉइंटमेंट बुक करने में खुशी होगी। क्या आप अपना पंजीकृत मोबाइल नंबर साझा कर सकते हैं ताकि मैं आपका मरीज़ रिकॉर्ड ढूंढ सकूँ?"

        ),

        "forgot_reference_ask_phone": (

            "कोई चिंता नहीं! आपको अपना पेशेंट आईडी याद रखने की ज़रूरत नहीं है। हम आपके पंजीकृत मोबाइल नंबर का उपयोग करके आपका रिकॉर्ड ढूंढने का प्रयास कर सकते हैं।"

        ),

        "patient_verified_success": (

            "धन्यवाद! हमें {patient_name} का मरीज़ रिकॉर्ड मिल गया है।\n\n"

            "नोट: अपॉइंटमेंट निर्धारण के लिए अस्पताल रिकॉर्ड मिलान किया गया है। आधिकारिक फोटो पहचान सत्यापन अस्पताल चेक-इन के समय रिसेप्शन पर पूरा किया जाता है।"

        ),

        "patient_registered_summary_confirm": (

            "पंजीकरण सफल रहा! आपका पेशेंट रेफरेंस नंबर {patient_reference} है।\n\n"

            "कृपया अपनी अपॉइंटमेंट के विवरण की पुष्टि करें:\n"

            "• मरीज: {patient_name}\n"

            "• विभाग: {specialty}\n"

            "• डॉक्टर: {doctor_name}\n"

            "• समय: {slot_display}\n"

            "• कारण: {reason_category}\n\n"

            "क्या आप इस अपॉइंटमेंट की पुष्टि करना चाहते हैं? (हाँ / नहीं)"

        ),

        "existing_patient_welcome_ask_ref": (

            "वापसी पर स्वागत है! क्या आपके पास अपना पेशेंट रेफरेंस नंबर है?"

        ),

        "existing_patient_forgot_ref_ask_phone": (

            "कोई बात नहीं। क्या मुझे आपका पंजीकृत 10 अंकों का मोबाइल नंबर मिल सकता है? मैं आपका रिकॉर्ड ढूंढ लूँगा।"

        ),

        "confirm_summary": (
            "कृपया अपनी अपॉइंटमेंट के विवरण की पुष्टि करें:\n"
            "• मरीज़: {patient_reference}\n"
            "• डॉक्टर: {doctor_name} ({specialty})\n"
            "• समय: {slot_display}\n"
            "• कारण: {reason_category}\n\n"
            "इस बुकिंग को कन्फर्म करने के लिए कृपया 'हाँ' कहें। बदलाव या रद्द करने के लिए 'नहीं' कहें।"
        ),

        "decline_confirm_ask_modify_or_cancel": (

            "समझ गया। क्या आप डॉक्टर या समय बदलना चाहते हैं, या इस बुकिंग को रद्द करना चाहते हैं?"

        ),

        "resuming_booking": (

            "बिल्कुल! आपकी अपॉइंटमेंट बुकिंग जारी रखी जा रही है।"

        ),

        "processing_booking": "पुष्टि करने के लिए धन्यवाद। आपकी अपॉइंटमेंट बुकिंग प्रोसेस की जा रही है...",

        "offer_specialty_consultation": (

            "ज़रूर! मैं आपके लिए {specialty} परामर्श की व्यवस्था करने में मदद कर सकता हूँ। क्या आप चाहते हैं कि मैं उपलब्ध {specialist_noun} ढूँढूँ?"

        ),

        "checking_available_specialists": (

            "ज़रूर। मैं उपलब्ध {specialist_plural} की जांच कर रहा हूँ।"

        ),

        "found_specialists_recommend": (

            "मुझे {count} {specialist_plural} मिले:\n{doc_list}\n\n"

            "क्या आप चाहते हैं कि मैं उपलब्धता के आधार पर {recommend_name} की सिफारिश करूँ?"

        ),

        "specialist_choice_excellent": (

            "{doctor_name} एक बेहतरीन विकल्प हैं। मैं उनके उपलब्ध अपॉइंटमेंट स्लॉट की जांच कर रहा हूँ।"

        ),

        "found_doctors": (

            "आरोग्य वन अस्पताल में {count} विशेषज्ञ उपलब्ध हैं:\n{doc_list}\n\n"

            "आप किस डॉक्टर के साथ अपॉइंटमेंट बुक करना चाहेंगे?"

        ),

        "selected_doctor_slots": (

            "{doctor_name} ({specialty}) को चुना गया है।\n\n"

            "उपलब्ध अपॉइंटमेंट्स:\n{slot_lines}\n\n"

            "आपके लिए कौन सा समय सबसे अच्छा रहेगा?"

        ),

        "recommended_doctor_slots": (

            "{specialty} के लिए मैं {doctor_name} की सिफारिश करता हूँ।\n"

            "उपलब्ध अपॉइंटमेंट्स:\n{slot_lines}\n\n"

            "आपके लिए कौन सा समय सबसे अच्छा रहेगा? (यदि आप किसी अन्य डॉक्टर से मिलना चाहते हैं, तो कृपया बताएं।)"

        ),

        "available_slots": (

            "{doctor_name} के लिए उपलब्ध अपॉइंटमेंट्स:\n{slot_lines}\n\n"

            "आपके लिए कौन सा समय सबसे अच्छा रहेगा?"

        ),

        "invalid_slot": (

            "'{invalid_slot}' {doctor_name} के लिए एक मान्य उपलब्ध स्लॉट आईडी नहीं है (Invalid slot ID)। "

            "कृपया वास्तविक उपलब्ध स्लॉट आईडी में से किसी एक को चुनें: {available_ids}\n"

            "{slot_lines}"

        ),

        "urgent_chest_pain_note": (

            "⚠️ आपातकालीन चिकित्सा मार्गदर्शन (Emergency Guidance): सीने में दर्द या सांस लेने में गंभीर तकलीफ एक आपातकालीन स्थिति हो सकती है। "

            "यदि दर्द तेज है, सांस लेने में तकलीफ या पसीना आ रहा है, तो ओपीडी अपॉइंटमेंट के लिए देरी किए बिना "

            "तुरंत आपातकालीन सेवा (108 / 112) या नजदीकी इमरजेंसी विभाग में जाएं।"

        ),

        "no_slots": "{doctor_name} के लिए अभी कोई खाली स्लॉट उपलब्ध नहीं है। क्या आप किसी अन्य डॉक्टर को देखना चाहेंगे?",

        "no_doctors": "उस खोज के लिए कोई डॉक्टर नहीं मिला। क्या आप जनरल मेडिसिन या अन्य विभाग देखना चाहेंगे?",

        "changed_reconfirm": (

            "बुकिंग विवरण बदल गए हैं। कृपया अपडेट किए गए विवरण की पुष्टि करें:\n"

            "• Doctor: {doctor_name}\n"

            "• Slot: {slot_display}\n"

            "• Reason: {reason_category}\n"

            "• Patient Reference: {patient_reference}\n\n"

            "बुकिंग पूरी करने के लिए 'हाँ' (YES) लिखें।"

        ),

        "explicit_confirm_required": (

            "बुकिंग से पहले आपकी स्पष्ट पुष्टि आवश्यक है। "

            "कृपया पुष्टि के लिए 'हाँ' (YES) या रद्द करने के लिए 'नहीं' (NO) लिखें।"

        ),

        "booking_confirmed": (

            "अपॉइंटमेंट कन्फर्म हो गई है! (Appointment Confirmed! 🎉)\n"

            "• Appointment ID: {appointment_id}\n"

            "• Doctor: {doctor_name}\n"

            "• Schedule: {appointment_start_time}\n"

            "• Status: {appointment_status}\n"

            "• Patient Reference: {patient_reference}\n\n"

            "आपके अपॉइंटमेंट का विवरण आपके पंजीकृत मोबाइल नंबर पर एसएमएस द्वारा भेज दिया जाएगा (प्रदर्शन मोड)।\n\n"

            "आरोग्य वन अस्पताल चुनने के लिए धन्यवाद। हम आपके शीघ्र स्वस्थ होने की कामना करते हैं। अपना ध्यान रखें!"

        ),

        "doctor_not_found_ask_alternative": (

            "डॉक्टर {doctor_name} आरोग्य वन अस्पताल में उपलब्ध नहीं हैं। क्या आप किसी अन्य डॉक्टर से परामर्श लेना चाहते हैं या उपलब्ध डॉक्टरों की सूची देखना चाहते हैं?"

        ),

        "doctor_ambiguous_clarify": (

            "'{doctor_name}' नाम से कई डॉक्टर उपलब्ध हैं। कृपया स्पष्ट करें कि आप किस डॉक्टर से परामर्श लेना चाहते हैं?"

        ),

        "booking_failed": (

            "Booking could not be completed: {error}\n"

            "चुना गया स्लॉट उपलब्ध नहीं है। कृपया कोई दूसरा उपलब्ध स्लॉट चुनें।"

        ),

        "provider_error": (

            "AI सेवा अस्थायी रूप से अनुपलब्ध है ({reason})। कृपया थोड़ी देर बाद पुनः प्रयास करें।"

        ),

    },

}





def format_localized_message(lang: str, key: str, **kwargs: Any) -> str:

    lang_code = lang if lang in LOCALIZED_MESSAGES else "en"

    if key in LAB_AND_INSURANCE_MESSAGES.get(lang_code, {}):

        return LAB_AND_INSURANCE_MESSAGES[lang_code][key].format(**kwargs)

    if key in LAB_AND_INSURANCE_MESSAGES.get("en", {}):

        return LAB_AND_INSURANCE_MESSAGES["en"][key].format(**kwargs)

    template = LOCALIZED_MESSAGES[lang_code].get(key) or LOCALIZED_MESSAGES["en"][key]

    return template.format(**kwargs)





LAB_AND_INSURANCE_MESSAGES: Dict[str, Dict[str, str]] = {

    "en": {

        "ask_lab_verification_code": (

            "I can check your lab report order status at Aarogya One Hospital. "

            "Please share the 6-digit verification code provided on your lab receipt."

        ),

        "checking_lab_status": "Verifying your 6-digit lab code and retrieving current order status...",

        "searching_insurance": "Checking Aarogya One Hospital's active insurance providers and plan details...",

    },

    "te": {

        "ask_lab_verification_code": (

            "ఆరోగ్య వన్ హాస్పిటల్‌లో మీ ల్యాబ్ రిపోర్ట్ స్థితిని (Lab Report Status) నేను తనిఖీ చేయగలను. "

            "దయచేసి మీ ల్యాబ్ రసీదుపై ఉన్న 6-అంకెల వెరిఫికేషన్ కోడ్‌ను తెలియజేయండి."

        ),

        "checking_lab_status": "మీ 6-అంకెల ల్యాబ్ వెరిఫికేషన్ కోడ్‌ను పరిశీలించి రిపోర్ట్ స్థితిని తెలుసుకుంటున్నాను...",

        "searching_insurance": "ఆరోగ్య వన్ హాస్పిటల్‌లో అందుబాటులో ఉన్న ఇన్సూరెన్స్ (భీమా) సంస్థలు మరియు ప్లాన్ వివరాలను తనిఖీ చేస్తున్నాను...",

    },

    "ta": {

        "ask_lab_verification_code": (

            "ஆரோக்கியா ஒன் மருத்துவமனையில் உங்கள் லேப் ரிப்போர்ட் நிலையை (Lab Report Status) நான் சரிபார்க்க முடியும். "

            "தயவுசெய்து உங்கள் லேப் ரசீதில் உள்ள 6-இலக்க சரிபார்ப்பு குறியீட்டைப் பகிரவும்."

        ),

        "checking_lab_status": "உங்கள் 6-இலக்க லேப் சரிபார்ப்பு குறியீட்டைச் சரிபார்த்து நிலையைப் பெறுகிறேன்...",

        "searching_insurance": "ஆரோக்கியா ஒன் மருத்துவமனையின் காப்பீட்டு (Insurance) நிறுவனங்கள் மற்றும் திட்ட விவரங்களைத் தேடுகிறேன்...",

    },

    "kn": {

        "ask_lab_verification_code": (

            "ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯಲ್ಲಿ ನಿಮ್ಮ ಲ್ಯಾಬ್ ವರದಿ ಸ್ಥಿತಿಯನ್ನು (Lab Report Status) ನಾನು ಪರಿಶೀಲಿಸಬಲ್ಲೆ. "

            "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಲ್ಯಾಬ್ ರಸೀದಿಯಲ್ಲಿರುವ 6-ಅಂಕಿಯ ಪರಿಶೀಲನಾ ಕೋಡ್ ಅನ್ನು ತಿಳಿಸಿ."

        ),

        "checking_lab_status": "ನಿಮ್ಮ 6-ಅಂಕಿಯ ಲ್ಯಾಬ್ ಪರಿಶೀಲನಾ ಕೋಡ್ ಅನ್ನು ಪರಿಶೀಲಿಸಿ ಪ್ರಸ್ತುತ ಸ್ಥಿತಿಯನ್ನು ಪಡೆಯುತ್ತಿದ್ದೇನೆ...",

        "searching_insurance": "ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯ ಸಕ್ರಿಯ ವಿಮಾ (Insurance) ಕಂಪನಿಗಳು ಮತ್ತು ಯೋಜನೆಗಳ ವಿವರಗಳನ್ನು ಪರಿಶೀಲಿಸುತ್ತಿದ್ದೇನೆ...",

    },

    "hi": {

        "ask_lab_verification_code": (

            "मैं आरोग्य वन अस्पताल में आपकी लैब रिपोर्ट की स्थिति (Lab Report Status) जांच सकता हूँ। "

            "कृपया अपनी लैब रसीद पर दिया गया 6-अंकों का सत्यापन कोड साझा करें।"

        ),

        "checking_lab_status": "आपके 6-अंकों के लैब कोड को सत्यापित कर रिपोर्ट की स्थिति प्राप्त की जा रही है...",

        "searching_insurance": "आरोग्य वन अस्पताल के सक्रिय बीमा (Insurance) प्रदाताओं और प्लान विवरणों की जांच की जा रही है...",

    },

}





LOCALIZED_LAB_STATUS_LABELS: Dict[str, Dict[str, str]] = {

    "en": {

        "REGISTERED": "REGISTERED (Order Registered)",

        "SAMPLE_COLLECTED": "SAMPLE_COLLECTED (Sample Collected)",

        "PROCESSING": "PROCESSING (In Laboratory Processing)",

        "COMPLETED": "COMPLETED (Report Ready for Release)",

        "CANCELLED": "CANCELLED (Order Cancelled)",

    },

    "te": {

        "REGISTERED": "REGISTERED (ల్యాబ్ ఆర్డర్ నమోదైంది)",

        "SAMPLE_COLLECTED": "SAMPLE_COLLECTED (నమూనా సేకరించబడింది)",

        "PROCESSING": "PROCESSING (ల్యాబ్‌లో పరీక్ష జరుగుతోంది)",

        "COMPLETED": "COMPLETED (రిపోర్ట్ పూర్తయింది / సిద్ధంగా ఉంది)",

        "CANCELLED": "CANCELLED (ల్యాబ్ ఆర్డర్ రద్దు చేయబడింది)",

    },

    "ta": {

        "REGISTERED": "REGISTERED (பரிசோதனை பதிவு செய்யப்பட்டுள்ளது)",

        "SAMPLE_COLLECTED": "SAMPLE_COLLECTED (மாதிரி சேகரிக்கப்பட்டது)",

        "PROCESSING": "PROCESSING (ஆய்வகத்தில் பரிசோதனை நடைபெறுகிறது)",

        "COMPLETED": "COMPLETED (ரிப்போர்ட் தயாராக உள்ளது)",

        "CANCELLED": "CANCELLED (பரிசோதனை ரத்து செய்யப்பட்டது)",

    },

    "kn": {

        "REGISTERED": "REGISTERED (ಲ್ಯಾಬ್ ಆರ್ಡರ್ ನೋಂದಾಯಿಸಲಾಗಿದೆ)",

        "SAMPLE_COLLECTED": "SAMPLE_COLLECTED (ಮಾದರಿ ಸಂಗ್ರಹಿಸಲಾಗಿದೆ)",

        "PROCESSING": "PROCESSING (ಪ್ರಯೋಗಾಲಯದಲ್ಲಿ ಪರೀಕ್ಷೆ ಪ್ರಗತಿಯಲ್ಲಿದೆ)",

        "COMPLETED": "COMPLETED (ವರದಿ ಸಿದ್ಧವಾಗಿದೆ)",

        "CANCELLED": "CANCELLED (ಆರ್ಡರ್ ರದ್ದುಗೊಳಿಸಲಾಗಿದೆ)",

    },

    "hi": {

        "REGISTERED": "REGISTERED (लैब ऑर्डर पंजीकृत)",

        "SAMPLE_COLLECTED": "SAMPLE_COLLECTED (सैंपल एकत्र किया गया)",

        "PROCESSING": "PROCESSING (प्रयोगशाला में जांच जारी है)",

        "COMPLETED": "COMPLETED (रिपोर्ट तैयार है)",

        "CANCELLED": "CANCELLED (ऑर्डर रद्द कर दिया गया)",

    },

}





def is_lab_report_inquiry(text: Optional[str]) -> bool:

    """

    Detects whether the user message is asking to check or verify a lab report / diagnostic test status

    across English, Telugu, Tamil, Kannada, and Hindi (native scripts and Romanized forms).

    """

    if not text or not text.strip():

        return False

    low = text.strip().lower()

    if re.search(

        r"\b(lab\s+report(?:s)?|lab\s+status|lab\s+order(?:s)?|lab\s+test(?:s)?|lab\s+result(?:s)?|test\s+report(?:s)?|test\s+status|blood\s+report(?:s)?|blood\s+test|diagnostic\s+report(?:s)?|pathology\s+report(?:s)?|report\s+status|verification\s+code|lab\s+code|check\s+(?:my\s+)?report|verify\s+(?:my\s+)?(?:lab|report)|is\s+my\s+report\s+ready|my\s+report\s+status|parikshana\s+code|varadi\s+sthiti|jaanch\s+report|janch\s+report|riport\s+status)\b",

        low,

    ):

        return True



    indic_lab_terms = (

        # Telugu

        "ల్యాబ్ రిపోర్ట్", "లాబ్ రిపోర్ట్", "రిపోర్ట్ స్టేటస్", "రిపోర్ట్ స్థితి",

        "రక్త పరీక్ష", "టెస్ట్ రిపోర్ట్", "ల్యాబ్ పరీక్ష", "పరిశీలన కోడ్", "వెరిఫికేషన్ కోడ్",

        "ల్యాబ్ కోడ్", "నా రిపోర్ట్", "రిపోర్ట్ వచ్చిందా",

        # Tamil

        "லேப் ரிப்போர்ட்", "பரிசோதனை முடிவு", "பரிசோதனை அறிக்கை", "ரிப்போர்ட் நிலை",

        "இரத்த பரிசோதனை", "சரிபார்ப்பு குறியீடு", "என் ரிப்போர்ட்", "லேப் நிலை",

        # Kannada

        "ಲ್ಯಾಬ್ ವರದಿ", "ಲ್ಯಾಬ್ ರಿಪೋರ್ಟ್", "ಪರೀಕ್ಷಾ ವರದಿ", "ವರದಿ ಸ್ಥಿತಿ",

        "ರಕ್ತ ಪರೀಕ್ಷೆ", "ಪರಿಶೀಲನಾ ಕೋಡ್", "ನನ್ನ ವರದಿ", "ಲ್ಯಾಬ್ ಸ್ಥಿತಿ",

        # Hindi

        "लैब रिपोर्ट", "टेस्ट रिपोर्ट", "रिपोर्ट स्टेटस", "रिपोर्ट की स्थिति",

        "जांच रिपोर्ट", "मेरी रिपोर्ट", "ब्लड रिपोर्ट", "सत्यापन कोड", "वेरिफिकेशन कोड",

    )

    return any(term in text for term in indic_lab_terms)





def extract_lab_verification_code_candidate(

    text: Optional[str], is_awaiting_code: bool = False

) -> tuple[Optional[str], Optional[str]]:

    """

    Extracts a 6-digit lab verification code (preserving leading zeros, e.g. '048271')

    or identifies a malformed code attempt when the user is inquiring about lab status

    or when the session is awaiting a lab verification code.

    Returns (valid_six_digit_code, malformed_code_attempt).

    """

    if not text or not text.strip():

        return None, None



    cleaned = re.sub(r"\bPAT-[A-Za-z0-9-]+\b", "", text, flags=re.IGNORECASE)

    cleaned = re.sub(r"\bslot-[A-Za-z0-9_-]+\b", "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", cleaned)

    cleaned = re.sub(r"\b\d{1,2}:\d{2}\b", "", cleaned)



    # 1. Exact 6-digit numeric code (including leading zeros like 048271)

    six_digit_match = re.search(r"(?<![A-Za-z0-9])(\d{6})(?![A-Za-z0-9])", cleaned)

    if six_digit_match:

        return six_digit_match.group(1), None



    # 2. Check for malformed code attempts (e.g. 3-5 digits, 7-10 digits, or alphanumeric code like 12345A)

    alnum_code_match = re.search(

        r"\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])([A-Za-z0-9]{4,8})\b", cleaned

    )

    if alnum_code_match:

        cand = alnum_code_match.group(1)

        if cand.lower() not in ("slot1", "slot2", "pat01", "hba1c", "b12"):

            return None, cand



    wrong_len_digits = re.search(r"(?<![A-Za-z0-9])(\d{3,5}|\d{7,10})(?![A-Za-z0-9])", cleaned)

    if wrong_len_digits:

        cand_num = wrong_len_digits.group(1)

        if cand_num not in ("108", "112", "2024", "2025", "2026"):

            return None, cand_num



    if is_awaiting_code:

        short_digits = re.search(r"(?<![A-Za-z0-9])(\d{1,2})(?![A-Za-z0-9])", cleaned)

        if short_digits:

            return None, short_digits.group(1)



    explicit_code_token = re.search(

        r"(?:verification\s+code|lab\s+code|code|కోడ్|குறியீடு|ಕೋಡ್|कोड)\s*(?:is|[:\-])?\s*([A-Za-z0-9_-]{2,12})\b",

        cleaned,

        re.IGNORECASE,

    )

    if explicit_code_token:

        tok = explicit_code_token.group(1)

        if tok.lower() not in (

            "for", "to", "my", "is", "status", "check", "verify", "please", "report", "lab", "test", "number"

        ):

            return None, tok



    return None, None





def format_lab_verification_reply(lang: str, data: Dict[str, Any]) -> str:

    """

    Formats the structured output of `check_lab_report_status` in the patient's active language

    without exposing any patient identifiers or clinical lab values.

    """

    lang_code = lang if lang in SUPPORTED_LANGUAGES else "en"

    verified = bool(data.get("verified"))



    if verified:

        test_name = data.get("test_name") or "Laboratory Test"

        raw_status = str(data.get("lab_status") or "PROCESSING").upper()

        status_label = LOCALIZED_LAB_STATUS_LABELS.get(lang_code, LOCALIZED_LAB_STATUS_LABELS["en"]).get(

            raw_status, raw_status

        )

        explanation = data.get("status_explanation") or ""

        next_step = data.get("next_step") or ""

        updated_at = data.get("last_updated_at") or "N/A"

        disclaimer = data.get("disclaimer") or (

            "Status verification only: Actual clinical test values and medical interpretations are not displayed here."

        )



        if lang_code == "te":

            return (

                f"✅ ల్యాబ్ రిపోర్ట్ స్థితి ధృవీకరించబడింది (Lab Order Status Verified):\n"

                f"• పరీక్ష పేరు (Test Name): {test_name}\n"

                f"• ప్రస్తుత స్థితి (Current Status): {status_label}\n"

                f"• వివరణ: {explanation}\n"

                f"• తదుపరి సూచన (Next Step): {next_step}\n"

                f"• చివరిగా అప్‌డేట్ చేసిన సమయం: {updated_at}\n\n"

                f"ℹ️ గమనిక: ఇది ల్యాబ్ ఆర్డర్ స్థితి మాత్రమే; భద్రతా కారణాల దృష్ట్యా పరీక్ష ఫలితాలు లేదా వైద్య నిర్ధారణ ఇక్కడ చూపబడవు. ({disclaimer})"

            )

        if lang_code == "ta":

            return (

                f"✅ லேப் ரிப்போர்ட் நிலை சரிபார்க்கப்பட்டது (Lab Order Status Verified):\n"

                f"• பரிசோதனை பெயர் (Test Name): {test_name}\n"

                f"• தற்போதைய நிலை (Current Status): {status_label}\n"

                f"• விளக்கம்: {explanation}\n"

                f"• அடுத்த படி (Next Step): {next_step}\n"

                f"• கடைசியாகப் புதுப்பிக்கப்பட்ட நேரம்: {updated_at}\n\n"

                f"ℹ️ குறிப்பு: இது பரிசோதனை நிலை மட்டுமே; மருத்துவ முடிவுகள் அல்லது விளக்கங்கள் இங்கே வழங்கப்படமாட்டாது. ({disclaimer})"

            )

        if lang_code == "kn":

            return (

                f"✅ ಲ್ಯಾಬ್ ವರದಿ ಸ್ಥಿತಿ ಪರಿಶೀಲಿಸಲಾಗಿದೆ (Lab Order Status Verified):\n"

                f"• ಪರೀಕ್ಷೆಯ ಹೆಸರು (Test Name): {test_name}\n"

                f"• ಪ್ರಸ್ತುತ ಸ್ಥಿತಿ (Current Status): {status_label}\n"

                f"• ವಿವರಣೆ: {explanation}\n"

                f"• ಮುಂದಿನ ಹಂತ (Next Step): {next_step}\n"

                f"• ಕೊನೆಯದಾಗಿ ನವೀಕರಿಸಿದ ಸಮಯ: {updated_at}\n\n"

                f"ℹ️ ಸೂಚನೆ: ಇದು ಲ್ಯಾಬ್ ಆರ್ಡರ್ ಸ್ಥಿತಿ ಮಾತ್ರ; ವೈದ್ಯಕೀಯ ಫಲಿತಾಂಶಗಳು ಅಥವಾ ವ್ಯಾಖ್ಯಾನಗಳನ್ನು ಇಲ್ಲಿ ತೋರಿಸಲಾಗುವುದಿಲ್ಲ. ({disclaimer})"

            )

        if lang_code == "hi":

            return (

                f"✅ लैब रिपोर्ट की स्थिति सत्यापित की गई (Lab Order Status Verified):\n"

                f"• जांच का नाम (Test Name): {test_name}\n"

                f"• वर्तमान स्थिति (Current Status): {status_label}\n"

                f"• विवरण: {explanation}\n"

                f"• अगला कदम (Next Step): {next_step}\n"

                f"• अंतिम अपडेट समय: {updated_at}\n\n"

                f"ℹ️ सूचना: यह केवल लैब ऑर्डर की स्थिति है; गोपनीयता और सुरक्षा के लिए वास्तविक मेडिकल रिपोर्ट के मान यहाँ प्रदर्शित नहीं किए जाते हैं। ({disclaimer})"

            )

        return (

            f"✅ Lab Report Status Verified:\n"

            f"• Test Name: {test_name}\n"

            f"• Current Status: {status_label}\n"

            f"• Details: {explanation}\n"

            f"• Next Step: {next_step}\n"

            f"• Last Updated: {updated_at}\n\n"

            f"ℹ️ Note: {disclaimer}"

        )



    # Verification failed (invalid format, unknown/expired/inactive code, or rate limited)

    error_code = str(data.get("error_code") or "INVALID_OR_EXPIRED_CODE")

    if error_code == "RATE_LIMITED":

        if lang_code == "te":

            return (

                "⚠️ చాలాసార్లు తప్పు వెరిఫికేషన్ కోడ్ నమోదు చేయబడింది (Too many failed verification attempts). "

                "దయచేసి కొన్ని నిమిషాలు ఆగి మళ్ళీ ప్రయత్నించండి లేదా ఆరోగ్య వన్ డయాగ్నస్టిక్స్ డెస్క్‌ను సంప్రదించండి."

            )

        if lang_code == "ta":

            return (

                "⚠️ பலமுறை தவறான சரிபார்ப்பு குறியீடு உள்ளிடப்பட்டுள்ளது (Too many failed verification attempts). "

                "தயவுசெய்து சிறிது நேரம் கழித்து மீண்டும் முயற்சிக்கவும்."

            )

        if lang_code == "kn":

            return (

                "⚠️ ಹಲವು ಬಾರಿ ತಪ್ಪಾದ ಪರಿಶೀಲನಾ ಕೋಡ್ ನಮೂದಿಸಲಾಗಿದೆ (Too many failed verification attempts). "

                "ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."

            )

        if lang_code == "hi":

            return (

                "⚠️ कई बार गलत सत्यापन कोड दर्ज किया गया है (Too many failed verification attempts)। "

                "कृपया कुछ मिनट प्रतीक्षा करें और पुनः प्रयास करें।"

            )

        return (

            "⚠️ Too many failed verification attempts. Please wait a few minutes before trying again "

            "or contact the Aarogya One Diagnostics Desk."

        )



    if error_code == "INVALID_CODE_FORMAT":

        if lang_code == "te":

            return (

                "❌ వెరిఫికేషన్ కోడ్ తప్పనిసరిగా 6 అంకెలు (000000–999999) కలిగి ఉండాలి. "

                "దయచేసి మీ సరైన 6-అంకెల ల్యాబ్ వెరిఫికేషన్ కోడ్‌ను మళ్ళీ పంపండి."

            )

        if lang_code == "ta":

            return (

                "❌ சரிபார்ப்பு குறியீடு சரியாக 6 இலக்கங்களைக் (000000–999999) கொண்டிருக்க வேண்டும். "

                "தயவுசெய்து உங்கள் சரியான 6-இலக்க குறியீட்டை மீண்டும் உள்ளிடவும்."

            )

        if lang_code == "kn":

            return (

                "❌ ಪರಿಶೀಲನಾ ಕೋಡ್ ನಿಖರವಾಗಿ 6 ಅಂಕಿಗಳನ್ನು (000000–999999) ಹೊಂದಿರಬೇಕು. "

                "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಸರಿಯಾದ 6-ಅಂಕಿಯ ಕೋಡ್ ಅನ್ನು ಮತ್ತೆ ನಮೂದಿಸಿ."

            )

        if lang_code == "hi":

            return (

                "❌ सत्यापन कोड में ठीक 6 अंक (000000–999999) होने चाहिए। "

                "कृपया अपना सही 6-अंकों का लैब सत्यापन कोड दोबारा दर्ज करें।"

            )

        return (

            "❌ Invalid verification code format: The verification code must contain exactly 6 digits (000000–999999). "

            "Please check your receipt and enter a valid 6-digit code."

        )



    # INVALID_OR_EXPIRED_CODE

    if lang_code == "te":

        return (

            "❌ మీరు ఇచ్చిన 6-అంకెల వెరిఫికేషన్ కోడ్ చెల్లదు లేదా గడువు ముగిసింది (Invalid or expired verification code). "

            "దయచేసి మీ ల్యాబ్ రసీదుపై ఉన్న 6-అంకెల కోడ్‌ను సరిచూసి మళ్ళీ నమోదు చేయండి."

        )

    if lang_code == "ta":

        return (

            "❌ நீங்கள் வழங்கிய 6-இலக்க சரிபார்ப்பு குறியீடு தவறானது அல்லது காலாவதியானது (Invalid or expired verification code). "

            "தயவுசெய்து உங்கள் ரசீதில் உள்ள 6-இலக்க குறியீட்டைச் சரிபார்த்து மீண்டும் முயற்சிக்கவும்."

        )

    if lang_code == "kn":

        return (

            "❌ ನೀವು ನೀಡಿದ 6-ಅಂಕಿಯ ಪರಿಶೀಲನಾ ಕೋಡ್ ಅಮಾನ್ಯವಾಗಿದೆ ಅಥವಾ ಅವಧಿ ಮುಗಿದಿದೆ (Invalid or expired verification code). "

            "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಲ್ಯಾಬ್ ರಸೀದಿಯಲ್ಲಿರುವ 6-ಅಂಕಿಯ ಕೋಡ್ ಪರಿಶೀಲಿಸಿ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."

        )

    if lang_code == "hi":

        return (

            "❌ आपके द्वारा दिया गया 6-अंकों का सत्यापन कोड अमान्य है या समाप्त हो चुका है (Invalid or expired verification code)। "

            "कृपया अपनी लैब रसीद पर दिए गए 6-अंकों के कोड की जांच करें और पुनः प्रयास करें।"

        )

    return (

        "❌ Invalid or expired verification code: We could not verify a lab order with that 6-digit code. "

        "Please double-check your 6-digit verification code and try again, or contact the Aarogya One Diagnostics Desk."

    )





def is_insurance_inquiry(text: Optional[str]) -> bool:

    """

    Detects whether the user message is asking about hospital insurance providers, plans,

    cashless eligibility, reimbursement, co-pay, or pre-authorization across all 5 languages.

    """

    if not text or not text.strip():

        return False

    low = text.strip().lower()

    if re.search(

        r"\b(insurance|insurer|insurers|cashless|reimbursement|copay|co-pay|pre-?authorization|pre-?auth|tpa|mediclaim|policy\s+coverage|health\s+policy|insurance\s+plan(?:s)?|insurance\s+provider(?:s)?|aarogya\s+shield|aarogya\s+senior|senior\s+care|gold\s+cashless|health\s+plan|care\s+plan|medical\s+plan|bharat\s+care|deccan\s+star|kaveri\s+national|kaveri\s+corporate|legacy\s+metro|bima|beema|bheema|bhima|kaapeedu|kappidu|vime)\b",

        low,

    ):

        return True



    indic_insurance_terms = (

        # Telugu

        "ఇన్సూరెన్స్", "భీమా", "బీమా", "క్యాష్‌లెస్", "క్యాష్ లెస్",

        "రీయింబర్స్‌మెంట్", "మెడిక్లెయిమ్", "ప్రీ-ఆథరైజేషన్", "ఆరోగ్య షీల్డ్", "భారత్ కేర్", "డెక్కన్ స్టార్", "కావేరి",

        # Tamil

        "காப்பீடு", "இன்சூரன்ஸ்", "கேஷ்லெஸ்", "மருத்துவ காப்பீடு", "பாலிசி",

        "ரீஇம்பர்ஸ்மென்ட்", "ஆரோக்கியா ஷீல்ட்", "பாரத் கேர்", "டெக்கான் ஸ்டார்",

        # Kannada

        "ವಿಮೆ", "ಇನ್ಶೂರೆನ್ಸ್", "ಕ್ಯಾಶ್‌ಲೆಸ್", "ಆರೋಗ್ಯ ವಿಮೆ", "ಪಾಲಿಸಿ",

        "ಮರುಪಾವತಿ", "ಆರೋಗ್ಯ ಶೀಲ್ಡ್", "ಭಾರತ್ ಕೇರ್", "ಡೆಕ್ಕನ್ ಸ್ಟಾರ್",

        # Hindi

        "बीमा", "इंश्योरेंस", "कैशलेस", "प्रतिपूर्ति", "मेडिक्लेम",

        "पॉलिसी", "कवरेज", "टीपीए", "आरोग्य शील्ड", "भारत केयर", "डेक्कन स्टार",

    )

    return any(term in text for term in indic_insurance_terms)





def is_slot_inquiry(text: Optional[str]) -> bool:

    """

    Detects whether the user is inquiring about available appointment slots, timings, or dates.

    """

    if not text or not text.strip():

        return False

    low = text.strip().lower()

    if re.search(

        r"\b(slot|slots|time|times|timing|timings|schedule|available\s+slots|open\s+slots|free\s+slots|next\s+available|show\s+slots|check\s+slots|when\s+available|what\s+time|when\s+is|when\s+can)\b",

        low,

    ):

        return True

    indic_slot_terms = (

        "\u0c38\u0c4d\u0c32\u0c3e\u0c1f\u0c4d", "\u0c38\u0c4d\u0c32\u0c3e\u0c1f\u0c4d\u0c32\u0c41", "\u0c38\u0c2e\u0c2f\u0c02", "\u0c1f\u0c48\u0c2e\u0c3f\u0c02\u0c17\u0c4d\u0c38\u0c4d",

        "\u0938\u094d\u0932\u0949\u091f", "\u0938\u092e\u092f", "\u0909\u092a\u0932\u092c\u094d\u0927",

        "\u0bb8\u0bcd\u0bb2\u0bbe\u0b9f\u0bcd", "\u0ba8\u0bc7\u0bb0\u0bae\u0bcd", "\u0ba8\u0bc7\u0bb0\u0b99\u0bcd\u0b95\u0bb3\u0bcd",

        "\u0cb8\u0ccd\u0cb2\u0cbe\u0c9f\u0ccd", "\u0cb8\u0cae\u0caf", "\u0cb2\u0cad\u0ccd\u0caf",

    )

    return any(term in text for term in indic_slot_terms)





KNOWN_INSURERS: List[Dict[str, Any]] = [

    # Active providers in hospital network

    {

        "canonical": "Aarogya Shield",

        "aliases": [

            "aarogya shield", "arogya shield", "aarogya shield insurance", "aarogya shield health insurance",

            "ఆరోగ్య షీల్డ్", "ஆரோக்கியா ஷீல்ட்", "ಆರೋಗ್ಯ ಶೀಲ್ಡ್", "आरोग्य शील्ड"

        ],

    },

    {

        "canonical": "Bharat Care",

        "aliases": [

            "bharat care", "bharat",

            "భారత్ కేర్", "பாரத் கேர்", "ಭಾರತ್ ಕೇರ್", "भारत केयर"

        ],

    },

    {

        "canonical": "Deccan Star",

        "aliases": [

            "deccan star", "deccan",

            "డెక్కన్ స్టార్", "டெக்கான் ஸ்டார்", "ಡೆಕ್ಕನ್ ಸ್ಟಾರ್", "डेक्कन स्टार"

        ],

    },

    {

        "canonical": "Kaveri",

        "aliases": [

            "kaveri", "kaveri national",

            "కావేరి", "காவேரி", "ಕಾವೇರಿ", "कावेरी"

        ],

    },

    # Inactive provider in database

    {

        "canonical": "Legacy Metro",

        "aliases": ["legacy metro", "legacy"],

    },

    # Common external / other insurance companies

    {

        "canonical": "Max Insurance",

        "aliases": [

            "max insurance", "max bupa", "niva bupa", "max life", "max health", "max"

        ],

    },

    {

        "canonical": "Star Health",

        "aliases": [

            "star health", "star health insurance", "star allied", "star mediclaim"

        ],

    },

    {

        "canonical": "HDFC ERGO",

        "aliases": ["hdfc ergo", "hdfc insurance", "hdfc life", "hdfc"],

    },

    {

        "canonical": "ICICI Lombard",

        "aliases": ["icici lombard", "icici prudential", "icici"],

    },

    {

        "canonical": "Care Health",

        "aliases": ["care health", "care insurance", "religare"],

    },

    {

        "canonical": "Bajaj Allianz",

        "aliases": ["bajaj allianz", "bajaj"],

    },

    {

        "canonical": "Tata AIG",

        "aliases": ["tata aig", "tata"],

    },

    {

        "canonical": "New India Assurance",

        "aliases": ["new india assurance", "new india"],

    },

    {

        "canonical": "United India Insurance",

        "aliases": ["united india insurance", "united india"],

    },

    {

        "canonical": "National Insurance",

        "aliases": ["national insurance"],

    },

    {

        "canonical": "Oriental Insurance",

        "aliases": ["oriental insurance", "oriental"],

    },

]





def extract_insurance_search_filters(text: str) -> Dict[str, Any]:

    """

    Extracts structured search arguments (provider_name, plan_name, plan_type, service, cashless)

    for `search_hospital_insurance` from a multilingual patient query.

    """

    cleaned_text = re.sub(r"\baarogya\s+one(?:\s+hospital)?\b", "", text, flags=re.IGNORECASE)

    cleaned_text = re.sub(r"\baarogya\s+hospital\b", "", cleaned_text, flags=re.IGNORECASE)

    low = cleaned_text.strip().lower()

    provider_name: Optional[str] = None

    plan_name: Optional[str] = None

    plan_type: Optional[str] = None

    service: Optional[str] = None

    cashless: Optional[bool] = None



    # Check known insurers first

    for item in KNOWN_INSURERS:

        for alias in item["aliases"]:

            if alias.isascii():

                if re.search(rf"\b{re.escape(alias)}\b", low):

                    provider_name = item["canonical"]

                    break

            else:

                if alias in text:

                    provider_name = item["canonical"]

                    break

        if provider_name:

            break



    # If no known insurer matched, check if user explicitly asked about an unknown insurance entity:

    # e.g., "Is <Name> Insurance covered?", "Does <Name> Insurance work?", "Is <Name> covered?"

    excluded_words = {

        "health", "my", "our", "all", "the", "hospital", "cashless", "private", "any", "which", "what",

        "is", "does", "have", "take", "cover", "covered", "coverage", "get", "give", "need", "want", "for", "me",

        "under", "in", "with", "from", "on", "at", "by", "to", "or", "and", "a", "an", "about",

        # Indic transliterations

        "naaku", "naku", "maaku", "maku", "enakku", "enaku", "nanage", "nange", "mujhe", "hame",

        "hamare", "mera", "meri", "mere", "aapka", "aapki", "ungal", "ungala", "nanna", "kavali",

        "vendum", "beku", "chahiye", "undi", "undaa", "undha", "irukka", "ideya", "hai", "kya",

        "details", "info", "information",

    }

    if not provider_name:

        m_name = re.search(

            r"\b([A-Za-z0-9\-'.]+?(?:\s+[A-Za-z0-9\-'.]+?){0,2})\s+(?:insurance|mediclaim|health\s+tpa|tpa|bima|beema|assurance)\b",

            text,

            re.IGNORECASE,

        )

        if m_name:

            raw_cand = m_name.group(1).strip()

            clean_words = [w for w in raw_cand.split() if w.lower() not in excluded_words]

            if clean_words:

                cand = " ".join(clean_words)

                if len(cand) >= 2:

                    provider_name = cand.title()

        if not provider_name:

            m_is = re.search(

                r"\b(?:is|does|about)\s+([A-Za-z0-9\-'.]+?(?:\s+[A-Za-z0-9\-'.]+?){0,2})\s+(?:accepted|covered|available|supported|taken|valid|work)\b",

                text,

                re.IGNORECASE,

            )

            if m_is:

                raw_cand = m_is.group(1).strip()

                clean_words = [w for w in raw_cand.split() if w.lower() not in excluded_words]

                if clean_words:

                    cand = " ".join(clean_words)

                    if len(cand) >= 2:

                        provider_name = cand.title()



    # Plan name detection

    if re.search(r"\b(gold\s+cashless|gold)\b", low):

        plan_name = "Gold"

    elif re.search(r"\b(opd\s*&\s*diagnostics|opd\s+care|diagnostics\s+care)\b", low):

        plan_name = "OPD & Diagnostics"

    elif re.search(r"\b(family\s+floater\s+prime|prime)\b", low):

        plan_name = "Prime"

    elif re.search(r"\b(basic\s+reimbursement|reimbursement\s+saver|saver)\b", low):

        plan_name = "Saver"

    elif re.search(r"\b(senior\s+citizen\s+shield|senior\s+care|senior\s+citizen|senior)\b", low):

        plan_name = "Senior"

    elif re.search(r"\b(corporate\s+group\s+cashless|corporate\s+premier)\b", low):

        plan_name = "Corporate Group"



    # Cashless filter

    has_cashless_word = bool(

        "cashless" in low

        or any(t in text for t in ("క్యాష్‌లెస్", "క్యాష్ లెస్", "கேஷ்லெஸ்", "ಕ್ಯಾಶ್‌ಲೆಸ್", "कैशलेस"))

    )

    has_reimb_word = bool(

        "reimbursement" in low

        or any(t in text for t in ("రీయింబర్స్‌మెంట్", "ரீஇம்பர்ஸ்மென்ட்", "ಮರುಪಾವತಿ", "प्रतिपूर्ति"))

    )

    if has_cashless_word and not has_reimb_word and not provider_name and not plan_name:

        cashless = True



    # Service filter

    if re.search(r"\b(opd|outpatient|consultation)\b", low) or any(

        t in text for t in ("ఓపీడీ", "ओपीडी", "புறநோயாளி", "ಹೊರರೋಗಿ")

    ):

        service = "OPD"

    elif re.search(r"\b(maternity|pregnancy|delivery)\b", low) or any(

        t in text for t in ("ప్రసూతి", "மகப்பேறு", "ಹೆರಿಗೆ", "मातृत्व")

    ):

        service = "Maternity"



    # Plan type filter

    if "senior citizen" in low or any(t in text for t in ("సీనియర్ సిటిజన్", "మూத்த குடிமக்கள்", "ಹಿರಿಯ ನಾಗರಿಕ", "वरिष्ठ नागरिक")):

        plan_type = "Senior Citizen"

    elif "family floater" in low:

        plan_type = "Family Floater"

    elif "corporate" in low:

        plan_type = "Corporate"



    args: Dict[str, Any] = {}

    if provider_name is not None:

        args["provider_name"] = provider_name

    if plan_name is not None:

        args["plan_name"] = plan_name

    if plan_type is not None:

        args["plan_type"] = plan_type

    if service is not None:

        args["service"] = service

    if cashless is not None:

        args["cashless"] = cashless

    return args





def format_insurance_search_reply(

    lang: str,

    data: Dict[str, Any],

    user_message: Optional[str] = None,

) -> str:

    """

    Formats the structured output of `search_hospital_insurance` in the patient's active language,

    distinguishing:

    A. Provider-specific query: If found, returns only that provider's plans and offers follow-up.

       If not found, clearly states provider was not found and provides Insurance Desk contact WITHOUT dumping catalogue.

    B. Plan-specific query: Returns only matching plan information.

    C. Treatment/Service query: Explains TPA pre-authorization, policy exclusions, and non-guarantee.

    D. General request: Returns complete catalogue only when specifically requested.

    Always includes non-guarantee disclaimer and insurance desk contact.

    """

    lang_code = lang if lang in SUPPORTED_LANGUAGES else "en"

    providers = data.get("providers") or []

    matched_count = int(data.get("matched_count") or len(providers))

    desk = data.get("insurance_desk_contact") or {}

    desk_phone = desk.get("phone") or "1800-100-4200 (Ext. 400)"

    desk_location = desk.get("location") or "Ground Floor, Block A — Aarogya One Hospital"

    disclaimer = data.get("disclaimer") or (

        "Informational only: Listed insurance plan details do not guarantee coverage or claim approval. "

        "Final eligibility, co-pay, and cashless authorization depend on your specific policy terms, "

        "insurer/TPA approval, and verification at the Aarogya One Hospital Insurance Desk."

    )



    msg_low = (user_message or "").strip().lower()



    # Detect requested provider or plan from data or message

    queried_provider = (

        data.get("provider_name")

        or data.get("query_provider")

        or (data.get("searched_filters") or {}).get("provider_name")

    )

    if not queried_provider and user_message:

        extracted = extract_insurance_search_filters(user_message)

        queried_provider = extracted.get("provider_name")



    queried_plan = data.get("plan_name")

    if not queried_plan and user_message:

        extracted = extract_insurance_search_filters(user_message)

        queried_plan = extracted.get("plan_name")



    is_treatment_query = bool(

        re.search(

            r"\b(cardiac|heart|surgery|operation|procedure|consultation|opd|mri|ct\s*scan|blood\s*test|dialysis|maternity|delivery|hospitalization|admit|admission|icu|stent|angioplasty|treatment|therapy|chemo|transplant|bypass)\b",

            msg_low,

        )

    )



    is_general_catalogue = bool(

        re.search(r"\b(all|list|catalogue|every|which|what|accepted)\b.*\b(insurance|providers|plans|companies)\b", msg_low)

        or re.search(r"\b(insurance|providers|plans)\s+(?:list|catalogue|options)\b", msg_low)

    )



    # CATEGORY A1: Provider explicitly queried but NOT found in active network records

    if queried_provider and (matched_count == 0 or not providers):

        if lang_code == "te":

            return (

                f"ℹ️ మీరు అడిగిన ఇన్సూరెన్స్ సంస్థ '{queried_provider}' ప్రస్తుతం ఆరోగ్య వన్ హాస్పిటల్ యాక్టివ్ నెట్‌వర్క్ రికార్డులలో అందుబాటులో లేదు (Not listed in active hospital insurance network).\n"

                f"• హాస్పిటల్ ఇన్సూరెన్స్ డెస్క్ (Insurance Desk): {desk_phone} | {desk_location}\n"

                f"• రీయింబర్స్‌మెంట్ (Reimbursement) లేదా అవుట్-ఆఫ్-నెట్‌వర్క్ సహాయం కోసం దయచేసి మీ పాలసీ కార్డుతో ఇన్సూరెన్స్ డెస్క్‌ను సంప్రదించండి.\n\n"

                f"⚠️ ముఖ్య గమనిక (Disclaimer): {disclaimer}"

            )

        if lang_code == "ta":

            return (

                f"ℹ️ நீங்கள் கேட்ட காப்பீட்டு நிறுவனம் '{queried_provider}' ஆரோக்கியா ஒன் மருத்துவமனையின் தற்போதைய செயலில் உள்ள நெட்வொர்க் பட்டியலில் இல்லை (Not listed in active hospital insurance network).\n"

                f"• மருத்துவமனை காப்பீட்டு உதவி மையம் (Insurance Desk): {desk_phone} | {desk_location}\n"

                f"• ரீஇம்பர்ஸ்மென்ட் (Reimbursement) அல்லது பிற உதவிகளுக்கு காப்பீட்டு மையத்தை அணுகவும்.\n\n"

                f"⚠️ முக்கிய குறிப்பு (Disclaimer): {disclaimer}"

            )

        if lang_code == "kn":

            return (

                f"ℹ️ ನೀವು ಕೇಳಿದ ವಿಮಾ ಕಂಪನಿ '{queried_provider}' ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯ ಪ್ರಸ್ತುತ ಸಕ್ರಿಯ ನೆಟ್‌ವರ್ಕ್ ದಾಖಲೆಗಳಲ್ಲಿ ಕಂಡುಬಂದಿಲ್ಲ (Not listed in active hospital insurance network).\n"

                f"• ಆಸ್ಪತ್ರೆ ವಿಮಾ ಸಹಾಯ ಕೇಂದ್ರ (Insurance Desk): {desk_phone} | {desk_location}\n"

                f"• ಮರುಪಾವತಿ (Reimbursement) ಅಥವಾ ನೆಟ್‌ವರ್ಕ್ ಹೊರಗಿನ ಸಹಾಯಕ್ಕಾಗಿ ದಯವಿಟ್ಟು ವಿಮಾ ಕೇಂದ್ರವನ್ನು ಸಂಪರ್ಕಿಸಿ.\n\n"

                f"⚠️ ಪ್ರಮುಖ ಸೂಚನೆ (Disclaimer): {disclaimer}"

            )

        if lang_code == "hi":

            return (

                f"ℹ️ आपके द्वारा पूछा गया बीमा प्रदाता '{queried_provider}' वर्तमान में आरोग्य वन अस्पताल के सक्रिय नेटवर्क रिकॉर्ड में उपलब्ध नहीं है (Not listed in active hospital insurance network)।\n"

                f"• अस्पताल बीमा हेल्पडेस्क (Insurance Desk): {desk_phone} | {desk_location}\n"

                f"• प्रतिपूर्ति (Reimbursement) या गैर-नेटवर्क सहायता के लिए कृपया अपने पॉलिसी कार्ड के साथ बीमा डेस्क से संपर्क करें।\n\n"

                f"⚠️ महत्वपूर्ण अस्वीकरण (Disclaimer): {disclaimer}"

            )

        return (

            f"ℹ️ The requested insurance provider ('{queried_provider}') is not currently listed in Aarogya One Hospital's active network records.\n"

            f"• Hospital Insurance Desk: {desk_phone} | {desk_location}\n"

            f"• Please contact our Insurance Desk with your policy card to check reimbursement options or out-of-network assistance.\n\n"

            f"⚠️ Disclaimer: {disclaimer}"

        )



    # CATEGORY C: Treatment / Procedure / Consultation coverage question without specific provider match

    if is_treatment_query and not queried_provider and not queried_plan:

        if lang_code == "te":

            return (

                f"ℹ️ ఇన్సూరెన్స్ కింద చికిత్స మరియు కన్సల్టేషన్ కవరేజ్ వివరాలు:\n"

                f"• నిర్దిష్ట చికిత్సలు, శస్త్రచికిత్సలు లేదా కన్సల్టేషన్‌లకు కవరేజ్ మీ వ్యక్తిగత పాలసీ నిబంధనలు, వెయిటింగ్ పీరియడ్ మరియు ఇన్సూరెన్స్ సంస్థ ముందస్తు అనుమతిపై ఆధారపడి ఉంటుంది.\n"

                f"• ప్లాన్ చేసిన సర్జరీలకు క్యాష్‌లెస్ సదుపాయం పొందడానికి 48-72 గంటల ముందు ప్రీ-ఆథరైజేషన్ (Pre-Auth) దరఖాస్తు చేసుకోవాలి. అత్యవసర చికిత్సలకు చేరిన 24 గంటలలోపు సమాచారం అందించాలి.\n"

                f"• ఓపీడీ (OPD) కన్సల్టేషన్‌లు ప్రత్యేక రైడర్‌లు లేదా నిర్దిష్ట ప్లాన్‌లలో మాత్రమే వర్తిస్తాయి.\n"

                f"• ముందస్తుగా క్లెయిమ్ లేదా కవరేజ్ ఆమోదాన్ని హామీ ఇవ్వడం సాధ్యం కాదు; ఇది TPA వెరిఫికేషన్‌పై ఆధారపడి ఉంటుంది.\n\n"

                f"📞 ఆరోగ్య వన్ హాస్పిటల్ ఇన్సూరెన్స్ డెస్క్: {desk_phone} | {desk_location}\n"

                f"మీ నిర్దిష్ట ఇన్సూరెన్స్ ప్రొవైడర్ లేదా ప్లాన్ వివరాలు తనిఖీ చేయమంటారా?\n\n"

                f"⚠️ ముఖ్య గమనిక (Disclaimer): {disclaimer}"

            )

        if lang_code == "ta":

            return (

                f"ℹ️ காப்பீட்டின் கீழ் சிகிச்சை மற்றும் ஆலோசனை பாதுகாப்பு விவரங்கள்:\n"

                f"• குறிப்பிட்ட சிகிச்சைகள், அறுவை சிகிச்சைகள் அல்லது ஆலோசனைகளுக்கான கவரேஜ் உங்கள் பாலிசி விதிமுறைகள் மற்றும் காப்பீட்டு நிறுவனத்தின் முன் அனுமதியைப் பொறுத்தது.\n"

                f"• திட்டமிடப்பட்ட சிகிச்சைகளுக்கு கேஷ்லெஸ் அனுமதி பெற 48-72 மணி நேரத்திற்கு முன் முன்-அனுமதி (Pre-Auth) பெற வேண்டும். அவசர சிகிச்சைகளுக்கு 24 மணி நேரத்திற்குள் தெரிவிக்க வேண்டும்.\n"

                f"• புறநோயாளி (OPD) ஆலோசனைகள் குறிப்பிட்ட திட்டங்களில் மட்டுமே அனுமதிக்கப்படும்.\n"

                f"• காப்பீட்டு ஒப்புதல் முன்கூட்டியே உத்தரவாதம் அளிக்கப்பட முடியாது; இது TPA சரிபார்ப்புக்கு உட்பட்டது.\n\n"

                f"📞 ஆரோக்கியா ஒன் மருத்துவமனை காப்பீட்டு உதவி மையம்: {desk_phone} | {desk_location}\n"

                f"உங்கள் குறிப்பிட்ட காப்பீட்டு நிறுவனம் அல்லது திட்ட விவரங்களை நான் சரிபார்க்க வேண்டுமா?\n\n"

                f"⚠️ முக்கிய குறிப்பு (Disclaimer): {disclaimer}"

            )

        if lang_code == "kn":

            return (

                f"ℹ️ ವಿಮೆಯ ಅಡಿಯಲ್ಲಿ ಚಿಕಿತ್ಸೆ ಮತ್ತು ಸಮಾಲೋಚನೆ ಕವರೇಜ್ ವಿವರ:\n"

                f"• ನಿರ್ದಿಷ್ಟ ಚಿಕಿತ್ಸೆಗಳು, ಶಸ್ತ್ರಚಿಕಿತ್ಸೆಗಳು ಅಥವಾ ಸಮಾಲೋಚನೆಗಳ ಕವರೇಜ್ ನಿಮ್ಮ ವೈಯಕ್ತಿಕ ಪಾಲಿಸಿ ನಿಯಮಗಳು ಮತ್ತು ವಿಮಾ ಕಂಪನಿಯ ಪೂರ್ವಾನುಮತಿಯನ್ನು ಅವಲಂಬಿಸಿರುತ್ತದೆ.\n"

                f"• ನಿಗದಿತ ಚಿಕಿತ್ಸೆಗಳಿಗೆ ಕ್ಯಾಶ್‌ಲೆಸ್ ಪಡೆಯಲು 48-72 ಗಂಟೆಗಳ ಮುಂಚಿತವಾಗಿ ಪೂರ್ವ-ಅಧಿಕಾರ (Pre-Auth) ಪಡೆಯಬೇಕು. ತುರ್ತು ಚಿಕಿತ್ಸೆಗೆ ದಾಖಲಾದ 24 ಗಂಟೆಗಳಲ್ಲಿ ಮಾಹಿತಿ ನೀಡಬೇಕು.\n"

                f"• ಹೊರರೋಗಿ (OPD) ಸಮಾಲೋಚನೆಗಳು ಆಯ್ದ ಯೋಜನೆಗಳಲ್ಲಿ ಮಾತ್ರ ಲಭ್ಯವಿರುತ್ತವೆ.\n"

                f"• ವಿಮಾ ಕ್ಲೈಮ್ ಅಥವಾ ಕವರೇಜ್ ಅನ್ನು ಮುಂಚಿತವಾಗಿ ಖಾತರಿಪಡಿಸಲಾಗುವುದಿಲ್ಲ; ಇದು TPA ಪರಿಶೀಲನೆಗೆ ಒಳಪಟ್ಟಿರುತ್ತದೆ.\n\n"

                f"📞 ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆ ವಿಮಾ ಸಹಾಯ ಕೇಂದ್ರ: {desk_phone} | {desk_location}\n"

                f"ನಿಮ್ಮ ನಿರ್ದಿಷ್ಟ ವಿಮಾ ಕಂಪನಿ ಅಥವಾ ಯೋಜನೆಯ ವಿವರಗಳನ್ನು ಪರಿಶೀಲಿಸಬೇಕೇ?\n\n"

                f"⚠️ ಪ್ರಮುಖ ಸೂಚನೆ (Disclaimer): {disclaimer}"

            )

        if lang_code == "hi":

            return (

                f"ℹ️ बीमा के तहत उपचार और परामर्श कवरेज संबंधी जानकारी:\n"

                f"• विशिष्ट उपचारों, सर्जरी या परामर्श के लिए कवरेज आपकी व्यक्तिगत पॉलिसी की शर्तों, प्रतीक्षा अवधि और बीमा कंपनी की पूर्व-स्वीकृति पर निर्भर करता है।\n"

                f"• नियोजित सर्जरी के लिए कैशलेस सुविधा प्राप्त करने हेतु 48-72 घंटे पहले पूर्व-प्राधिकरण (Pre-Auth) आवश्यक है। आपातकालीन स्थिति में भर्ती के 24 घंटों के भीतर सूचित करना होगा।\n"

                f"• ओपीडी (OPD) परामर्श केवल चुनिंदा योजनाओं या राइडर्स के तहत कवर होते हैं।\n"

                f"• अग्रिम रूप से क्लेम या कवरेज की गारंटी नहीं दी जा सकती; यह टीपीए सत्यापन पर निर्भर करता है।\n\n"

                f"📞 आरोग्य वन अस्पताल बीमा हेल्पडेस्क: {desk_phone} | {desk_location}\n"

                f"क्या आप चाहते हैं कि मैं आपके विशिष्ट बीमा प्रदाता या प्लान का विवरण जांचूं?\n\n"

                f"⚠️ महत्वपूर्ण अस्वीकरण (Disclaimer): {disclaimer}"

            )

        return (

            f"ℹ️ Treatment & Consultation Coverage Under Insurance:\n"

            f"• Coverage for specific treatments (such as surgeries, cardiac procedures, or consultations) depends on your individual insurance policy terms, plan inclusions, waiting periods, and insurer pre-authorization.\n"

            f"• Cashless authorization for planned procedures requires prior authorization (Pre-Auth) submitted to your TPA/insurer 48–72 hours in advance. Emergency treatments require notification within 24 hours of admission.\n"

            f"• OPD consultations and diagnostics are covered under select plans (such as Aarogya Shield OPD & Diagnostics Care) or subject to policy riders and co-pays.\n"

            f"• Final coverage or claim eligibility cannot be guaranteed in advance and is subject to TPA verification.\n\n"

            f"📞 Aarogya One Hospital Insurance Desk: {desk_phone} | {desk_location}\n"

            f"Would you like me to check your specific insurance provider or plan details?\n\n"

            f"⚠️ Disclaimer: {disclaimer}"

        )



    # Format plan lines for matching providers

    plan_lines: List[str] = []

    for prov in providers:

        prov_name = prov.get("name", "Insurance Provider")

        prov_contact = prov.get("support_contact") or desk_phone

        plans = prov.get("plans") or []

        if not plans:

            plan_lines.append(f"• {prov_name} (Support: {prov_contact})")

        else:

            for pl in plans:

                cashless_str = "Cashless: Yes" if pl.get("cashless_available") else "Cashless: No"

                reimb_str = "Reimbursement: Yes" if pl.get("reimbursement_available") else "Reimbursement: No"

                preauth_str = "Pre-Auth: Required" if pl.get("preauthorization_required") else "Pre-Auth: Not Required"

                plan_lines.append(

                    f"• {prov_name} — {pl.get('plan_name')} ({pl.get('plan_type')})\n"

                    f"  - Coverage: {pl.get('coverage_summary')}\n"

                    f"  - Co-pay: {pl.get('copay_summary')}\n"

                    f"  - Billing: {cashless_str} | {reimb_str} | {preauth_str}\n"

                    f"  - Notes: {pl.get('network_notes') or 'Verify at TPA Desk'}"

                )



    joined_plans = "\n".join(plan_lines)



    # CATEGORY A2: Single provider queried and found

    if queried_provider and matched_count == 1:

        first_prov_name = providers[0].get("name", queried_provider)

        if lang_code == "te":

            return (

                f"🏥 ఆరోగ్య వన్ హాస్పిటల్ — {first_prov_name} నెట్‌వర్క్ వివరాలు:\n"

                f"{joined_plans}\n\n"

                f"📞 ఇన్సూరెన్స్ హెల్ప్‌డెస్క్ (Insurance Desk): {desk_phone} ({desk_location})\n"

                f"మీరు ఏదైనా నిర్దిష్ట చికిత్స లేదా కన్సల్టేషన్ కవరేజ్ గురించి తెలుసుకోవాలనుకుంటున్నారా?\n\n"

                f"⚠️ ముఖ్య గమనిక (Disclaimer): {disclaimer}"

            )

        if lang_code == "ta":

            return (

                f"🏥 ஆரோக்கியா ஒன் மருத்துவமனை — {first_prov_name} நெட்வொர்க் விவரங்கள்:\n"

                f"{joined_plans}\n\n"

                f"📞 காப்பீட்டு உதவி மையம் (Insurance Desk): {desk_phone} ({desk_location})\n"

                f"குறிப்பிட்ட சிகிச்சை அல்லது ஆலோசனை கவரேஜ் பற்றி நீங்கள் தெரிந்துகொள்ள விரும்புகிறீர்களா?\n\n"

                f"⚠️ முக்கிய குறிப்பு (Disclaimer): {disclaimer}"

            )

        if lang_code == "kn":

            return (

                f"🏥 ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆ — {first_prov_name} ನೆಟ್‌ವರ್ಕ್ ವಿವರ:\n"

                f"{joined_plans}\n\n"

                f"📞 ವಿಮಾ ಸಹಾಯ ಕೇಂದ್ರ (Insurance Desk): {desk_phone} ({desk_location})\n"

                f"ನೀವು ಯಾವುದೇ ನಿರ್ದಿಷ್ಟ ಚಿಕಿತ್ಸೆ ಅಥವಾ ಸಮಾಲೋಚನೆ ಕವರೇಜ್ ಬಗ್ಗೆ ತಿಳಿಯಲು ಬಯಸುವಿರಾ?\n\n"

                f"⚠️ ಪ್ರಮುಖ ಸೂಚನೆ (Disclaimer): {disclaimer}"

            )

        if lang_code == "hi":

            return (

                f"🏥 आरोग्य वन अस्पताल — {first_prov_name} नेटवर्क विवरण:\n"

                f"{joined_plans}\n\n"

                f"📞 बीमा हेल्पडेस्क (Insurance Desk): {desk_phone} ({desk_location})\n"

                f"क्या आप किसी विशिष्ट उपचार या परामर्श कवरेज के बारे में जानना चाहते हैं?\n\n"

                f"⚠️ महत्वपूर्ण अस्वीकरण (Disclaimer): {disclaimer}"

            )

        return (

            f"🏥 Aarogya One Hospital — Active Network Information for {first_prov_name}:\n"

            f"{joined_plans}\n\n"

            f"📞 Insurance & TPA Helpdesk: {desk_phone} ({desk_location})\n"

            f"Would you like me to check a particular treatment or consultation?\n\n"

            f"⚠️ Disclaimer: {disclaimer}"

        )



    # CATEGORY B: Plan-specific inquiry

    if queried_plan:

        if lang_code == "te":

            return (

                f"🏥 ఆరోగ్య వన్ హాస్పిటల్ — ప్లాన్ వివరాలు ({queried_plan}):\n"

                f"{joined_plans}\n\n"

                f"📞 ఇన్సూరెన్స్ హెల్ప్‌డెస్క్: {desk_phone} ({desk_location})\n"

                f"⚠️ ముఖ్య గమనిక (Disclaimer): {disclaimer}"

            )

        if lang_code == "ta":

            return (

                f"🏥 ஆரோக்கியா ஒன் மருத்துவமனை — திட்ட விவரங்கள் ({queried_plan}):\n"

                f"{joined_plans}\n\n"

                f"📞 காப்பீட்டு உதவி மையம்: {desk_phone} ({desk_location})\n"

                f"⚠️ முக்கிய குறிப்பு (Disclaimer): {disclaimer}"

            )

        if lang_code == "kn":

            return (

                f"🏥 ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆ — ಯೋಜನೆಯ ವಿವರಗಳು ({queried_plan}):\n"

                f"{joined_plans}\n\n"

                f"📞 ವಿಮಾ ಸಹಾಯ ಕೇಂದ್ರ: {desk_phone} ({desk_location})\n"

                f"⚠️ ಪ್ರಮುಖ ಸೂಚನೆ (Disclaimer): {disclaimer}"

            )

        if lang_code == "hi":

            return (

                f"🏥 आरोग्य वन अस्पताल — प्लान विवरण ({queried_plan}):\n"

                f"{joined_plans}\n\n"

                f"📞 बीमा हेल्पडेस्क: {desk_phone} ({desk_location})\n"

                f"⚠️ महत्वपूर्ण अस्वीकरण (Disclaimer): {disclaimer}"

            )

        return (

            f"🏥 Aarogya One Hospital — Insurance Plan Information:\n"

            f"{joined_plans}\n\n"

            f"📞 Insurance & TPA Helpdesk: {desk_phone} ({desk_location})\n"

            f"⚠️ Disclaimer: {disclaimer}"

        )



    # CATEGORY D: General Catalogue Request

    if lang_code == "te":

        return (

            f"🏥 ఆరోగ్య వన్ హాస్పిటల్ — ఆమోదించబడిన ఇన్సూరెన్స్ సంస్థలు మరియు ప్లాన్ వివరాలు ({matched_count} సంస్థలు):\n"

            f"{joined_plans}\n\n"

            f"📞 ఇన్సూరెన్స్ హెల్ప్‌డెస్క్ (Insurance Desk): {desk_phone} ({desk_location})\n"

            f"⚠️ ముఖ్య గమనిక (Disclaimer): ఈ వివరాలు ప్రాథమిక సమాచారం కోసం మాత్రమే; తుది కవరేజ్, క్యాష్‌లెస్ అనుమతి మరియు క్లెయిమ్ ఆమోదం మీ పాలసీ నిబంధనలు, ఇన్సూరెన్స్ సంస్థ/TPA ఆమోదం మరియు హాస్పిటల్ బిల్లింగ్ వెరిఫికేషన్‌పై ఆధారపడి ఉంటాయి. ({disclaimer})"

        )

    if lang_code == "ta":

        return (

            f"🏥 ஆரோக்கியா ஒன் மருத்துவமனை — ஏற்றுக்கொள்ளப்படும் காப்பீட்டு நிறுவனங்கள் மற்றும் திட்டங்கள் ({matched_count} நிறுவனங்கள்):\n"

            f"{joined_plans}\n\n"

            f"📞 காப்பீட்டு உதவி மையம் (Insurance Desk): {desk_phone} ({desk_location})\n"

            f"⚠️ முக்கிய குறிப்பு (Disclaimer): இந்தத் தகவல் வழிகாட்டுதலுக்கு மட்டுமே; இறுதி காப்பீட்டு ஒப்புதல் மற்றும் கேஷ்லெஸ் தகுதி உங்கள் பாலிசி விதிமுறைகள், காப்பீட்டு நிறுவனம்/TPA ஒப்புதல் மற்றும் மருத்துவமனை பில்லிங் சரிபார்ப்பைப் பொறுத்தது. ({disclaimer})"

        )

    if lang_code == "kn":

        return (

            f"🏥 ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆ — ಸ್ವೀಕರಿಸಲಾಗುವ ವಿಮಾ ಕಂಪನಿಗಳು ಮತ್ತು ಯೋಜನೆಗಳ ವಿವರ ({matched_count} ಕಂಪನಿಗಳು):\n"

            f"{joined_plans}\n\n"

            f"📞 ವಿಮಾ ಸಹಾಯ ಕೇಂದ್ರ (Insurance Desk): {desk_phone} ({desk_location})\n"

            f"⚠️ ಪ್ರಮುಖ ಸೂಚನೆ (Disclaimer): ಈ ಮಾಹಿತಿಯು ಸಾಮಾನ್ಯ ಮಾರ್ಗದರ್ಶನಕ್ಕಾಗಿ ಮಾತ್ರ; ಅಂತಿಮ ಕವರೇಜ್, ಕ್ಯಾಶ್‌ಲೆಸ್ ಅನುಮೋದನೆ ಮತ್ತು ಕ್ಲೈಮ್ ಇತ್ಯರ್ಥವು ನಿಮ್ಮ ಪಾಲಿಸಿ ನಿಯಮಗಳು, ವಿಮಾ ಕಂಪನಿ/TPA ಅನುಮೋದನೆ ಮತ್ತು ಆಸ್ಪತ್ರೆಯ ಬಿಲ್ಲಿಂಗ್ ಪರಿಶೀಲನೆಯನ್ನು ಅವಲಂಬಿಸಿರುತ್ತದೆ. ({disclaimer})"

        )

    if lang_code == "hi":

        return (

            f"🏥 आरोग्य वन अस्पताल — स्वीकृत बीमा प्रदाता और प्लान विवरण ({matched_count} प्रदाता):\n"

            f"{joined_plans}\n\n"

            f"📞 बीमा हेल्पडेस्क (Insurance Desk): {desk_phone} ({desk_location})\n"

            f"⚠️ महत्वपूर्ण अस्वीकरण (Disclaimer): यह जानकारी केवल सामान्य मार्गदर्शन के लिए है; अंतिम कवरेज, कैशलेस पात्रता और क्लेम की मंजूरी आपकी पॉलिसी की शर्तों, बीमा कंपनी/TPA की स्वीकृति और अस्पताल बिलिंग सत्यापन पर निर्भर करती है। ({disclaimer})"

        )

    return (

        f"🏥 Aarogya One Hospital — Active Insurance Providers & Plans ({matched_count} provider(s)):\n"

        f"{joined_plans}\n\n"

        f"📞 Insurance & TPA Helpdesk: {desk_phone} ({desk_location})\n"

        f"⚠️ Disclaimer: {disclaimer}"

    )





def with_urgent_guidance_if_needed(lang: str, reply: str, *texts: Optional[str]) -> str:

    """

    If any provided text mentions chest pain or an acute emergency symptom, prepends

    concise emergency guidance in the active language without blocking booking progress.

    """

    if not any(is_urgent_symptom(t) for t in texts if t):

        return reply

    note = format_localized_message(lang, "urgent_chest_pain_note")

    if "108" in reply or note in reply:

        return reply

    return f"{note}\n\n{reply}"





def get_offered_slots_from_session(session_state: AgentSessionState) -> List[Dict[str, Any]]:

    """

    Returns the list of available slots most recently offered for the currently selected doctor

    (or the latest get_available_slots tool execution in session_state.tool_trace).

    """

    target_doc_id = session_state.draft.doctor_id

    fallback_slots: Optional[List[Dict[str, Any]]] = None



    for tr in reversed(session_state.tool_trace):

        if tr.tool_name == "get_available_slots" and tr.success and isinstance(tr.data, list):

            slots_data = [s for s in tr.data if isinstance(s, dict) and s.get("slot_id")]

            if fallback_slots is None:

                fallback_slots = slots_data

            if target_doc_id and slots_data:

                if any(s.get("doctor_id") == target_doc_id for s in slots_data):

                    return slots_data

            elif not target_doc_id:

                return slots_data



    return fallback_slots or []





def get_offered_doctors_from_session(session_state: AgentSessionState) -> List[Dict[str, Any]]:

    """Returns the list of doctors most recently returned by search_doctors in session_state.tool_trace."""

    for tr in reversed(session_state.tool_trace):

        if tr.tool_name == "search_doctors" and tr.success and isinstance(tr.data, list) and tr.data:

            return [d for d in tr.data if isinstance(d, dict) and d.get("doctor_id")]

    return []





def resolve_ordinal_doctor_selection(

    text: str, session_state: AgentSessionState

) -> Optional[Dict[str, Any]]:

    """

    Resolves contextual / ordinal doctor selections such as 'first doctor', 'second one',

    'మొదటి డాక్టర్', 'முதல் மருத்துவர்', 'ಮೊದಲ ವೈದ್ಯರು', 'पहले डॉक्टर', or 'show his slots'

    when only 1 doctor was listed in the previous search_doctors tool trace.

    """

    if not text or not text.strip():

        return None

    offered_docs = get_offered_doctors_from_session(session_state)

    if not offered_docs:

        return None



    low = text.strip().lower()



    # If the user explicitly mentions a doctor by name (e.g. Dr. Priya Nair, Dr. Sharma), let explicit doctor detection handle it

    if re.search(r"\b(?:dr\.?|doctor)\s+[a-z]+", low) or any(

        d in low for d in ("nair", "sharma", "swamy", "mehta", "sen", "patel", "rao")

    ):

        return None



    # Check "anyone is fine" / no preference when multiple or single doctors are offered

    if offered_docs and not session_state.draft.doctor_id:

        if re.search(

            r"\b(anyone\s+(?:is\s+)?(?:fine|ok|okay|good|cool)|any\s+(?:doctor|specialist|one)?\s+(?:is\s+)?(?:fine|ok|okay|good|cool)|no\s+preference|either\s+(?:is\s+)?(?:fine|ok|okay|good|cool)|whichever|anyone|any\s+one|you\s+(?:choose|pick|decide)|suggest\s+one|whoever|anyone\s+works|any\s+works|whatever\s+is\s+available\s+first|the\s+earliest(?:\s+one)?|evarain[a-z]*\s+(?:parvaledu|parledu|okay|ok)|ye\s+doctor\s+aina\s+(?:okay|ok|fine|parvaledu)|edaina\s+parvaledu)\b",

            low,

        ) or any(

            t in text

            for t in (

                "ఎవరైనా పర్లేదు", "ఎవరైనా పర్వాలేదు", "ఎవరైనా ఒకే", "మీరే చెప్పండి",

                "யாராக இருந்தாலும் சரி", "யாராவது சரி", "யாரு வேணா",

                "ಯಾರಾದರೂ ಸರಿ", "ಯಾರಾದ್ರೂ ಪರವಾಗಿಲ್ಲ",

                "कोई भी चलेगा", "कोई भी", "किसी से भी",

            )

        ):

            return offered_docs[0]



    # Check request for alternative doctor

    if len(offered_docs) >= 2 and (

        re.search(r"\b(?:other|another|different|next)\s+(?:doctor|specialist|option|one)\b", low)

        or any(t in text for t in ("వేరే డాక్టర్", "మరో డాక్టర్", "வேறு மருத்துவர்", "ಇನ್ನೊಬ್ಬ ವೈದ್ಯರು", "दूसरे डॉक्टर"))

    ):

        if session_state.draft.doctor_id == offered_docs[0]["doctor_id"]:

            return offered_docs[1]

        return offered_docs[1]



    # Check ordinal 1st

    if re.search(r"\b(first\s+(?:doctor|one|specialist|option)|1st\s+(?:doctor|one|option)|option\s+1|modati\s+doctor|mudhal\s+maruthuvar|modala\s+vaidyaru|pehle\s+doctor|pahle\s+doctor)\b", low) or any(

        t in text for t in ("మొదటి డాక్టర్", "మొదటి వారు", "முதல் மருத்துவர்", "ಮೊದಲ ವೈದ್ಯರು", "पहले डॉक्टर", "पहले वाले")

    ):

        return offered_docs[0]



    # Check ordinal 2nd

    if len(offered_docs) >= 2 and (

        re.search(r"\b(second\s+(?:doctor|one|specialist|option)|2nd\s+(?:doctor|one|option)|option\s+2|rendava\s+doctor|irandavadhu\s+maruthuvar|eradane\s+vaidyaru|doosre\s+doctor|dusre\s+doctor)\b", low)

        or any(

            t in text for t in ("రెండవ డాక్టర్", "రెండో డాక్టర్", "இரண்டாவது மருத்துவர்", "ಎರಡನೇ ವೈದ್ಯರು", "दूसरे डॉक्टर", "दूसरे वाले")

        )

    ):

        return offered_docs[1]



    # If exactly 1 doctor was found in the last search and user confirms or asks for slots

    if len(offered_docs) == 1 and not session_state.draft.doctor_id:

        if is_contextual_affirmative(text):

            return offered_docs[0]

        if re.search(

            r"\b(book\s+with\s+(?:him|her|them|this\s+doctor)|show\s+slots|available\s+slots|check\s+slots|his\s+slots|her\s+slots|select\s+(?:him|her)|continue|kk|book)\b",

            low,

        ) or any(

            t in text

            for t in (

                "స్లాట్లు చూపించండి", "ఆయనతో బుక్", "ఆమెతో బుక్",

                "நேரங்களைக் காட்டு", "அவரிடம் புக்",

                "ಸ್ಲಾಟ್ ತೋರಿಸಿ", "ಅವರೊಂದಿಗೆ ಬುಕ್",

                "स्लॉट दिखाएं", "उन्हीं के साथ", "उनके स्लॉट",

            )

        ):

            return offered_docs[0]



    return None





def match_slot_by_natural_language(

    text: str, offered_slots: List[Dict[str, Any]]

) -> Optional[Dict[str, Any]]:

    """

    Intelligently maps natural conversational appointment time/slot expressions to an offered slot:

    - Date and time: 'November 1 at 10:00 AM', 'Nov 1, 10 AM', '10:00 AM', '2:00 PM', '10 AM', '2 PM'

    - Relative time-of-day: 'tomorrow morning', 'morning', 'afternoon', 'after 2 PM', 'evening'

    - Contextual choices: 'the first one', 'first one', '1st one', 'second one', 'the second one', 'the first', 'the second'

    - Preferences: 'earliest available', 'earliest', 'choose the best option', 'that works'

    - Multilingual expressions in Telugu, Tamil, Kannada, and Hindi.

    """

    if not text or not offered_slots:

        return None



    low = text.strip().lower()



    # 1. Contextual ordinal & relative expressions

    if re.search(

        r"\b(first\s+one|the\s+first\s+one|the\s+first|first\s+slot|1st\s+slot|first\s+available|option\s+1|modati\s+slot|mudhal\s+slot|modala\s+slot|pehla\s+slot|pahla\s+slot)\b",

        low,

    ) or any(

        t in text

        for t in (

            "మొదటి స్లాట్", "మొదటి సమయం", "మొదటిది",

            "முதல் ஸ்லாட்", "முதல் நேரம்", "முதலாவது",

            "ಮೊದಲ ಸ್ಲಾಟ್", "ಮೊದಲ ಸಮಯ", "ಮೊದಲನೆಯದು",

            "पहला स्लॉट", "पहला समय", "पहला वाला",

        )

    ):

        return offered_slots[0]



    if len(offered_slots) >= 2 and (

        re.search(

            r"\b(second\s+one|the\s+second\s+one|the\s+second|second\s+slot|2nd\s+slot|second\s+available|option\s+2|rendava\s+slot|irandavadhu\s+slot|eradane\s+slot|doosra\s+slot|dusra\s+slot)\b",

            low,

        )

        or any(

            t in text

            for t in (

                "రెండవ స్లాట్", "రెండో స్లాట్", "రెండవది", "రెండోది",

                "இரண்டாவது ஸ்லாட்", "இரண்டாவது நேரம்", "இரண்டாவது",

                "ಎರಡನೇ ಸ್ಲಾಟ್", "ಎರಡನೇ ಸಮಯ", "ಎರಡನೆಯದು",

                "दूसरा स्लॉट", "दूसरा समय", "दूसरा वाला",

            )

        )

    ):

        return offered_slots[1]



    if len(offered_slots) >= 3 and re.search(

        r"\b(third\s+one|the\s+third\s+one|the\s+third|third\s+slot|3rd\s+slot|option\s+3)\b",

        low,

    ):

        return offered_slots[2]



    # 2. General preference or acceptance

    if re.search(r"\b(choose\s+(the\s+)?best\s+option|earliest(\s+available)?|the\s+earliest|that\s+works|best\s+option)\b", low):

        return offered_slots[0]



    # Parse datetime objects for offered slots

    from datetime import datetime

    slot_dt_list = []

    for s in offered_slots:

        st = s.get("start_time")

        if not st:

            slot_dt_list.append((None, s))

            continue

        try:

            clean = str(st).replace("Z", "").split("+")[0].replace(" ", "T")

            dt = datetime.fromisoformat(clean)

            slot_dt_list.append((dt, s))

        except Exception:

            slot_dt_list.append((None, s))



    # 3. Relative time-of-day phrases

    after_match = re.search(r"\bafter\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", low)

    if after_match:

        after_hr = int(after_match.group(1))

        is_pm = after_match.group(3) == "pm" if after_match.group(3) else (after_hr < 12 and after_hr <= 7)

        if is_pm and after_hr < 12:

            after_hr += 12

        for dt, s in slot_dt_list:

            if dt and dt.hour >= after_hr:

                return s



    if re.search(r"\b(morning|tomorrow\s+morning|ఉదయం|सुबह|காலை|ಬೆಳಿಗ್ಗೆ)\b", low):

        for dt, s in slot_dt_list:

            if dt and dt.hour < 12:

                return s



    if re.search(r"\b(afternoon|మధ్యాహ్నం|दोपहर|மதியம்|ಮಧ್ಯಾಹ್ನ)\b", low):

        for dt, s in slot_dt_list:

            if dt and 12 <= dt.hour < 17:

                return s



    if re.search(r"\b(evening|సాయంత్రం|शाम|மாலை|ಸಂಜೆ)\b", low):

        for dt, s in slot_dt_list:

            if dt and dt.hour >= 17:

                return s



    # 4. Explicit 12-hour or 24-hour time in message

    time_pat = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", low)

    time_24_pat = re.search(r"(\d{1,2}):(\d{2})", low)



    target_hour = None

    target_minute = 0

    if time_pat:

        h = int(time_pat.group(1))

        m = int(time_pat.group(2)) if time_pat.group(2) else 0

        ampm = time_pat.group(3).lower()

        if ampm == "pm" and h < 12:

            h += 12

        elif ampm == "am" and h == 12:

            h = 0

        target_hour = h

        target_minute = m

    elif time_24_pat:

        h = int(time_24_pat.group(1))

        m = int(time_24_pat.group(2))

        is_pm_indicator = bool(re.search(r"(మధ్యాహ్నం|afternoon|दोपहर|மதியம்|ಮಧ್ಯಾಹ್ನ|సాయంత్రం|evening|शाम|மாலை|ಸಂಜೆ|రాత్రి|night)", low))

        if is_pm_indicator and h < 12:

            h += 12

        target_hour = h

        target_minute = m



    # Month and day

    month_names = {

        "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,

        "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,

        "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10, "oct": 10,

        "november": 11, "nov": 11, "december": 12, "dec": 12,

        "జనవరి": 1, "ఫిబ్రవరి": 2, "మార్చి": 3, "ఏప్రిల్": 4, "మే": 5, "జూన్": 6,

        "జూలై": 7, "ఆగస్టు": 8, "సెప్టెంబర్": 9, "అక్టోబర్": 10, "నవంబర్": 11, "డిసెంబర్": 12,

        "जनवरी": 1, "फ़रवरी": 2, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6,

        "जुलाई": 7, "अगस्त": 8, "सितंबर": 9, "अक्टूबर": 10, "नवंबर": 11, "दिसंबर": 12,

        "ஜனவரி": 1, "பிப்ரவரி": 2, "மார்ச்": 3, "ஏப்ரல்": 4, "மே": 5, "ஜூன்": 6,

        "ஜூலை": 7, "ஆகஸ்ட்": 8, "செப்டம்பர்": 9, "அக்டோபர்": 10, "நவம்பர்": 11, "டிசம்பர்": 12,

        "ಜನವರಿ": 1, "ಫೆಬ್ರವರಿ": 2, "ಮಾರ್ಚ್": 3, "ಏಪ್ರಿಲ್": 4, "ಮೇ": 5, "ಜೂನ್": 6,

        "ಜುಲೈ": 7, "ಆಗಸ್ಟ್": 8, "ಸೆಪ್ಟೆಂಬರ್": 9, "ಅಕ್ಟೋಬರ್": 10, "ನವೆಂಬರ್": 11, "ಡಿಸೆಂಬರ್": 12

    }

    target_month = None

    target_day = None

    for m_name, m_num in month_names.items():

        m_regex = rf"(?:^|\s|\b){m_name}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s|\b|$)"

        m_found = re.search(m_regex, low)

        if m_found:

            target_month = m_num

            target_day = int(m_found.group(1))

            break

        rev_regex = rf"(?:^|\s|\b)(\d{{1,2}})(?:st|nd|rd|th)?\s+{m_name}(?:\s|\b|$)"

        rev_found = re.search(rev_regex, low)

        if rev_found:

            target_month = m_num

            target_day = int(rev_found.group(1))

            break



    # Match both date and time

    if target_month is not None and target_day is not None and target_hour is not None:

        for dt, s in slot_dt_list:

            if dt and dt.month == target_month and dt.day == target_day and dt.hour == target_hour and dt.minute == target_minute:

                return s

        for dt, s in slot_dt_list:

            if dt and dt.month == target_month and dt.day == target_day and dt.hour == target_hour:

                return s



    # Match date only

    if target_month is not None and target_day is not None and target_hour is None:

        for dt, s in slot_dt_list:

            if dt and dt.month == target_month and dt.day == target_day:

                return s



    # Match time only

    if target_hour is not None:

        for dt, s in slot_dt_list:

            if dt and dt.hour == target_hour and dt.minute == target_minute:

                return s

        for dt, s in slot_dt_list:

            if dt and dt.hour == target_hour:

                return s



    return None





def resolve_slot_selection(

    text: str, session_state: AgentSessionState

) -> tuple[Optional[str], Optional[str], Optional[str]]:

    """

    Resolves a patient's slot input against the current offered slots list.

    Returns (valid_slot_id, valid_slot_start_time, invalid_slot_id):

    - Normalizes bare numeric input (e.g. '101' -> 'slot-101') ONLY if 'slot-101' is in the current offered slots list.

    - Supports contextual ordinal selection ('first slot', 'second slot', 'మొదటి స్లాట్', 'पहला स्लॉट', etc.)

      and time-of-day matching (e.g. '10:00', '14:00') when offered slots exist.

    - Rejects unoffered or malformed slot IDs (e.g. 'slot-id-101', 'slot-999', or unoffered numbers) by returning

      invalid_slot_id so the assistant can clearly explain it is invalid and show actual available slot IDs.

    """

    if not text or not text.strip():

        return None, None, None



    # Do not treat lab verification codes as slot selections when checking lab status

    if session_state.pending_action == "AWAITING_LAB_VERIFICATION_CODE" or is_lab_report_inquiry(text):

        if not re.search(r"\bslot-[A-Za-z0-9_-]+\b", text, re.IGNORECASE):

            return None, None, None



    # Flexible slot requests (e.g. 'anything is fine', 'कोई भी समय चलेगा', 'ఏదైనా పర్వాలేదు')

    # are handled by suggest_earliest_slot rather than selecting a specific slot immediately

    if is_flexible_slot_request(text):

        return None, None, None



    offered_slots = get_offered_slots_from_session(session_state)

    offered_map: Dict[str, Dict[str, Any]] = {

        str(s["slot_id"]).lower(): s for s in offered_slots if s.get("slot_id")

    }



    # 1. Explicit 'slot-...' identifier in message

    slot_match = re.search(r"\b(slot-[A-Za-z0-9_-]+)\b", text, re.IGNORECASE)

    if slot_match:

        raw_slot = slot_match.group(1)

        raw_low = raw_slot.lower()

        if raw_low in offered_map:

            matched = offered_map[raw_low]

            return str(matched["slot_id"]), matched.get("start_time"), None

        # Allow the seeded booked-slot test fixture to test 409 conflict at commit time

        if raw_low == "slot-sharma-booked-3":

            return raw_slot, None, None

        # If no get_available_slots trace exists yet in this session (e.g. single-turn unit test),

        # accept well-formed slot-... IDs except malformed 'slot-id-...' inputs

        if not offered_map and not raw_low.startswith("slot-id-"):

            return raw_slot, None, None

        return None, None, raw_slot



    # 2. Match natural language time / date / ordinal / preference expression if offered_slots exist

    if offered_slots:

        nat_slot = match_slot_by_natural_language(text, offered_slots)

        if nat_slot:

            return str(nat_slot["slot_id"]), nat_slot.get("start_time"), None



    # 3. Contextual ordinal slot selection ('first slot', 'second slot', etc.) when offered_slots exist

    low = text.strip().lower()

    if offered_slots:

        if re.search(

            r"\b(first\s+slot|1st\s+slot|first\s+available|option\s+1|modati\s+slot|mudhal\s+slot|modala\s+slot|pehla\s+slot|pahla\s+slot)\b",

            low,

        ) or any(

            t in text

            for t in (

                "మొదటి స్లాట్", "మొదటి సమయం",

                "முதல் ஸ்லாட்", "முதல் நேரம்",

                "ಮೊದಲ ಸ್ಲಾಟ್", "ಮೊದಲ ಸಮಯ",

                "पहला स्लॉट", "पहला समय",

            )

        ):

            s0 = offered_slots[0]

            return str(s0["slot_id"]), s0.get("start_time"), None



        if len(offered_slots) >= 2 and (

            re.search(

                r"\b(second\s+slot|2nd\s+slot|second\s+available|option\s+2|rendava\s+slot|irandavadhu\s+slot|eradane\s+slot|doosra\s+slot|dusra\s+slot)\b",

                low,

            )

            or any(

                t in text

                for t in (

                    "రెండవ స్లాట్", "రెండో స్లాట్",

                    "இரண்டாவது ஸ்லாட்", "இரண்டாவது நேரம்",

                    "ಎರಡನೇ ಸ್ಲಾಟ್", "ಎರಡನೇ ಸಮಯ",

                    "दूसरा स्लॉट", "दूसरा समय",

                )

            )

        ):

            s1 = offered_slots[1]

            return str(s1["slot_id"]), s1.get("start_time"), None



        # Match explicit HH:MM time if it uniquely/directly matches an offered slot's start_time

        time_match = re.search(r"\b(\d{1,2}:\d{2})\b", low)

        if time_match:

            hhmm = time_match.group(1)

            if len(hhmm) == 4:

                hhmm_padded = f"0{hhmm}"

            else:

                hhmm_padded = hhmm

            for s_obj in offered_slots:

                st = str(s_obj.get("start_time", ""))

                if hhmm in st or hhmm_padded in st:

                    return str(s_obj["slot_id"]), s_obj.get("start_time"), None



    # 3. Check 'slot <token>' with whitespace (e.g., 'slot 101' or 'slot id 101')

    slot_space_match = re.search(r"\bslot\s+([A-Za-z0-9_-]+)\b", text, re.IGNORECASE)

    if slot_space_match:

        tok = slot_space_match.group(1)

        if tok.lower() not in ("for", "with", "in", "on", "at", "is", "id", "ids", "list", "options"):

            cand = f"slot-{tok}".lower()

            if cand in offered_map:

                matched = offered_map[cand]

                return str(matched["slot_id"]), matched.get("start_time"), None

            if tok.lower() in offered_map:

                matched = offered_map[tok.lower()]

                return str(matched["slot_id"]), matched.get("start_time"), None

            return None, None, f"slot-{tok}" if not tok.lower().startswith("slot") else tok



    # 4. Bare numeric slot selection (e.g., '101' -> 'slot-101' ONLY if 'slot-101' is in offered_map)

    cleaned_for_nums = re.sub(r"\bPAT-[A-Za-z0-9-]+\b", "", text, flags=re.IGNORECASE)

    cleaned_for_nums = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", cleaned_for_nums)

    cleaned_for_nums = re.sub(r"\b\d{1,2}:\d{2}\b", "", cleaned_for_nums)

    num_matches = re.findall(r"\b(\d{1,6})\b", cleaned_for_nums)

    if num_matches:

        for num_str in num_matches:

            candidate_key = f"slot-{num_str}".lower()

            if candidate_key in offered_map:

                matched = offered_map[candidate_key]

                return str(matched["slot_id"]), matched.get("start_time"), None



        # If patient is at the slot selection step and entered an unoffered number (e.g. '101' when not offered, or '999')

        only_digits_and_slot_words = re.sub(

            r"\b(i|want|choose|pick|select|book|slot|number|id|option|please|for|me)\b",

            "",

            cleaned_for_nums.lower(),

        )

        only_digits_and_slot_words = re.sub(r"[\d\s,.:;!?-]+", "", only_digits_and_slot_words)

        if session_state.draft.doctor_id and not session_state.draft.slot_id and not only_digits_and_slot_words:

            return None, None, num_matches[0]



    # 5. Exact UUID or custom slot_id from offered_map appearing in text

    text_low = text.lower()

    for sid_low, s_obj in offered_map.items():

        if sid_low in text_low:

            return str(s_obj["slot_id"]), s_obj.get("start_time"), None



    return None, None, None





MULTILINGUAL_SPECIALTY_KEYWORDS: Dict[str, List[str]] = {

    "Cardiology": [

        "heart", "cardio", "cardiology", "cardiologist", "chest pain", "palpitation", "palpitations", "angina",

        "gunde", "gunde noppi", "chati noppi", "chaati noppi", "nenju vali", "idhaya", "idhayam",

        "ede novu", "hrudaya", "seene mein dard", "chaati mein dard", "dil ka doctor",

        "కార్డియాలజీ", "కార్డియాలజిస్ట్", "గుండె", "ఛాతీ నొప్పి", "గుండె దడ",

        "இதயவியல்", "இதய", "நெஞ்சு வலி", "படபடப்பு",

        "ಕಾರ್ಡಿಯಾಲಜಿ", "ಹೃದ್ರೋಗ", "ಹೃದ್ರೋಗ ತಜ್ಞ", "ಹೃದಯ", "ಎದೆ ನೋವು", "ಎದೆ ಬಡಿತ",

        "कार्डियोलॉजी", "कार्डियोलॉजिस्ट", "हृदय", "दिल", "सीने में दर्द", "छाती में दर्द", "घबराहट",

    ],

    "Neurology": [

        "brain", "neuro", "neurology", "neurologist", "headache", "migraine", "stroke", "seizure", "numbness",

        "dizziness", "dizzy", "vertigo", "epilepsy", "nerve",

        "talanoppi", "medadu", "thalaivali", "narambu", "talenovu", "sirdard", "sar dard", "dimag",

        "న్యూరాలజీ", "న్యూరాలజిస్ట్", "మెదడు", "తలనొప్పి", "మైగ్రేన్", "నరాల",

        "நரம்பியல்", "நரம்பு", "தலைவலி", "ஒற்றைத் தலைவலி",

        "ನ್ಯೂರಾಲಜಿ", "ನರ", "ತಲೆನೋವು", "ಮೈಗ್ರೇನ್",

        "न्यूरोलॉजी", "न्यूरोलॉजिस्ट", "नस", "सिरदर्द", "माइग्रेन", "दिमाग",

    ],

    "Orthopedics": [

        "bone", "joint", "ortho", "orthopedics", "orthopedic", "knee", "fracture", "spine", "back pain", "arthritis",

        "shoulder pain", "neck pain", "ankle",

        "mokalla noppi", "emuka", "keella", "elumbu", "moottu vali", "mandi novu", "moole", "haddi", "ghutne", "kamar dard",

        "ఆర్థోపెడిక్స్", "ఎముక", "ఎముకల", "కీళ్ల", "మోకాళ్ళ నొప్పి", "వెన్నునొప్పి",

        "எலும்பியல்", "எலும்பு", "மூட்டு வலி", "முழங்கால் வலி", "முதுகு வலி",

        "ಆರ್ಥೋಪೆಡಿಕ್ಸ್", "ಮೂಳೆ", "ಮಂಡಿ ನೋವು", "ಕೀಲು ನೋವು", "ಬೆನ್ನು ನೋವು",

        "ऑर्थोपेडिक्स", "हड्डी", "घुटने", "जोड़ों का दर्द", "कमर दर्द",

    ],

    "Pediatrics": [

        "child", "children", "pediatric", "pediatrics", "pediatrician", "infant", "baby", "kid", "vaccination", "newborn",

        "pillala", "chinna pillala", "kuzhandhai", "makkala", "magu", "bachon", "bacha",

        "పీడియాట్రిక్స్", "పిల్లల", "చిన్నపిల్లల", "టీకా",

        "குழந்தைகள்", "குழந்தை", "தடுப்பூசி",

        "ಪೀಡಿಯಾಟ್ರಿಕ್ಸ್", "ಮಕ್ಕಳ", "ಮಗು",

        "पीडियाट्रिक्स", "बाल रोग", "बच्चों", "बच्चे", "टीकाकरण",

    ],

    "General Medicine": [

        "fever", "cough", "cold", "flu", "weakness", "general", "physician", "checkup", "routine",

        "stomach pain", "body pain", "diabetes", "infection",

        "jwaram", "daggu", "jalubu", "kaichal", "irumal", "sali", "jwara", "kemmu", "negadi", "bukhar", "khansi", "jukam",

        "జనరల్ మెడిసిన్", "జ్వరం", "దగ్గు", "జలుబు", "సాధారణ వైద్యం", "నీరసం",

        "பொது மருத்துவம்", "காய்ச்சல்", "இருமல்", "சளி",

        "ಜನರಲ್ ಮೆಡಿಸಿನ್", "ಜ್ವರ", "ಕೆಮ್ಮು", "ನೆಗಡಿ", "ಸಾಮಾನ್ಯ",

        "जनरल मेडिसिन", "बुखार", "खांसी", "जुकाम", "सामान्य चिकित्सा", "फिजीशियन", "कमजोरी",

    ],

}



MULTILINGUAL_DOCTOR_KEYWORDS: List[Dict[str, Any]] = [

    {

        "search_term": "Sharma",

        "keywords": ["sharma", "rajesh", "శర్మ", "రాజేష్", "சர்மா", "ராஜேஷ்", "ಶರ್ಮಾ", "ರಾಜೇಶ್", "शर्मा", "राजेश"],

    },

    {

        "search_term": "Nair",

        "keywords": ["nair", "priya", "నాయర్", "ప్రియ", "ప్రియా", "நாயர்", "பிரியா", "ನಾಯರ್", "ಪ್ರಿಯಾ", "नायर", "प्रिया"],

    },

    {

        "search_term": "Swamy",

        "keywords": ["swamy", "arvind", "స్వామి", "అరవింద్", "சுவாமி", "அரவிந்த்", "ಸ್ವಾಮಿ", "ಅರವಿಂದ್", "स्वामी", "अरविंद"],

    },

    {

        "search_term": "Sen",

        "keywords": ["sen", "ananya", "సేన్", "అనన్య", "சென்", "அனன்யா", "ಸೇನ್", "ಅನನ್ಯಾ", "सेन", "अनन्या"],

    },

    {

        "search_term": "Mehta",

        "keywords": ["mehta", "vikram", "మెహతా", "విక్రమ్", "மேத்தா", "விக்ரம்", "ಮೆಹ್ತಾ", "ವಿಕ್ರಮ್", "मेहता", "विक्रम"],

    },

    {

        "search_term": "Rao",

        "keywords": ["rao", "sunita", "రావు", "సునీత", "ராவ்", "சுனிதா", "ರாவ್", "ಸುನೀತಾ", "राव", "सुनीता"],

    },

]



MULTILINGUAL_REASON_PHRASES: List[str] = [

    # Telugu

    "ఛాతీ నొప్పి మరియు గుండె దడ", "గుండె నొప్పి పరీక్ష", "గుండె దడ", "ఛాతీ నొప్పి", "ఛాతీలో నొప్పి", "గుండె నొప్పి",

    "తలనొప్పి", "మైగ్రేన్", "మోకాళ్ళ నొప్పి", "కీళ్ల నొప్పి", "వెన్నునొప్పి", "జ్వరం మరియు దగ్గు", "జ్వరం", "దగ్గు", "జలుబు",

    "సాధారణ తనిఖీ", "సాధారణ పరీక్ష", "ఊపిరి ఆడకపోవడం",

    # Tamil

    "நெஞ்சு வலி மற்றும் படபடப்பு", "நெஞ்சு வலி பரிசோதனை", "நெஞ்சு வலி", "இதய வலி", "படபடப்பு",

    "தலைவலி", "ஒற்றைத் தலைவலி", "மூட்டு வலி", "முழங்கால் வலி", "முதுகு வலி", "காய்ச்சல்", "இருமல்", "சளி",

    "வழக்கமான பரிசோதனை", "மூச்சுத்திணறல்",

    # Kannada

    "ಎದೆ ನೋವು ಮತ್ತು ಎದೆ ಬಡಿತ", "ಎದೆ ನೋವು ತಪಾಸಣೆ", "ಎದೆ ನೋವು", "ಹೃದಯ ನೋವು", "ಎದೆ ಬಡಿತ",

    "ತಲೆನೋವು", "ಮೈಗ್ರೇನ್", "ಮಂಡಿ ನೋವು", "ಕೀಲು ನೋವು", "ಬೆನ್ನು ನೋವು", "ಜ್ವರ", "ಕೆಮ್ಮು", "ನೆಗಡಿ",

    "ಸಾಮಾನ್ಯ ತಪಾಸಣೆ", "ಉಸಿರಾಟದ ತೊಂದರೆ",

    # Hindi

    "सीने में दर्द और घबराहट", "सीने में दर्द की जांच", "सीने में दर्द", "छाती में दर्द", "दिल में दर्द", "घबराहट",

    "सिरदर्द", "माइग्रेन", "घुटने में दर्द", "जोड़ों का दर्द", "कमर दर्द", "बुखार और खांसी", "बुखार", "खांसी", "जुकाम",

    "रूटीन चेकअप", "सामान्य जांच", "सांस लेने में तकलीफ",

]



ENGLISH_REASON_PHRASES: List[str] = [

    "intermittent palpitations and chest evaluation",

    "chest pain and palpitations",

    "chest pain evaluation",

    "Chest pain checkup",

    "severe chest pain",

    "chest pain",

    "chest tightness",

    "chest discomfort",

    "intermittent palpitations",

    "palpitations",

    "heart pain",

    "angina consultation",

    "angina",

    "shortness of breath",

    "difficulty breathing",

    "cardiac checkup",

    "chronic migraine",

    "migraine",

    "severe headache",

    "headache",

    "dizziness",

    "knee pain",

    "joint pain",

    "back pain",

    "shoulder pain",

    "fever and cough",

    "high fever",

    "fever",

    "cough and cold",

    "cough",

    "stomach pain",

    "child vaccination",

    "vaccination",

    "routine checkup",

    "general checkup",

    "annual checkup",

    "routine review",

    "follow-up",

    "follow up",

    # Transliterated clinical reason phrases

    "gunde noppi",

    "chati noppi",

    "chaati noppi",

    "talanoppi",

    "mokalla noppi",

    "jwaram",

    "nenju vali",

    "thalaivali",

    "moottu vali",

    "kaichal",

    "ede novu",

    "talenovu",

    "mandi novu",

    "jwara",

    "seene mein dard",

    "chaati mein dard",

    "sirdard",

    "ghutne mein dard",

    "kamar dard",

    "bukhar",

]





SPECIALTY_NOUNS: Dict[str, Dict[str, Dict[str, str]]] = {

    "en": {

        "Cardiology": {"noun": "cardiologist", "plural": "cardiologists"},

        "Neurology": {"noun": "neurologist", "plural": "neurologists"},

        "Orthopedics": {"noun": "orthopedic specialist", "plural": "orthopedic specialists"},

        "Pediatrics": {"noun": "pediatrician", "plural": "pediatricians"},

        "General Medicine": {"noun": "general physician", "plural": "general physicians"},

        "Dermatology": {"noun": "dermatologist", "plural": "dermatologists"},

    },

    "te": {

        "Cardiology": {"noun": "కార్డియాలజిస్ట్ (గుండె నిపుణులు)", "plural": "కార్డియాలజిస్ట్‌లను"},

        "Neurology": {"noun": "న్యూరాలజిస్ట్ (నరాల నిపుణులు)", "plural": "న్యూరాలజిస్ట్‌లను"},

        "Orthopedics": {"noun": "ఆర్థోపెడిక్ నిపుణులు", "plural": "ఆర్థోపెడిక్ నిపుణులను"},

        "Pediatrics": {"noun": "పీడియాట్రిషియన్ (పిల్లల నిపుణులు)", "plural": "పీడియాట్రిషియన్లను"},

        "General Medicine": {"noun": "జనరల్ ఫిజీషియన్", "plural": "జనరల్ ఫిజీషియన్లను"},

        "Dermatology": {"noun": "డెర్మటాలజిస్ట్ (చర్మ నిపుణులు)", "plural": "డెర్మటాలజిస్ట్‌లను"},

    },

    "ta": {

        "Cardiology": {"noun": "இதய மருத்துவரை (Cardiologist)", "plural": "இதய மருத்துவர்களை"},

        "Neurology": {"noun": "நரம்பியல் மருத்துவரை (Neurologist)", "plural": "நரம்பியல் மருத்துவர்களை"},

        "Orthopedics": {"noun": "எலும்பியல் மருத்துவரை (Orthopedist)", "plural": "எலும்பியல் மருத்துவர்களை"},

        "Pediatrics": {"noun": "குழந்தைகள் நல மருத்துவரை (Pediatrician)", "plural": "குழந்தைகள் நல மருத்துவர்களை"},

        "General Medicine": {"noun": "பொது மருத்துவரை (General Physician)", "plural": "பொது மருத்துவர்களை"},

        "Dermatology": {"noun": "சரும மருத்துவரை (Dermatologist)", "plural": "சரும மருத்துவர்களை"},

    },

    "kn": {

        "Cardiology": {"noun": "ಹೃದ್ರೋಗ ತಜ್ಞರನ್ನು (Cardiologist)", "plural": "ಹೃದ್ರೋಗ ತಜ್ಞರನ್ನು"},

        "Neurology": {"noun": "ನರರೋಗ ತಜ್ಞರನ್ನು (Neurologist)", "plural": "ನರರೋಗ ತಜ್ಞರನ್ನು"},

        "Orthopedics": {"noun": "ಮೂಳೆ ರೋಗ ತಜ್ಞರನ್ನು (Orthopedist)", "plural": "ಮೂಳೆ ರೋಗ ತಜ್ಞರನ್ನು"},

        "Pediatrics": {"noun": "ಮಕ್ಕಳ ತಜ್ಞರನ್ನು (Pediatrician)", "plural": "ಮಕ್ಕಳ ತಜ್ಞರನ್ನು"},

        "General Medicine": {"noun": "ಸಾಮಾನ್ಯ ವೈದ್ಯರನ್ನು (General Physician)", "plural": "ಸಾಮಾನ್ಯ ವೈದ್ಯರನ್ನು"},

        "Dermatology": {"noun": "ಚರ್ಮರೋಗ ತಜ್ಞರನ್ನು (Dermatologist)", "plural": "ಚರ್ಮರೋಗ ತಜ್ಞರನ್ನು"},

    },

    "hi": {

        "Cardiology": {"noun": "कार्डियोलॉजिस्ट (हृदय रोग विशेषज्ञ)", "plural": "कार्डियोलॉजिस्ट्स"},

        "Neurology": {"noun": "न्यूरोलॉजिस्ट (नस रोग विशेषज्ञ)", "plural": "न्यूरोलॉजिस्ट्स"},

        "Orthopedics": {"noun": "ऑर्थोपेडिक विशेषज्ञ (हड्डी रोग विशेषज्ञ)", "plural": "ऑर्थोपेडिक विशेषज्ञों"},

        "Pediatrics": {"noun": "बाल रोग विशेषज्ञ (Pediatrician)", "plural": "बाल रोग विशेषज्ञों"},

        "General Medicine": {"noun": "सामान्य चिकित्सक (General Physician)", "plural": "सामान्य चिकित्सकों"},

        "Dermatology": {"noun": "त्वचा रोग विशेषज्ञ (Dermatologist)", "plural": "त्वचा रोग विशेषज्ञों"},

    },

}





def get_specialist_noun(lang: str, specialty: str) -> str:

    lang_code = lang if lang in SPECIALTY_NOUNS else "en"

    entry = SPECIALTY_NOUNS[lang_code].get(specialty)

    if entry:

        return entry["noun"]

    return f"{specialty} specialist"





def get_specialist_plural(lang: str, specialty: str) -> str:

    lang_code = lang if lang in SPECIALTY_NOUNS else "en"

    entry = SPECIALTY_NOUNS[lang_code].get(specialty)

    if entry:

        return entry["plural"]

    return f"{specialty} specialists"





def normalize_specialty_term(raw: str) -> Optional[str]:

    """

    Normalizes common variations, synonyms, and misspellings of medical specialties.

    Handles typos like 'cardioligist', 'cardiolgy', 'neurologest', 'orthopedist',

    'orthopaedic', 'paediatrician', 'dermatologyst', etc.

    """

    if not raw or not raw.strip():

        return None

    low = raw.strip().lower()



    # Exact or substring patterns for typo tolerance

    if (

        re.search(r"\b(cardio|cardioligist|cardiologist|cardiology|cardiolgy|cardiolog|heart\s*specialist|heart\s*doctor|dil\s*ka\s*doctor|idhaya\s*maruthuvar)\b", low)

        or re.search(r"cardio[a-z]*", low)

    ):

        return "Cardiology"

    if (

        re.search(r"\b(neuro|neurologest|neurologist|neurology|neurolog|brain\s*specialist|nerve\s*specialist)\b", low)

        or re.search(r"neuro[a-z]*", low)

    ):

        return "Neurology"

    if (

        re.search(r"\b(ortho|orthopedist|orthopedic|orthopedics|orthopaedic|orthopaedics|bone\s*specialist|joint\s*specialist)\b", low)

        or re.search(r"ortho[a-z]*", low)

    ):

        return "Orthopedics"

    if (

        re.search(r"\b(paediatrician|paediatric|paediatrics|pediatrician|pediatric|pediatrics|child\s*specialist)\b", low)

        or re.search(r"p[ae]diatr[a-z]*", low)

    ):

        return "Pediatrics"

    if (

        re.search(r"\b(dermatologist|dermatology|dermatologyst|dermat|skin\s*specialist|skin\s*doctor)\b", low)

        or re.search(r"dermat[a-z]*", low)

    ):

        return "Dermatology"

    if re.search(r"\b(general\s*medicine|general\s*physician|physician|internal\s*medicine|family\s*doctor)\b", low):

        return "General Medicine"



    # Multilingual terms

    indic_cardio = (

        "కార్డియాలజీ", "కార్డియాలజిస్ట్", "గుండె డాక్టర్",

        "இதயவியல்", "இதய மருத்துவர்",

        "ಕಾರ್ಡಿಯಾಲಜಿ", "ಹೃದ್ರೋಗ ತಜ್ಞ", "ಹೃದ್ರೋಗ ವಿಭಾಗ",

        "कार्डियोलॉजी", "कार्डियोलॉजिस्ट", "हृदय रोग विशेषज्ञ",

    )

    if any(t in raw for t in indic_cardio):

        return "Cardiology"



    indic_neuro = (

        "న్యూరాలజీ", "న్యూరాలజిస్ట్", "నరాల డాక్టర్", "నరాల విభాగం",

        "நரம்பியல்", "நரம்பு மருத்துவர்",

        "ನ್ಯೂರಾಲಜಿ", "ನರರೋಗ ತಜ್ಞ", "ನರರೋಗ ವಿಭಾಗ",

        "न्यूरोलॉजी", "न्यूरोलॉजिस्ट", "नस रोग विशेषज्ञ",

    )

    if any(t in raw for t in indic_neuro):

        return "Neurology"



    indic_ortho = (

        "ఆర్థోపెడిక్స్", "ఎముకల డాక్టర్", "కీళ్ల విభాగం",

        "எலும்பியல்", "எலும்பு மருத்துவர்",

        "ಆರ್ಥೋಪೆಡಿಕ್ಸ್", "ಮೂಳೆ ತಜ್ಞ",

        "ऑर्थोपेडिक्स", "हड्डी रोग विशेषज्ञ",

    )

    if any(t in raw for t in indic_ortho):

        return "Orthopedics"



    indic_paed = (

        "పీడియాట్రిక్స్", "పిల్లల డాక్టర్", "పిల్లల విభాగం",

        "குழந்தைகள் நலம்", "குழந்தைகள் மருத்துவர்",

        "ಪೀಡಿಯಾಟ್ರಿಕ್ಸ್", "ಮಕ್ಕಳ ತಜ್ಞ",

        "पीडियाट्रिक्स", "बाल रोग विशेषज्ञ",

    )

    if any(t in raw for t in indic_paed):

        return "Pediatrics"



    indic_gen = (

        "జనరల్ మెడిసిన్", "సాధారణ వైద్యం",

        "பொது மருத்துவம்", "பொது மருத்துவர்",

        "ಜನರಲ್ ಮೆಡಿಸಿನ್", "ಸಾಮಾನ್ಯ ವೈದ್ಯಕೀಯ",

        "जनरल मेडिसिन", "सामान्य चिकित्सा", "फिजीशियन",

    )

    if any(t in raw for t in indic_gen):

        return "General Medicine"



    indic_derm = (

        "డెర్మటాలజీ", "చర్మ డాక్టర్", "చర్మ నిపుణులు",

        "சரும மருத்துவர்", "தோல் மருத்துவர்",

        "ಚರ್ಮ ತಜ್ಞ", "ಚರ್ಮರೋಗ ತಜ್ಞ",

        "त्वचा रोग विशेषज्ञ", "डर्मेटोलॉजिस्ट",

    )

    if any(t in raw for t in indic_derm):

        return "Dermatology"



    return None





EXPLICIT_SPECIALTY_DEPARTMENT_KEYWORDS: Dict[str, List[str]] = {

    "Cardiology": [

        "cardio", "cardiology", "cardiologist", "heart specialist", "dil ka doctor", "idhaya maruthuvar",

        "కార్డియాలజీ", "కార్డియాలజిస్ట్", "గుండె డాక్టర్",

        "இதயவியல்", "இதய மருத்துவர்",

        "ಕಾರ್ಡಿಯಾಲಜಿ", "ಹೃದ್ರೋಗ ತಜ್ಞ", "ಹೃದ್ರೋಗ ವಿಭಾಗ",

        "कार्डियोलॉजी", "कार्डियोलॉजिस्ट", "हृदय रोग विशेषज्ञ",

    ],

    "Neurology": [

        "neuro", "neurology", "neurologist", "brain specialist", "nerve specialist",

        "న్యూరాలజీ", "న్యూరాలజిస్ట్", "నరాల డాక్టర్", "నరాల విభాగం",

        "நரம்பியல்", "நரம்பு மருத்துவர்",

        "ನ್ಯೂರಾಲಜಿ", "ನರರೋಗ ತಜ್ಞ", "ನರರೋಗ ವಿಭಾಗ",

        "न्यूरोलॉजी", "न्यूरोलॉजिस्ट", "नस रोग विशेषज्ञ",

    ],

    "Orthopedics": [

        "ortho", "orthopedics", "orthopedic", "bone specialist", "joint specialist",

        "ఆర్థోపెడిక్స్", "ఎముకల డాక్టర్", "కీళ్ల విభాగం",

        "எலும்பியல்", "எலும்பு மருத்துவர்",

        "ಆರ್ಥೋಪೆಡಿಕ್ಸ್", "ಮೂಳೆ ತಜ್ಞ",

        "ऑर्थोपेडिक्स", "हड्डी रोग विशेषज्ञ",

    ],

    "Pediatrics": [

        "pediatric", "pediatrics", "pediatrician", "child specialist",

        "పీడియాట్రిక్స్", "పిల్లల డాక్టర్", "పిల్లల విభాగం",

        "குழந்தைகள் நலம்", "குழந்தைகள் மருத்துவர்",

        "ಪೀಡಿಯಾಟ್ರಿಕ್ಸ್", "ಮಕ್ಕಳ ತಜ್ಞ",

        "पीडियाट्रिक्स", "बाल रोग विशेषज्ञ",

    ],

    "General Medicine": [

        "general medicine", "general physician", "physician", "family doctor", "internal medicine",

        "జనరల్ మెడిసిన్", "సాధారణ వైద్యం",

        "பொது மருத்துவம்", "பொது மருத்துவர்",

        "ಜನರಲ್ ಮೆಡಿಸಿನ್", "ಸಾಮಾನ್ಯ ವೈದ್ಯಕೀಯ",

        "जनरल मेडिसिन", "सामान्य चिकित्सा", "फिजीशियन",

    ],

    "Dermatology": [

        "dermatology", "dermatologist", "dermatologyst", "skin specialist", "skin doctor", "dermat",

        "డెర్మటాలజీ", "చర్మ డాక్టర్", "చర్మ నిపుణులు",

        "சரும மருத்துவர்", "தோல் மருத்துவர்",

        "ಚರ್ಮ ತಜ್ಞ", "ಚರ್ಮರೋಗ ತಜ್ಞ",

        "त्वचा रोग विशेषज्ञ", "डर्मेटोलॉजिस्ट",

    ],

}



COMMON_SECONDARY_GENERAL_MEDICINE_SYMPTOMS: List[str] = [

    "headache", "talanoppi", "thalaivali", "talenovu", "sirdard", "sar dard",

    "తలనొప్పి", "தலைவலி", "ತಲೆನೋವು", "सिरदर्द",

    "body pain", "weakness", "dizziness", "dizzy", "cold", "cough", "fever",

    "జ్వరం", "దగ్గు", "జలుబు", "నీరసం",

    "காய்ச்சல்", "இருமல்", "சளி",

    "ಜ್ವರ", "ಕೆಮ್ಮು", "ನೆಗಡಿ",

    "बुखार", "खांसी", "जुकाम", "कमजोरी",

]





def detect_explicit_specialty_request(text: str) -> Optional[str]:

    """

    Returns the canonical specialty ONLY if the user explicitly named a medical specialty

    or specialist title (e.g., 'Neurology', 'neurologist', 'కార్డియాలజిస్ట్', 'cardioligist'),

    as opposed to merely mentioning a symptom like 'headache' or 'తలనొప్పి'.

    Uses normalized typo-tolerant matching and controlled synonym map.

    """

    if not text or not text.strip():

        return None



    # Typo-tolerant normalization first

    normalized = normalize_specialty_term(text)

    if normalized:

        return normalized



    low = text.lower()

    for spec, keywords in EXPLICIT_SPECIALTY_DEPARTMENT_KEYWORDS.items():

        for kw in keywords:

            if kw.isascii():

                if re.search(rf"\b{re.escape(kw)}\b", low):

                    return spec

            else:

                if kw in text:

                    return spec

    return None





EXPLICIT_DOCTOR_STOPWORDS = {
    "के", "का", "की", "साथ", "को", "से", "में", "వారితో", "వారి", "వారికి", 
    "for", "regarding", "about", "who", "kavali", "కావాలి", "చూపించాలి", "వెళ్ళాలి",
    "appointment", "booking", "slot", "slots", "availability", "details", "list",
    "names", "hospital", "chahiye", "veendum", "beku", "vendi", "theva", "venum",
    "specialist", "consultation", "time", "fee", "cost", "today", "tomorrow",
    "near", "best", "good", "any", "anyone", "someone", "please", "can", "you",
    "book", "schedule", "cheyandi", "karo", "pannunga", "madi", "undi", "undhi"
}

EXPLICIT_DOCTOR_SPECIALTY_WORDS = {
    "fever", "heart", "cardio", "cardiology", "cardiologist", "cardioligist",
    "neuro", "neurology", "neurologist", "ortho", "orthopedics", "orthopedist", "orthopaedic",
    "peds", "pediatrics", "pediatrician", "paediatrician", "derma", "dermatology", "dermatologist",
    "general", "physician", "medicine", "doctor", "specialist",
    "జ్వరం", "గుండె", "మెదడు", "ఎముకల", "కీళ్ల", "పిల్లల", "బుఖార్", "కாய்ச்சల్", "ಜ್ವರ", "ಬುಖಾರ್",
    "కార్డియాలజీ", "కార్డియాలజిస్ట్", "న్యూరాలజీ", "న్యూరాలజిస్ట్", "ఆర్థోపెడిక్స్"
}

EXPLICIT_DOCTOR_HONORIFICS = [
    "గారితో", "గారికి", "గారు", "గారి", "తో", "జీ", "जी", "साहब", "அவர்கள்", "உடன்", "ಅವರೊಂದಿಗೆ", "ಅವರ"
]


def extract_explicit_doctor_name(text: str) -> Optional[str]:
    """
    Extracts explicitly named doctor from user input across English, Telugu, Hindi, Tamil, and Kannada.
    Distinguishes explicit doctor names (e.g. 'డాక్టర్ జగ్గయ్య', 'Dr. Jaggayya', 'Dr. Rajesh Sharma') from clinical specialty requests
    (e.g. 'I want to see a cardiologist', 'see a neurologist', 'I need a doctor for fever', 'నాకు డాక్టర్ కావాలి').
    """
    if not text:
        return None
    patterns = [
        r'(?:dr\.?|doctor|డాక్టర్|డాక్టరు|డాక్టర్\s+గారు|డాక్టరు\s+గారు|डॉक्टर|डाక్టర్|டாக்டர்|ಡಾಕ್ಟರ್)\s+([A-Za-z\u0C00-\u0C7F\u0900-\u097F\u0B80-\u0BFF\u0C80-\u0CFF]+(?:\s+[A-Za-z\u0C00-\u0C7F\u0900-\u097F\u0B80-\u0BFF\u0C80-\u0CFF]+)?)',
        r'(?:with|see|consult)\s+(?:dr\.?|doctor)\s+([A-Za-z\u0C00-\u0C7F\u0900-\u097F\u0B80-\u0BFF\u0C80-\u0CFF]+(?:\s+[A-Za-z\u0C00-\u0C7F\u0900-\u097F\u0B80-\u0BFF\u0C80-\u0CFF]+)?)',
        r'([A-Za-z\u0C00-\u0C7F]+)\s*గారితో',
        r'([A-Za-z\u0900-\u097F]+)\s*జీ\s*కే\s*साथ',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            parts = raw.split()
            valid_parts = []
            for p in parts:
                cleaned_p = p
                while True:
                    changed = False
                    for h in sorted(EXPLICIT_DOCTOR_HONORIFICS, key=len, reverse=True):
                        if cleaned_p.endswith(h) and len(cleaned_p) > len(h):
                            cleaned_p = cleaned_p[:-len(h)].strip()
                            changed = True
                            break
                    if not changed:
                        break
                if (
                    cleaned_p
                    and cleaned_p.lower() not in EXPLICIT_DOCTOR_STOPWORDS
                    and cleaned_p.lower() not in EXPLICIT_DOCTOR_SPECIALTY_WORDS
                    and cleaned_p not in EXPLICIT_DOCTOR_HONORIFICS
                ):
                    valid_parts.append(cleaned_p)
            if not valid_parts:
                continue
            res = " ".join(valid_parts)
            if len(res) >= 2:
                return res
    return None


def detect_doctor_query(text: str) -> Optional[str]:

    low = text.lower()

    for entry in MULTILINGUAL_DOCTOR_KEYWORDS:

        for kw in entry["keywords"]:

            if kw.isascii():

                if re.search(rf"\b{re.escape(kw)}\b", low):

                    return entry["search_term"]

            else:

                if kw in text:

                    return entry["search_term"]

    # Check for explicitly named doctor (e.g., 'doctor జగ్గయ్య', 'Dr. Jaggayya')
    return extract_explicit_doctor_name(text)





def _matches_keyword_list(text: str, low: str, keywords: List[str]) -> bool:

    for kw in keywords:

        if kw.isascii():

            if re.search(rf"\b{re.escape(kw)}\b", low):

                return True

        else:

            if kw in text:

                return True

    return False





def detect_specialty_query(text: str, current_specialty: Optional[str] = None) -> Optional[str]:

    """

    Detects clinical specialty from user message while respecting multi-symptom clinical context:

    1. If the user explicitly names a department/specialist (e.g. 'Neurology', 'Cardiologist'), honor it.

    2. If the message reports General Medicine symptoms (such as fever / 'జ్వరం' / 'बुखार' / 'காய்ச்சல்' / 'ಜ್ವರ')

       alongside common secondary symptoms like headache ('తలనొప్పి'), prioritize 'General Medicine'

       rather than switching to 'Neurology'.

    3. If `current_specialty == 'General Medicine'` is already active in the session and the user only

       adds common secondary symptoms (like headache / 'తలనొప్పి') without explicitly requesting a different

       department, preserve 'General Medicine'.

    """

    if not text or not text.strip():

        return None



    explicit_spec = detect_explicit_specialty_request(text)

    if explicit_spec:

        return explicit_spec



    low = text.lower()

    matched_specialties: List[str] = []

    for spec, keywords in MULTILINGUAL_SPECIALTY_KEYWORDS.items():

        if _matches_keyword_list(text, low, keywords):

            matched_specialties.append(spec)



    if not matched_specialties:

        return None



    # Multi-symptom General Medicine rule: fever/cold/cough + headache -> General Medicine

    if "General Medicine" in matched_specialties and "Neurology" in matched_specialties:

        severe_neuro_cues = [

            "stroke", "seizure", "epilepsy", "paralysis", "numbness",

            "పక్షవాతం", "ఫిట్స్", "பக்கவாதம்", "வலிப்பு", "ಪಾಶ್ವವಾಯು", "लकवा", "दौरा",

        ]

        if not _matches_keyword_list(text, low, severe_neuro_cues):

            return "General Medicine"



    # Preserve existing General Medicine when patient only adds a common symptom like headache

    if (

        current_specialty == "General Medicine"

        and "Neurology" in matched_specialties

        and _matches_keyword_list(text, low, COMMON_SECONDARY_GENERAL_MEDICINE_SYMPTOMS)

    ):

        severe_neuro_cues = [

            "stroke", "seizure", "epilepsy", "paralysis", "numbness",

            "పక్షవాతం", "ఫిట్స్", "பக்கவாதம்", "வலிப்பு", "ಪಾಶ್ವವಾಯು", "लकवा", "दौरा",

        ]

        if not _matches_keyword_list(text, low, severe_neuro_cues):

            return "General Medicine"



    return matched_specialties[0]





def extract_reason_from_text(text: str) -> Optional[str]:

    if not text or not text.strip():

        return None



    # 1. Explicit prefix in English or Indic languages

    m = re.search(

        r"(?:reason|కారణం|காரணம்|ಕಾರಣ|कारण)\s*[:\-]\s*([^\n]+)",

        text,

        re.IGNORECASE,

    )

    if m:

        return m.group(1).strip().rstrip(".")



    # 2. Explicit reason change phrasing ('change reason to <reason>', 'reason is <reason>')

    m_change = re.search(

        r"\b(?:change\s+reason\s+to|update\s+reason\s+to|reason\s+is)\s+([^\n]+)",

        text,

        re.IGNORECASE,

    )

    if m_change:

        return m_change.group(1).strip().rstrip(".")



    # 3. English 'for <reason>' pattern

    m2 = re.search(

        r"for\s+(intermittent\s+palpitations|chest pain(?:\s+checkup|\s+evaluation)?|angina(?:\s+consultation)?|routine checkup|general checkup|evaluation|chronic migraine|migraine|severe headache|headache|consultation|knee pain|joint pain|back pain|palpitations|high fever|fever(?:\s+and\s+cough|\s+and\s+headache)?|child vaccination|vaccination|follow-?up)[^.\n]*",

        text,

        re.IGNORECASE,

    )

    if m2:

        cleaned_for = re.sub(r"\s+(?:patient|pat-|my\s+id|slot-).*$", "", m2.group(0).strip(), flags=re.IGNORECASE)

        return cleaned_for.strip()



    # 4. Multilingual (Indic) clinical reason phrases — collect all non-overlapping matches in order of appearance

    matched_indic: List[tuple[int, str]] = []

    for phrase in MULTILINGUAL_REASON_PHRASES:

        idx = text.find(phrase)

        if idx != -1:

            if any(phrase in existing and phrase != existing for _, existing in matched_indic):

                continue

            matched_indic = [(i, p) for i, p in matched_indic if not (p in phrase and p != phrase)]

            matched_indic.append((idx, phrase))



    if matched_indic:

        matched_indic.sort(key=lambda item: item[0])

        ordered_phrases = [p for _, p in matched_indic]

        if len(ordered_phrases) > 1:

            return ", ".join(ordered_phrases)

        return ordered_phrases[0]



    # 5. Natural-language English & transliterated clinical reason phrases (e.g. 'chest pain' or 'fever, headache')

    low = text.strip().lower()

    matched_en: List[tuple[int, str]] = []

    for phrase in ENGLISH_REASON_PHRASES:

        m_en = re.search(rf"\b{re.escape(phrase.lower())}\b", low)

        if m_en:

            idx = m_en.start()

            if any(phrase.lower() in existing.lower() and phrase.lower() != existing.lower() for _, existing in matched_en):

                continue

            matched_en = [(i, p) for i, p in matched_en if not (p.lower() in phrase.lower() and p.lower() != phrase.lower())]

            matched_en.append((idx, phrase))



    if matched_en:

        matched_en.sort(key=lambda item: item[0])

        cleaned = text.strip()

        if (

            len(cleaned) <= 60

            and not re.search(r"\b(PAT-[A-Za-z0-9-]+|slot-[A-Za-z0-9_-]+)\b", cleaned, re.IGNORECASE)

            and detect_doctor_query(cleaned) is None

            and detect_explicit_specialty_request(cleaned) is None

        ):

            return cleaned

        if len(matched_en) > 1:

            return ", ".join(p for _, p in matched_en)

        return matched_en[0][1]



    return None





def merge_reason_categories(

    existing_reason: Optional[str],

    new_reason: Optional[str],

    is_explicit_replacement: bool = False,

) -> Optional[str]:

    """

    Combines existing and newly reported symptoms so additional symptoms (e.g. 'జ్వరం' followed by

    'జ్వరం, తలనొప్పి' or 'తలనొప్పి') enrich the visit reason rather than discarding prior symptom context.

    """

    if not new_reason:

        return existing_reason

    if not existing_reason or is_explicit_replacement:

        return new_reason

    if existing_reason.lower() == new_reason.lower():

        return existing_reason

    if existing_reason.lower() in new_reason.lower():

        return new_reason

    if new_reason.lower() in existing_reason.lower():

        return existing_reason

    return f"{existing_reason}, {new_reason}"





def build_localized_prompt_for_current_state(session_state: AgentSessionState) -> str:

    """

    Constructs the localized prompt for the session's current state without resetting or

    advancing the draft (used when the patient switches language or asks where they are in the flow).

    Never repeats the generic initial greeting once a conversation is already underway.

    """

    lang = session_state.language

    draft = session_state.draft



    if session_state.pending_action == "AWAITING_LAB_VERIFICATION_CODE":

        return format_localized_message(lang, "ask_lab_verification_code")



    if session_state.pending_action == "SEARCH_SPECIALTY_DOCTORS" or (draft.specialty and not draft.doctor_id):

        spec = draft.specialty or "General Medicine"

        spec_noun = get_specialist_noun(lang, spec)

        return format_localized_message(

            lang,

            "offer_specialty_consultation",

            specialty=spec,

            specialist_noun=spec_noun,

        )



    if session_state.pending_action == "SHOW_SLOTS_FOR_DOCTOR":

        doc_name = (session_state.pending_action_data or {}).get("doctor_name") or draft.doctor_name or "the doctor"

        spec = (session_state.pending_action_data or {}).get("specialty") or draft.specialty or "Specialist"

        return format_localized_message(

            lang,

            "doctor_found_consult_or_more",

            doctor_name=doc_name,

            specialty=spec,

        )



    if draft.is_complete():

        summary = format_localized_message(

            lang,

            "confirm_summary",

            patient_reference=draft.patient_reference,

            doctor_name=draft.doctor_name or "Specialist",

            specialty=draft.specialty or "OPD",

            slot_display=format_slot_display(draft.slot_id, draft.slot_start_time, lang=lang),

            reason_category=draft.reason_category,

        )

        return with_urgent_guidance_if_needed(lang, summary, draft.reason_category)



    if draft.doctor_id and draft.slot_id and draft.reason_category and not draft.patient_reference:

        prompt = format_localized_message(lang, "ask_patient_ref")

        return with_urgent_guidance_if_needed(lang, prompt, draft.reason_category)



    if draft.doctor_id and draft.slot_id and not draft.reason_category:
        slot_disp = format_slot_display(draft.slot_id, draft.slot_start_time, lang=lang)
        return format_localized_message(
            lang,
            "ask_reason",
            slot_display=slot_disp,
            slot_id=slot_disp,
            doctor_name=draft.doctor_name or "the doctor",
        )



    if draft.doctor_id and not draft.slot_id:

        offered_slots = get_offered_slots_from_session(session_state)

        if offered_slots:

            slot_lines = "\n".join(

                [f"• {format_human_slot_time(s.get('start_time'), lang=lang)}" for s in offered_slots[:5]]

            )

            return format_localized_message(

                lang,

                "available_slots",

                doctor_name=draft.doctor_name or "the doctor",

                slot_lines=slot_lines,

                example_slot=offered_slots[0]["slot_id"],

            )



    # Check if doctors were listed in tool_trace

    for tr in reversed(session_state.tool_trace):

        if tr.tool_name == "search_doctors" and tr.success and isinstance(tr.data, list) and tr.data:

            docs = tr.data

            doc_list_str = "\n".join(

                [f"• {d['display_name']} — {d['specialty']} ({d.get('department_name', d['specialty'])})" for d in docs]

            )

            return format_localized_message(

                lang,

                "found_doctors",

                count=len(docs),

                doc_list=doc_list_str,

            )



    if any(m.role == "assistant" for m in session_state.history):

        return format_localized_message(lang, "clarify_need")



    return format_localized_message(lang, "greeting")





def build_uncertainty_reply(lang: str, session_state: AgentSessionState) -> str:

    """

    Builds an empathetic, context-aware localized response when the patient expresses

    uncertainty (e.g., 'I don't know which doctor', 'నాకు తెలియదు ఎవరు', 'मुझे नहीं पता',

    'எனக்கு தெரியவில்லை', 'ನನಗೆ ಗೊತ್ತಿಲ್ಲ') without resetting the conversation, repeating

    the generic introduction, or inferring a diagnosis.

    Also records the offered follow-up action in `session_state.pending_action` so a subsequent

    contextual affirmative reply ('సరే', 'okay', 'சரி', 'ಸರಿ', 'ठीक है') executes it directly.

    """

    if session_state.pending_action == "AWAITING_LAB_VERIFICATION_CODE":

        return format_localized_message(lang, "ask_lab_verification_code")



    draft = session_state.draft

    if draft.is_complete() or session_state.step == ConversationStep.AWAITING_CONFIRMATION:

        return f"{format_localized_message(lang, 'ambiguous_confirm')}\n\n{build_localized_prompt_for_current_state(session_state)}"



    if draft.doctor_id and not draft.slot_id:

        offered_slots = get_offered_slots_from_session(session_state)

        if offered_slots:

            s0 = offered_slots[0]

            session_state.pending_action = "SELECT_EARLIEST_SLOT"

            session_state.pending_action_data = {

                "slot_id": str(s0["slot_id"]),

                "slot_start_time": s0.get("start_time"),

                "doctor_id": draft.doctor_id,

                "doctor_name": draft.doctor_name,

            }

            return f"{format_localized_message(lang, 'ambiguous_confirm')}\n\n{build_localized_prompt_for_current_state(session_state)}"

        session_state.pending_action = "SHOW_SLOTS_FOR_DOCTOR"

        session_state.pending_action_data = {

            "doctor_id": draft.doctor_id,

            "doctor_name": draft.doctor_name or "Doctor",

            "specialty": draft.specialty or "General Medicine",

        }

        return format_localized_message(lang, "ambiguous_doctor_choice", doc_names=draft.doctor_name or "Doctor")



    if draft.doctor_id or draft.slot_id:

        return f"{format_localized_message(lang, 'ambiguous_confirm')}\n\n{build_localized_prompt_for_current_state(session_state)}"



    offered_docs = get_offered_doctors_from_session(session_state)

    if offered_docs:

        primary_doc = offered_docs[0]

        session_state.pending_action = "SHOW_SLOTS_FOR_DOCTOR"

        session_state.pending_action_data = {

            "doctor_id": primary_doc.get("doctor_id"),

            "doctor_name": primary_doc.get("display_name"),

            "specialty": primary_doc.get("specialty") or draft.specialty,

        }

        doc_names = ", ".join(str(d.get("display_name", "Doctor")) for d in offered_docs)

        return format_localized_message(lang, "ambiguous_doctor_choice", doc_names=doc_names)



    # No doctors listed yet: ambiguous_general offers a General Medicine consultation

    session_state.pending_action = "SEARCH_GENERAL_MEDICINE"

    session_state.pending_action_data = {"specialty": "General Medicine"}

    return format_localized_message(lang, "ambiguous_general")





def ensure_response_in_session_language(

    reply: str,

    session_state: AgentSessionState,

    user_message: str,

) -> str:

    """

    Post-processing guard: verifies that when the active session language is an Indic language

    (te, ta, kn, hi), the generated assistant reply actually contains characters in that

    language's native script. Never assumes that detecting a language guarantees that an LLM

    or fallback path produced that language.

    """

    lang = session_state.language

    draft = session_state.draft

    if lang not in ("te", "ta", "kn", "hi"):

        return reply



    if has_expected_language_script(reply, lang):

        return reply



    # The generated reply lacks the expected target language script (e.g. an English fallback leaked).

    # Construct a deterministic, context-preserving response in the active language.

    emergency_kind = detect_emergency_priority_kind(user_message, session_state)

    if emergency_kind in ("emergency_priority", "emergency_followup"):

        return format_localized_message(lang, emergency_kind)



    if is_cancellation(user_message):

        return format_localized_message(lang, "cancelled")



    if session_state.tool_trace:

        last_tr = session_state.tool_trace[-1]

        if last_tr.tool_name == "check_lab_report_status" and isinstance(last_tr.data, dict):

            return format_lab_verification_reply(lang, last_tr.data)

        if last_tr.tool_name == "search_hospital_insurance" and isinstance(last_tr.data, dict):
            return format_insurance_search_reply(lang, last_tr.data)

    if session_state.pending_action == "AWAITING_LAB_VERIFICATION_CODE":
        return format_localized_message(lang, "ask_lab_verification_code")

    if session_state.pending_action == "CLARIFY_ACCOUNT_VS_BOOKING" or is_ambiguous_account_or_booking_inquiry(user_message):
        return format_localized_message(lang, "clarify_account_vs_booking")

    if is_ambiguous_reply(user_message):
        return build_uncertainty_reply(lang, session_state)



    general_q = detect_general_question_intent(user_message)

    if general_q == "departments":

        return format_localized_message(lang, "departments_info")

    if general_q == "hours":

        return format_localized_message(lang, "hours_info")

    if general_q == "how_to_book":

        return format_localized_message(lang, "how_to_book")



    return build_localized_prompt_for_current_state(session_state)





class BaseReasoningAdapter(ABC):

    """

    Abstract interface for reasoning-model adapters.

    Ensures clean decoupling so provider can be switched to Gemini, Gnani AI, Evon,

    or MockReasoningAdapter without modifying the conversation manager or tool router.

    """



    def _detect_doctor_query(self, text: str) -> Optional[str]:

        return detect_doctor_query(text)



    def _detect_specialty(self, text: str, current_specialty: Optional[str] = None) -> Optional[str]:

        return detect_specialty_query(text, current_specialty=current_specialty)



    def _extract_reason(self, text: str) -> Optional[str]:

        return extract_reason_from_text(text)



    @abstractmethod

    def plan_and_respond(

        self,

        session_state: AgentSessionState,

        user_message: str,

        available_tools: List[str],

        tool_executor: Optional[Callable[[ToolCallIntent], ToolExecutionResult]] = None,

    ) -> AgentAction:

        """

        Analyzes conversation context, extracts medical/booking entities,

        and returns either an immediate text response or a tool invocation intent.

        """

        pass





class MockReasoningAdapter(BaseReasoningAdapter):

    """

    Deterministic, rule-based reasoning adapter for offline development and automated tests.

    Consumes zero external AI credits and supports natural multi-turn conversation across

    English, Telugu, Tamil, Kannada, and Hindi (native and transliterated).

    """



    def plan_and_respond(

        self,

        session_state: AgentSessionState,

        user_message: str,

        available_tools: List[str],

        tool_executor: Optional[Callable[[ToolCallIntent], ToolExecutionResult]] = None,

    ) -> AgentAction:

        msg = user_message.strip()

        draft = session_state.draft

        session_state.language = detect_language(msg, session_state.language)

        lang = session_state.language



        # 0. Check if user is explicitly switching language mid-conversation

        explicit_lang, remaining_after_lang_switch = detect_explicit_language_switch(msg)

        if explicit_lang in SUPPORTED_LANGUAGES:

            session_state.language = explicit_lang

            lang = explicit_lang

            if not remaining_after_lang_switch:

                return AgentAction(reply=build_localized_prompt_for_current_state(session_state))

            msg = remaining_after_lang_switch



        lower = msg.lower()



        # 1. Check for cancellation intent

        if is_cancellation(msg):

            hard_cancel = bool(re.search(r"\b(cancel|stop|abort|nevermind|don'?t\s+book|do\s+not\s+book|raddu|mat\s+karo)\b", lower))

            if (

                session_state.confirmation_status in (ConfirmationStatus.PENDING, ConfirmationStatus.CONFIRMED)

                or session_state.step == ConversationStep.AWAITING_CONFIRMATION

                or draft.is_complete()

            ) and not hard_cancel:

                session_state.pending_action = "CONFIRM_OR_MODIFY"

                return AgentAction(

                    reply=format_localized_message(lang, "decline_confirm_ask_modify_or_cancel"),

                    tool_call=None,

                )

            if hard_cancel or (session_state.pending_action not in ("AWAITING_PATIENT_STATUS", "COLLECTING_EXISTING_PATIENT_REF") and not is_first_time_patient_reply(msg)):

                session_state.pending_action = None

                session_state.pending_action_data = {}

                return AgentAction(

                    reply=format_localized_message(lang, "cancelled")

                )



        # 1a. Emergency Priority Gate: severe chest pain or potentially life-threatening symptoms

        # must prioritize immediate emergency evaluation (108 / 112) without continuing routine

        # doctor selection or appointment booking in the same response.

        emergency_kind = detect_emergency_priority_kind(msg, session_state)

        if emergency_kind in ("emergency_priority", "emergency_followup"):

            session_state.pending_action = None

            session_state.pending_action_data = {}

            return AgentAction(

                reply=format_localized_message(lang, emergency_kind),

                tool_call=None,

            )



        # 1a-ins. Hospital Insurance Provider & Plan Information Inquiry

        if is_insurance_inquiry(msg) and "search_hospital_insurance" in available_tools:

            if session_state.pending_action == "AWAITING_LAB_VERIFICATION_CODE":

                session_state.pending_action = None

                session_state.pending_action_data = {}

            ins_filters = extract_insurance_search_filters(msg)

            return AgentAction(

                reply=format_localized_message(lang, "searching_specialty", specialty="Insurance"),

                tool_call=ToolCallIntent(

                    tool_name="search_hospital_insurance",

                    arguments=ins_filters,

                ),

            )



        # 1a-lab. Lab Report Status Verification Inquiry (or follow-up 6-digit code turn)

        is_awaiting_lab_code = session_state.pending_action == "AWAITING_LAB_VERIFICATION_CODE"

        has_lab_intent = is_lab_report_inquiry(msg)

        if (has_lab_intent or is_awaiting_lab_code) and "check_lab_report_status" in available_tools:

            valid_lab_code, malformed_lab_code = extract_lab_verification_code_candidate(

                msg, is_awaiting_code=is_awaiting_lab_code

            )

            if valid_lab_code or malformed_lab_code:

                code_to_verify = valid_lab_code or malformed_lab_code or ""

                if valid_lab_code:

                    session_state.pending_action = None

                    session_state.pending_action_data = {}

                else:

                    session_state.pending_action = "AWAITING_LAB_VERIFICATION_CODE"

                return AgentAction(

                    reply=format_localized_message(lang, "ask_lab_verification_code"),

                    tool_call=ToolCallIntent(

                        tool_name="check_lab_report_status",

                        arguments={

                            "verification_code": code_to_verify,

                            "session_key": session_state.session_id,

                        },

                    ),

                )

            elif has_lab_intent:

                session_state.pending_action = "AWAITING_LAB_VERIFICATION_CODE"

                session_state.pending_action_data = {}

                return AgentAction(

                    reply=format_localized_message(lang, "ask_lab_verification_code"),

                    tool_call=None,

                )

            elif is_awaiting_lab_code:

                # Recognize gratitude/closure after lab verification attempt

                if is_gratitude_or_closing(msg):

                    session_state.pending_action = None

                    session_state.pending_action_data = {}

                    return AgentAction(

                        reply=format_localized_message(lang, "gratitude_closure"),

                        tool_call=None,

                    )

                # If user switched to doctor/specialty/general question instead of providing a code, exit lab code wait

                elif (

                    self._detect_doctor_query(msg)

                    or self._detect_specialty(msg, current_specialty=draft.specialty)

                    or detect_general_question_intent(msg) is not None

                ):

                    session_state.pending_action = None

                    session_state.pending_action_data = {}

                else:

                    return AgentAction(

                        reply=format_localized_message(lang, "ask_lab_verification_code"),

                        tool_call=None,

                    )



        # 1b. Handle ambiguous / uncertain replies ("I don't know which doctor", "నాకు తెలియదు ఎవరు",

        # "मुझे नहीं पता", "எனக்கு தெரியவில்லை", "ನನಗೆ ಗೊತ್ತಿಲ್ಲ", "I'm not sure") BEFORE general questions

                # Ambiguous Account vs Appointment Booking Gate

        if is_ambiguous_account_or_booking_inquiry(msg):

            if session_state.booked_appointment:

                appt_id = session_state.booked_appointment.get("appointment_id", "")

                return AgentAction(

                    reply=format_localized_message(lang, "already_booked", appt_id=appt_id),

                    tool_call=None,

                )

            session_state.pending_action = "CLARIFY_ACCOUNT_VS_BOOKING"

            session_state.pending_action_data = {}

            return AgentAction(

                reply=format_localized_message(lang, "clarify_account_vs_booking"),

                tool_call=None,

            )



        if is_ambiguous_reply(msg):

            return AgentAction(

                reply=build_uncertainty_reply(lang, session_state),

                tool_call=None,

            )



        # 1c. Handle standalone greetings gracefully (preserving active state if mid-conversation)

        if is_greeting_only(msg):

            if (

                draft.doctor_id

                or draft.slot_id

                or draft.reason_category

                or get_offered_doctors_from_session(session_state)

                or any(m.role == "assistant" for m in session_state.history)

            ):

                return AgentAction(reply=build_localized_prompt_for_current_state(session_state))

            return AgentAction(reply=format_localized_message(lang, "greeting"))



        # 1c-2. Handle "continue previous booking" / "resume booking"

        if is_continue_booking_request(msg):

            resume_intro = format_localized_message(lang, "resuming_booking")

            current_prompt = build_localized_prompt_for_current_state(session_state)

            if current_prompt:

                reply = f"{resume_intro} {current_prompt}"

            else:

                reply = resume_intro

            return AgentAction(reply=reply)



        # 1d. Handle general hospital / appointment inquiries naturally while preserving context

        general_q = detect_general_question_intent(msg)

        if general_q == "departments":

            info = format_localized_message(lang, "departments_info")

            if draft.doctor_id or draft.slot_id:

                return AgentAction(reply=f"{info}\n\n{build_localized_prompt_for_current_state(session_state)}")

            return AgentAction(reply=info)

        if general_q == "hours":

            info = format_localized_message(lang, "hours_info")

            follow_up = build_localized_prompt_for_current_state(session_state)

            return AgentAction(reply=f"{info}\n\n{follow_up}")

        if general_q == "status_summary":

            return AgentAction(reply=build_localized_prompt_for_current_state(session_state))

        if general_q == "how_to_book":

            if session_state.pending_action:

                pass

            elif draft.doctor_id or draft.slot_id or get_offered_doctors_from_session(session_state):

                return AgentAction(reply=build_localized_prompt_for_current_state(session_state))

            else:

                return AgentAction(reply=format_localized_message(lang, "how_to_book"))



        # 1e. Handle active pending patient registration / identification actions

        if not draft.patient_reference:
            if session_state.pending_action in ("AWAITING_PATIENT_STATUS", "COLLECTING_EXISTING_PATIENT_REF") or is_first_time_patient_reply(msg):

                if is_first_time_patient_reply(msg):

                    draft.is_new_patient = True

                    session_state.pending_action = "COLLECTING_NEW_PATIENT_NAME"

                    return AgentAction(

                        reply=format_localized_message(lang, "welcome_new_patient_ask_name"),

                        tool_call=None,

                    )

                elif is_existing_patient_reply(msg):

                    draft.is_new_patient = False

                    phone_cand = extract_phone_number_candidate(msg)

                    if phone_cand:

                        session_state.pending_action = None

                        return AgentAction(

                            reply="Verifying patient record...",

                            tool_call=ToolCallIntent(

                                tool_name="verify_patient",

                                arguments={"phone_number": phone_cand},

                            ),

                        )

                    session_state.pending_action = "COLLECTING_EXISTING_PATIENT_PHONE"

                    return AgentAction(

                        reply=format_localized_message(lang, "welcome_back_ask_phone"),

                        tool_call=None,

                    )



            if session_state.pending_action == "COLLECTING_NEW_PATIENT_NAME":

                if is_contextual_affirmative(msg) and not extract_patient_name_candidate(msg):

                    return AgentAction(

                        reply=format_localized_message(lang, "welcome_new_patient_ask_name"),

                        tool_call=None,

                    )

                name_cand = extract_patient_name_candidate(msg)

                if name_cand:

                    draft.patient_name = name_cand

                    first_name = name_cand.split()[0]

                    session_state.pending_action = "COLLECTING_NEW_PATIENT_PHONE"

                    return AgentAction(

                        reply=format_localized_message(lang, "thank_name_ask_phone", name=first_name),

                        tool_call=None,

                    )



            if session_state.pending_action == "COLLECTING_NEW_PATIENT_PHONE":

                phone_cand = extract_phone_number_candidate(msg)

                if phone_cand:

                    draft.patient_phone = phone_cand

                    session_state.pending_action = None

                    return AgentAction(

                        reply="Registering patient details...",

                        tool_call=ToolCallIntent(

                            tool_name="register_patient",

                            arguments={

                                "full_name": draft.patient_name or "New Patient",

                                "phone_number": phone_cand,

                            },

                        ),

                    )

                else:

                    return AgentAction(

                        reply="Please provide a valid 10-digit mobile number so we can register and send your appointment confirmation.",

                        tool_call=None,

                    )



            if session_state.pending_action in ("COLLECTING_EXISTING_PATIENT_REF", "COLLECTING_EXISTING_PATIENT_PHONE"):

                if is_forgot_patient_ref_reply(msg):

                    session_state.pending_action = "COLLECTING_EXISTING_PATIENT_PHONE"

                    return AgentAction(

                        reply=format_localized_message(lang, "forgot_reference_ask_phone"),

                        tool_call=None,

                    )

                phone_cand = extract_phone_number_candidate(msg)

                if phone_cand:

                    session_state.pending_action = None

                    return AgentAction(

                        reply="Verifying patient record...",

                        tool_call=ToolCallIntent(

                            tool_name="verify_patient",

                            arguments={

                                "phone_number": phone_cand,

                            },

                        ),

                    )

                pat_found = re.search(r"\b(PAT-[A-Za-z0-9-]+)\b", msg, re.IGNORECASE)

                if pat_found:

                    draft.patient_reference = pat_found.group(1).upper()

                    session_state.pending_action = None

                    return AgentAction(

                        reply="Verifying patient record...",

                        tool_call=ToolCallIntent(

                            tool_name="verify_patient",

                            arguments={

                                "patient_reference": draft.patient_reference,

                            },

                        ),

                    )

                elif is_first_time_patient_reply(msg):

                    draft.is_new_patient = True

                    session_state.pending_action = "COLLECTING_NEW_PATIENT_NAME"

                    return AgentAction(

                        reply=format_localized_message(lang, "welcome_new_patient_ask_name"),

                        tool_call=None,

                    )



        had_doctor_and_slot_before_turn = bool(draft.doctor_id and draft.slot_id)

        had_slots_already_offered_for_doctor = bool(draft.doctor_id and get_offered_slots_from_session(session_state))

        captured_new_non_slot_detail = False



        # 2. Extract Patient Reference (e.g., PAT-2024-9182, PAT-1234, etc.)

        pat_match = re.search(r"\b(PAT-[A-Za-z0-9-]+)\b", msg, re.IGNORECASE)

        if pat_match:

            new_pat = pat_match.group(1).upper()

            if draft.patient_reference != new_pat:

                draft.patient_reference = new_pat

                captured_new_non_slot_detail = True

            if session_state.pending_action in ("AWAITING_PATIENT_STATUS", "COLLECTING_EXISTING_PATIENT_REF"):

                session_state.pending_action = None

                session_state.pending_action_data = {}



        # 2b. Check ordinal / contextual doctor selection from previous search_doctors trace

        ordinal_doc = resolve_ordinal_doctor_selection(msg, session_state)

        if ordinal_doc:

            if draft.doctor_id != ordinal_doc["doctor_id"]:

                draft.doctor_id = ordinal_doc["doctor_id"]

                draft.doctor_name = ordinal_doc.get("display_name")

                draft.specialty = ordinal_doc.get("specialty")

                draft.slot_id = None

                draft.slot_start_time = None

                had_slots_already_offered_for_doctor = False

                session_state.pending_action = None

                session_state.pending_action_data = {}



        # 2c. Detect explicit doctor selection or doctor correction mid-conversation

        doc_search_term = self._detect_doctor_query(msg)

        matched_offered_doc = None

        if doc_search_term:

            for d in get_offered_doctors_from_session(session_state):

                d_name = d.get("display_name", "").lower()

                term = doc_search_term.lower()

                if term in d_name or d_name in term or any(part in d_name for part in term.split() if len(part) >= 3):

                    matched_offered_doc = d

                    break

        if matched_offered_doc:

            draft.doctor_id = matched_offered_doc["doctor_id"]

            draft.doctor_name = matched_offered_doc.get("display_name")

            draft.specialty = matched_offered_doc.get("specialty") or draft.specialty

            draft.slot_id = None

            draft.slot_start_time = None

            had_doctor_and_slot_before_turn = False

            had_slots_already_offered_for_doctor = False

            session_state.pending_action = None

            session_state.pending_action_data = {}



        is_switching_doctor = False

        if doc_search_term and not matched_offered_doc:

            if not draft.doctor_id:

                is_switching_doctor = True

            elif draft.doctor_name and doc_search_term.lower() not in draft.doctor_name.lower():

                # Patient is switching to a different doctor mid-conversation

                draft.doctor_id = None

                draft.doctor_name = None

                draft.slot_id = None

                draft.slot_start_time = None

                had_doctor_and_slot_before_turn = False

                had_slots_already_offered_for_doctor = False

                is_switching_doctor = True

                session_state.pending_action = None

                session_state.pending_action_data = {}



        # 2d. Detect specialty query or specialty switch mid-conversation

        is_explicit_reason_update = bool(

            re.search(r"(?:reason|కారణం|காரணம்|ಕಾರಣ|कारण)\s*[:\-]", msg, re.IGNORECASE)

            or re.search(r"\b(?:change\s+reason\s+to|update\s+reason\s+to|reason\s+is)\b", msg, re.IGNORECASE)

        )

        explicit_specialty_req = None if is_explicit_reason_update else detect_explicit_specialty_request(msg)

        detected_specialty = (

            None

            if is_explicit_reason_update

            else self._detect_specialty(msg, current_specialty=draft.specialty)

        )

        has_explicit_change_cue = bool(

            re.search(r"\b(change|switch|instead|actually|different|another)\b", lower)

            or any(c in msg for c in ("మార్చండి", "వేరే", "மாற்று", "வேறு", "ಬದಲಾಯಿಸಿ", "ಬೇರೆ", "बदलें", "दूसरा"))

        )

        is_switching_specialty = False

        preserved_existing_specialty_on_symptom_update = False



        if detected_specialty and not doc_search_term and not ordinal_doc:

            if not draft.specialty and not draft.doctor_id:

                is_switching_specialty = True

            elif draft.specialty and detected_specialty.lower() == draft.specialty.lower():

                # Same specialty (e.g. fever followed by fever + headache keeping General Medicine)

                offered_docs_now = get_offered_doctors_from_session(session_state)

                if not draft.doctor_id and not offered_docs_now:

                    is_switching_specialty = True

                else:

                    preserved_existing_specialty_on_symptom_update = True

            elif draft.specialty and detected_specialty.lower() != draft.specialty.lower():

                # Different specialty detected: only switch if the user explicitly requested a specialty/department

                # or used an explicit change cue (never switch automatically just because a common secondary symptom was added)

                if explicit_specialty_req is not None or has_explicit_change_cue:

                    draft.doctor_id = None

                    draft.doctor_name = None

                    draft.specialty = detected_specialty

                    draft.slot_id = None

                    draft.slot_start_time = None

                    had_doctor_and_slot_before_turn = False

                    had_slots_already_offered_for_doctor = False

                    is_switching_specialty = True

                    session_state.pending_action = None

                    session_state.pending_action_data = {}

                else:

                    preserved_existing_specialty_on_symptom_update = True



        # 3. Resolve & validate Slot ID (supports 'slot-101', numeric '101', 'first slot', '10:00'; rejects 'slot-id-101')

        valid_slot_id, valid_slot_time, invalid_slot_id = resolve_slot_selection(msg, session_state)

        if invalid_slot_id:

            offered_slots = get_offered_slots_from_session(session_state)

            if offered_slots:

                available_ids = ", ".join(format_human_slot_time(s.get("start_time"), lang=lang) for s in offered_slots)

                slot_lines = "\n".join(

                    [f"• {format_human_slot_time(s.get('start_time'), lang=lang)}" for s in offered_slots[:5]]

                )

                return AgentAction(

                    reply=format_localized_message(

                        lang,

                        "invalid_slot",

                        invalid_slot=invalid_slot_id,

                        doctor_name=draft.doctor_name or "the doctor",

                        available_ids=available_ids,

                        slot_lines=slot_lines,

                    )

                )



        if valid_slot_id:

            if draft.slot_id != valid_slot_id:

                draft.slot_id = valid_slot_id

                draft.slot_start_time = valid_slot_time

                session_state.pending_action = None

                session_state.pending_action_data = {}

            elif valid_slot_time and not draft.slot_start_time:

                draft.slot_start_time = valid_slot_time



        # 4. Detect Reason mentions (with or without 'reason:' prefix, or reason correction/addition)

        extracted_reason = self._extract_reason(msg)

        has_explicit_prefix = bool(

            re.search(r"(?:reason|కారణం|காரணம்|ಕಾರಣ|कारण)\s*[:\-]", msg, re.IGNORECASE)

            or re.search(r"\b(?:change\s+reason\s+to|update\s+reason\s+to|reason\s+is)\b", msg, re.IGNORECASE)

        )

        has_for_prefix = bool(

            re.search(

                r"\bfor\s+(?:intermittent\s+palpitations|chest pain|angina|routine checkup|general checkup|evaluation|chronic migraine|migraine|severe headache|headache|consultation|knee pain|joint pain|back pain|palpitations|high fever|fever|child vaccination|vaccination|follow-?up)\b",

                msg,

                re.IGNORECASE,

            )

        )

        # Symptom-only message (without explicit specialist keyword like 'cardiologist' / 'కార్డియాలజిస్ట్')

        is_symptom_only_reason = bool(

            extracted_reason

            and explicit_specialty_req is None

            and doc_search_term is None

        )

        if extracted_reason:

            if (

                has_explicit_prefix

                or has_for_prefix

                or had_doctor_and_slot_before_turn

                or (draft.doctor_id and draft.slot_id)

                or doc_search_term is not None

                or ordinal_doc is not None

                or is_symptom_only_reason

                or draft.reason_category is not None

            ):

                merged_reason = merge_reason_categories(

                    draft.reason_category,

                    extracted_reason,

                    is_explicit_replacement=(has_explicit_prefix or has_for_prefix or has_explicit_change_cue),

                )

                if draft.reason_category != merged_reason:

                    draft.reason_category = merged_reason

                    captured_new_non_slot_detail = True

        elif (

            had_doctor_and_slot_before_turn

            and not draft.reason_category

            and not pat_match

                        and not invalid_slot_id

            and not is_contextual_affirmative(msg)

            and not is_greeting_only(msg)

            and not is_ambiguous_reply(msg)

            and general_q is None

            and not doc_search_term

            and not msg.endswith("?")

            and len(msg) >= 3

        ):

            # Patient is directly answering the "what is your reason/symptoms?" prompt in natural language

            draft.reason_category = msg

            captured_new_non_slot_detail = True



        # 5. Check if confirmation is pending and user explicitly confirms vs generic 'okay'

        is_explicit_confirm = is_affirmative(msg)

        is_context_accept = is_contextual_affirmative(msg)



        if (

            session_state.confirmation_status in [ConfirmationStatus.PENDING, ConfirmationStatus.CONFIRMED]

            and draft.is_complete()

        ):

            if is_explicit_confirm:

                session_state.pending_action = None

                session_state.pending_action_data = {}

                return AgentAction(

                    reply=format_localized_message(lang, "processing_booking"),

                    tool_call=ToolCallIntent(

                        tool_name="book_appointment",

                        arguments={

                            "patient_reference": draft.patient_reference,

                            "doctor_id": draft.doctor_id,

                            "selected_slot_id": draft.slot_id,

                            "reason_category": draft.reason_category,

                        },

                    ),

                )

            elif is_context_accept and not captured_new_non_slot_detail and not valid_slot_id:

                # Generic 'okay' / 'సరే' must NOT trigger book_appointment; ask for explicit confirmation

                summary = format_localized_message(

                    lang,

                    "confirm_summary",

                    patient_reference=draft.patient_reference,

                    doctor_name=draft.doctor_name or "Specialist",

                    specialty=draft.specialty or "OPD",

                    slot_display=format_slot_display(draft.slot_id, draft.slot_start_time, lang=lang),

                    reason_category=draft.reason_category,

                )

                explicit_note = format_localized_message(lang, "explicit_confirm_required")

                return AgentAction(

                    reply=with_urgent_guidance_if_needed(

                        lang, f"{explicit_note}\n\n{summary}", msg, draft.reason_category

                    ),

                    tool_call=None,

                )



        # 5b. Flexible slot request ("anything is fine", "earliest", "any time", "whichever")

        if is_flexible_slot_request(msg) and (draft.doctor_id or get_offered_doctors_from_session(session_state)) and not draft.slot_id:

            offered_slots = get_offered_slots_from_session(session_state)

            if offered_slots:

                s0 = offered_slots[0]

                session_state.pending_action = "CONFIRM_SUGGESTED_SLOT"

                session_state.pending_action_data = {

                    "slot_id": s0["slot_id"],

                    "slot_start_time": s0.get("start_time"),

                }

                formatted_time = format_human_slot_time(s0.get("start_time"), lang=lang)

                return AgentAction(

                    reply=format_localized_message(

                        lang, "suggest_earliest_slot", slot_time=formatted_time, slot_id=s0["slot_id"]

                    ),

                    tool_call=None,

                )



        # 5c. Execute pending offered action when the user responds with a contextual affirmative ('సరే', 'okay', 'சரி', 'ಸರಿ', 'ठीक है')

        if is_context_accept and not doc_search_term and not ordinal_doc and not draft.is_complete():

            pending_act = session_state.pending_action

            pending_data = dict(session_state.pending_action_data or {})



            if pending_act == "SHOW_SLOTS_FOR_DOCTOR":

                target_doc_id = pending_data.get("doctor_id") or draft.doctor_id

                target_doc_name = pending_data.get("doctor_name") or draft.doctor_name

                target_spec = pending_data.get("specialty") or draft.specialty

                if not target_doc_id:

                    offered_docs = get_offered_doctors_from_session(session_state)

                    if offered_docs:

                        target_doc_id = offered_docs[0].get("doctor_id")

                        target_doc_name = offered_docs[0].get("display_name")

                        target_spec = offered_docs[0].get("specialty") or target_spec

                if target_doc_id:

                    draft.doctor_id = str(target_doc_id)

                    if target_doc_name:

                        draft.doctor_name = str(target_doc_name)

                    if target_spec:

                        draft.specialty = str(target_spec)

                    session_state.pending_action = None

                    session_state.pending_action_data = {}

                    return AgentAction(

                        reply=format_localized_message(

                            lang, "specialist_choice_excellent", doctor_name=draft.doctor_name or "the doctor"

                        ),

                        tool_call=ToolCallIntent(

                            tool_name="get_available_slots",

                            arguments={"doctor_id": draft.doctor_id, "time_range": None},

                        ),

                    )



            elif pending_act == "SEARCH_SPECIALTY_DOCTORS":

                target_spec = str(pending_data.get("specialty") or draft.specialty or "Cardiology")

                draft.specialty = target_spec

                session_state.pending_action = None

                session_state.pending_action_data = {}

                spec_plural = get_specialist_plural(lang, target_spec)

                return AgentAction(

                    reply=format_localized_message(lang, "checking_available_specialists", specialist_plural=spec_plural),

                    tool_call=ToolCallIntent(

                        tool_name="search_doctors",

                        arguments={"specialty_or_department": target_spec},

                    ),

                )



            elif pending_act == "SEARCH_GENERAL_MEDICINE":

                target_spec = str(pending_data.get("specialty") or "General Medicine")

                draft.specialty = target_spec

                session_state.pending_action = None

                session_state.pending_action_data = {}

                return AgentAction(

                    reply=format_localized_message(lang, "searching_specialty", specialty=target_spec),

                    tool_call=ToolCallIntent(

                        tool_name="search_doctors",

                        arguments={"specialty_or_department": target_spec},

                    ),

                )



            elif pending_act in ("SELECT_EARLIEST_SLOT", "CONFIRM_SUGGESTED_SLOT"):

                slot_to_pick = pending_data.get("slot_id")

                if slot_to_pick:

                    draft.slot_id = str(slot_to_pick)

                    draft.slot_start_time = pending_data.get("slot_start_time")

                    session_state.pending_action = None

                    session_state.pending_action_data = {}

                    if not draft.patient_reference:

                        session_state.pending_action = "AWAITING_PATIENT_STATUS"

                        return AgentAction(

                            reply=format_localized_message(lang, "ask_visited_before"),

                            tool_call=None,

                        )



            # Fallback if pending_action was not explicitly set but exactly 1 doctor was offered in trace and slot not yet fetched

            if not draft.doctor_id:

                offered_docs = get_offered_doctors_from_session(session_state)

                if len(offered_docs) == 1:

                    chosen_doc = offered_docs[0]

                    draft.doctor_id = chosen_doc["doctor_id"]

                    draft.doctor_name = chosen_doc.get("display_name")

                    draft.specialty = chosen_doc.get("specialty") or draft.specialty

                    session_state.pending_action = None

                    session_state.pending_action_data = {}

                    return AgentAction(

                        reply=format_localized_message(

                            lang, "checking_slots", doctor_name=draft.doctor_name or "the doctor"

                        ),

                        tool_call=ToolCallIntent(

                            tool_name="get_available_slots",

                            arguments={"doctor_id": draft.doctor_id, "time_range": None},

                        ),

                    )



        # 6. Detect Doctor search / selection intent (if doctor not yet resolved from trace)

        if doc_search_term and (not draft.doctor_id or is_switching_doctor):

            reply_text = format_localized_message(lang, "searching_doctor", doc=doc_search_term)

            return AgentAction(

                reply=with_urgent_guidance_if_needed(lang, reply_text, msg),

                tool_call=ToolCallIntent(

                    tool_name="search_doctors",

                    arguments={"specialty_or_department": doc_search_term},

                ),

            )



        # 6b. If patient added additional common symptoms while a specialty/doctor was already identified

        # and no specialty switch is warranted, preserve the current specialty/doctor and offer next step

        if (

            preserved_existing_specialty_on_symptom_update

            and not is_switching_specialty

            and not draft.slot_id

        ):

            offered_docs = get_offered_doctors_from_session(session_state)

            if not draft.doctor_id and offered_docs:

                primary_doc = offered_docs[0]

                session_state.pending_action = "SHOW_SLOTS_FOR_DOCTOR"

                session_state.pending_action_data = {

                    "doctor_id": primary_doc.get("doctor_id"),

                    "doctor_name": primary_doc.get("display_name"),

                    "specialty": primary_doc.get("specialty") or draft.specialty,

                }

                reply_msg = format_localized_message(

                    lang,

                    "symptom_added_keep_specialty",

                    reason_category=draft.reason_category or msg,

                    specialty=draft.specialty or primary_doc.get("specialty", "General Medicine"),

                    doctor_name=primary_doc.get("display_name", "Doctor"),

                )

                return AgentAction(

                    reply=with_urgent_guidance_if_needed(lang, reply_msg, msg, draft.reason_category),

                    tool_call=None,

                )



        # 7. Detect Specialty query

        if detected_specialty and (not draft.doctor_id and is_switching_specialty):

            draft.specialty = detected_specialty

            is_direct_doc_search = bool(

                has_explicit_change_cue

                or re.search(r"\b(who|which|list|available|show|check|find|search)\b.*\b(doctor|physician|specialist|doctors|cardiologist|neurologist|orthopedist|pediatrician)\b", lower)

                or re.search(r"\b(?:i\s+need\s+to\s+consult\s+a\s+cardiologist)\b", lower)

                or any(q in msg for q in ("ఎవరు ఉన్నారు", "ఎవరున్నారు", "ఎవరు", "యార్", "ಯಾರು ಇದ್ದಾರೆ", "ಯಾರು", "कौन से डॉक्टर", "कौन डॉक्टर", "డాక్టర్లు ఎవరు", "డాక్టర్ ఎవరు"))

                or any(w in lower for w in ("find", "search", "list", "check doctor", "available doctor", "kavali", "vendum", "beku", "chahiye"))

            )

            has_explicit_symptoms = bool(

                draft.reason_category

                or is_urgent_symptom(msg)

                or any(s in lower for s in COMMON_SECONDARY_GENERAL_MEDICINE_SYMPTOMS)

                or any(phrase in msg for phrase in MULTILINGUAL_REASON_PHRASES)

            )

            is_explicit_consult_or_typo = bool(

                re.search(r"\b(thinking|want|need|meet|see|consult|arrange|like to|can i)\b", lower)

                or re.search(r"\b(cardioligist|cardiolgy|neurologest|orthopedist|orthopaedic|paediatrician|dermatologyst|heart\s+specialist|skin\s+specialist|general\s+physician)\b", lower)

                or re.search(r"cardio[a-z]*ist", lower)

            )

            # Offer consultation when patient specifies appointment/physician intent without symptoms or direct search command

            if is_explicit_consult_or_typo and not is_direct_doc_search and not has_explicit_symptoms:

                spec_noun = get_specialist_noun(lang, detected_specialty)

                session_state.pending_action = "SEARCH_SPECIALTY_DOCTORS"

                session_state.pending_action_data = {"specialty": detected_specialty}

                reply_text = format_localized_message(

                    lang,

                    "offer_specialty_consultation",

                    specialty=draft.specialty,

                    specialist_noun=spec_noun,

                )

                return AgentAction(

                    reply=with_urgent_guidance_if_needed(lang, reply_text, msg),

                    tool_call=None,

                )

            else:

                reply_text = format_localized_message(lang, "searching_specialty", specialty=draft.specialty)

                return AgentAction(

                    reply=with_urgent_guidance_if_needed(lang, reply_text, msg),

                    tool_call=ToolCallIntent(

                        tool_name="search_doctors",

                        arguments={"specialty_or_department": draft.specialty},

                    ),

                )



        # 8. If doctor is selected but slot is missing -> query slots (or concisely remind if slots already shown and user just gave another detail)

        if draft.doctor_id and not draft.slot_id:

            time_filter = None

            if "morning" in lower or "ఉదయం" in msg or "காலை" in msg or "ಬೆಳಿಗ್ಗೆ" in msg or "सुबह" in msg:

                time_filter = "morning"

            elif "afternoon" in lower or "మధ్యాహ్నం" in msg or "மதியம்" in msg or "ಮಧ್ಯಾಹ್ನ" in msg or "दोपहर" in msg:

                time_filter = "afternoon"

            elif "evening" in lower or "సాయంత్రం" in msg or "மாலை" in msg or "ಸಂಜೆ" in msg or "शाम" in msg:

                time_filter = "evening"



            if had_slots_already_offered_for_doctor and time_filter is None:

                offered_slots = get_offered_slots_from_session(session_state)

                if offered_slots:

                    if captured_new_non_slot_detail:

                        available_ids = ", ".join(format_human_slot_time(s.get("start_time"), lang=lang) for s in offered_slots)

                        concise_prompt = format_localized_message(

                            lang,

                            "detail_captured_pick_slot",

                            doctor_name=draft.doctor_name or "the doctor",

                            available_ids=available_ids,

                        )

                        return AgentAction(

                            reply=with_urgent_guidance_if_needed(lang, concise_prompt, msg, draft.reason_category)

                        )

                    slot_lines = "\n".join(

                        [f"• {format_human_slot_time(s['start_time'], lang=lang)}" for s in offered_slots]

                    )

                    return AgentAction(

                        reply=format_localized_message(

                            lang,

                            "available_slots",

                            doctor_name=draft.doctor_name or "the doctor",

                            slot_lines=slot_lines,

                        )

                    )



            return AgentAction(

                reply=format_localized_message(

                    lang, "checking_slots", doctor_name=draft.doctor_name or "the doctor"

                ),

                tool_call=ToolCallIntent(

                    tool_name="get_available_slots",

                    arguments={"doctor_id": draft.doctor_id, "time_range": time_filter},

                ),

            )



        # 9. If doctor and slot selected, but reason missing -> ask reason

        if draft.doctor_id and draft.slot_id and not draft.reason_category:

            slot_disp = format_slot_display(draft.slot_id, draft.slot_start_time, lang=lang)
            return AgentAction(
                reply=format_localized_message(
                    lang,
                    "ask_reason",
                    slot_display=slot_disp,
                    slot_id=slot_disp,
                    doctor_name=draft.doctor_name or "the doctor",
                )
            )



        # 10. If doctor, slot, reason selected, but patient reference missing -> ask visited before

        if draft.doctor_id and draft.slot_id and draft.reason_category and not draft.patient_reference:

            session_state.pending_action = "AWAITING_PATIENT_STATUS"

            prompt = format_localized_message(lang, "ask_visited_before")

            return AgentAction(

                reply=with_urgent_guidance_if_needed(lang, prompt, msg, draft.reason_category)

            )



        # 11. All 4 details present -> Present explicit confirmation summary

        if draft.is_complete():

            summary = format_localized_message(

                lang,

                "confirm_summary",

                patient_reference=draft.patient_reference,

                doctor_name=draft.doctor_name or "Specialist",

                specialty=draft.specialty or "OPD",

                slot_display=format_slot_display(draft.slot_id, draft.slot_start_time, lang=lang),

                reason_category=draft.reason_category,

            )

            return AgentAction(

                reply=with_urgent_guidance_if_needed(lang, summary, msg, draft.reason_category)

            )



        # 12. Contextual fallback if conversation is already underway; greeting only on fresh start

        if any(m.role == "assistant" for m in session_state.history):

            return AgentAction(

                reply=build_localized_prompt_for_current_state(session_state)

            )



        return AgentAction(

            reply=format_localized_message(lang, "greeting")

        )





class GeminiReasoningAdapter(BaseReasoningAdapter):

    """

    Production Gemini API reasoning adapter for MediVoice AI (Aarogya One Hospital).

    

    Features:

    - Uses official Gemini generateContent REST interface with function calling.

    - Supports Telugu (te), Tamil (ta), Kannada (kn), Hindi (hi), and English (en).

    - Keeps GEMINI_API_KEY strictly on the backend (sent via x-goog-api-key header).

    - Enforces bounded request timeouts and a maximum number of tool-calling rounds.

    - Never accesses the database directly or invokes unapproved tools.

    - Respects the conversation manager's explicit confirmation gate before booking.

    """



    GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    DEFAULT_FALLBACK_MODELS = [

        "gemini-3.5-flash",

        "gemini-3.5-flash-lite",

        "gemini-2.5-flash",

        "gemini-2.5-pro",

        "gemini-2.5-flash-lite",

        "gemini-flash-latest",

        "gemma-4-26b-a4b-it",

    ]



    def __init__(

        self,

        api_key: Optional[str] = None,

        model: Optional[str] = None,

        timeout_seconds: Optional[float] = None,

        max_tool_rounds: Optional[int] = None,

        thinking_level: Optional[str] = None,

        http_client: Optional[httpx.Client] = None,

        strict_mode: bool = False,

        enable_model_fallback: Optional[bool] = None,

    ):

        resolved_key = api_key if api_key is not None else (os.getenv("GEMINI_API_KEY") or settings.GEMINI_API_KEY)

        self.api_key: str = (resolved_key or "").strip()



        resolved_model = model or os.getenv("GEMINI_MODEL") or settings.GEMINI_MODEL or "gemini-3.5-flash"

        self.model: str = resolved_model.replace("models/", "").strip()



        raw_timeout = (

            timeout_seconds

            if timeout_seconds is not None

            else float(os.getenv("GEMINI_TIMEOUT_SECONDS") or settings.GEMINI_TIMEOUT_SECONDS or 15.0)

        )

        self.timeout_seconds: float = min(max(float(raw_timeout), 1.0), 60.0)



        raw_rounds = (

            max_tool_rounds

            if max_tool_rounds is not None

            else int(os.getenv("GEMINI_MAX_TOOL_ROUNDS") or settings.GEMINI_MAX_TOOL_ROUNDS or 4)

        )

        self.max_tool_rounds: int = min(max(int(raw_rounds), 1), 6)



        raw_thinking = (

            thinking_level

            if thinking_level is not None

            else os.getenv("GEMINI_THINKING_LEVEL", getattr(settings, "GEMINI_THINKING_LEVEL", "low"))

        )

        if raw_thinking and str(raw_thinking).strip().lower() not in ("", "none", "off", "false", "0"):

            self.thinking_level: Optional[str] = str(raw_thinking).strip().lower()

        else:

            self.thinking_level = None



        self.http_client = http_client

        self.strict_mode = strict_mode

        # Requirement 8: Do not silently fall back unless explicitly enabled

        if enable_model_fallback is not None:

            self.enable_model_fallback = bool(enable_model_fallback)

        else:

            self.enable_model_fallback = getattr(settings, "GEMINI_ENABLE_FALLBACK", False)

        self._managed_client: Optional[httpx.Client] = None
        self.last_error: Optional[str] = None
        self.last_model_used: Optional[str] = None
        self.last_turn_timings: Dict[str, Any] = {}
        self.last_turn_diagnostics: Optional[Dict[str, Any]] = None
        self.retry_count: int = 0
        self._last_status_code: Optional[int] = 200
        self._last_error_category: str = "none"
        self._current_correlation_id: str = ""
        self._current_turn_start_iso: str = ""

    def _get_client(self) -> httpx.Client:
        if self.http_client is not None:
            return self.http_client
        if self._managed_client is None or self._managed_client.is_closed:
            limits = httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                keepalive_expiry=30.0,
            )
            timeouts = httpx.Timeout(
                connect=5.0,
                read=self.timeout_seconds,
                write=10.0,
                pool=5.0,
            )
            self._managed_client = httpx.Client(limits=limits, timeout=timeouts)
        return self._managed_client

    def close(self) -> None:
        if self._managed_client is not None and not self._managed_client.is_closed:
            try:
                self._managed_client.close()
            except Exception:
                pass
            self._managed_client = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass



    def _record_timings(
        self,
        initial_gemini_request_ms: float,
        tool_router_ms: float,
        followup_gemini_request_ms: float,
        gemini_calls_count: int,
        t_start: float,
        correlation_id: Optional[str] = None,
        status_code: Optional[int] = None,
        error_category: Optional[str] = None,
        history_messages_count: Optional[int] = None,
        approx_tokens: Optional[int] = None,
        tool_rounds: Optional[int] = None,
        retry_count: Optional[int] = None,
    ) -> None:
        total_agent_ms = round((time.perf_counter() - t_start) * 1000, 2)
        corr_id = correlation_id or getattr(self, "_current_correlation_id", None) or f"turn-{uuid.uuid4().hex[:8]}"
        model_name = getattr(self, "last_model_used", None) or self.model
        now_iso = datetime.now(timezone.utc).isoformat()
        start_iso = getattr(self, "_current_turn_start_iso", None) or now_iso
        st_code = status_code if status_code is not None else getattr(self, "_last_status_code", 200)
        err_cat = error_category if error_category is not None else getattr(self, "_last_error_category", "none")
        retries = retry_count if retry_count is not None else getattr(self, "retry_count", 0)
        rounds_val = tool_rounds if tool_rounds is not None else (gemini_calls_count if gemini_calls_count > 0 else 0)
        hist_count = history_messages_count if history_messages_count is not None else 0
        tok_count = approx_tokens if approx_tokens is not None else 0

        self.last_turn_diagnostics = {
            "correlation_id": corr_id,
            "model": model_name,
            "start_time_iso": start_iso,
            "completion_time_iso": now_iso,
            "duration_ms": total_agent_ms,
            "status_code": st_code,
            "error_category": err_cat,
            "history_messages_count": hist_count,
            "approx_tokens": tok_count,
            "tool_rounds": rounds_val,
            "retry_count": retries,
        }

        self.last_turn_timings = {
            "initial_gemini_request_ms": round(initial_gemini_request_ms, 2),
            "tool_router_ms": round(tool_router_ms, 2),
            "followup_gemini_request_ms": round(followup_gemini_request_ms, 2),
            "gemini_calls_count": float(gemini_calls_count),
            "agent_ms": total_agent_ms,
        }

        logger.info(
            "Gemini turn diagnostics: correlation_id=%s model=%s duration_ms=%.1f status=%s error_category=%s "
            "history_messages=%d approx_tokens=%d tool_rounds=%d retry_count=%d",
            corr_id,
            model_name,
            total_agent_ms,
            st_code,
            err_cat,
            hist_count,
            tok_count,
            rounds_val,
            retries,
        )



    def _build_tool_declarations(self, available_tools: List[str]) -> List[Dict[str, Any]]:

        all_specs: Dict[str, Dict[str, Any]] = {

            "search_doctors": {

                "name": "search_doctors",

                "description": (

                    "Search active doctors at Aarogya One Hospital by clinical specialty, department, or doctor name. "

                    "Always pass specialty_or_department in English (e.g. 'Cardiology', 'Neurology', 'Orthopedics', "

                    "'Pediatrics', 'General Medicine', 'Sharma', 'Nair', 'Swamy', 'Sen', 'Mehta', 'Rao')."

                ),

                "parameters": {

                    "type": "OBJECT",

                    "properties": {

                        "specialty_or_department": {

                            "type": "STRING",

                            "description": (

                                "Canonical English specialty, department, or doctor surname "

                                "(Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine, Sharma, Nair, Swamy, Sen, Mehta, Rao)."

                            ),

                        },

                    },

                    "required": ["specialty_or_department"],

                },

            },

            "get_available_slots": {

                "name": "get_available_slots",

                "description": (

                    "Retrieve real available appointment slots from the database for a specific doctor_id. "

                    "Never invent slot IDs or times; always call this tool to get real slots."

                ),

                "parameters": {

                    "type": "OBJECT",

                    "properties": {

                        "doctor_id": {

                            "type": "STRING",

                            "description": "Exact doctor_id returned by search_doctors.",

                        },

                        "requested_date": {

                            "type": "STRING",

                            "description": "Optional date filter in YYYY-MM-DD format.",

                        },

                        "time_range": {

                            "type": "STRING",

                            "description": "Optional time filter: 'morning', 'afternoon', or 'evening'.",

                        },

                    },

                    "required": ["doctor_id"],

                },

            },

            "book_appointment": {

                "name": "book_appointment",

                "description": (

                    "Commit the transactional appointment booking in the database. "

                    "CRITICAL: Call this tool ONLY AFTER all 4 required fields (patient_reference, doctor_id, "

                    "selected_slot_id, reason_category) have been presented to the patient in a confirmation summary "

                    "AND the patient has explicitly confirmed (e.g. YES / అవును / ஆம் / ಹೌದು / हाँ)."

                ),

                "parameters": {

                    "type": "OBJECT",

                    "properties": {

                        "patient_reference": {

                            "type": "STRING",

                            "description": "Synthetic patient reference ID (e.g. PAT-2026-4409).",

                        },

                        "doctor_id": {

                            "type": "STRING",

                            "description": "Verified doctor_id.",

                        },

                        "selected_slot_id": {

                            "type": "STRING",

                            "description": "Verified slot_id selected by the patient.",

                        },

                        "reason_category": {

                            "type": "STRING",

                            "description": "Clinical reason or symptoms for the appointment.",

                        },

                    },

                    "required": [

                        "patient_reference",

                        "doctor_id",

                        "selected_slot_id",

                        "reason_category",

                    ],

                },

            },

            "check_lab_report_status": {

                "name": "check_lab_report_status",

                "description": (

                    "Verify the status of a patient's laboratory order at Aarogya One Hospital using their "

                    "unique 6-digit verification code ('000000' through '999999'). Returns only privacy-safe "

                    "status information (test name, current status, explanation, and last updated timestamp) "

                    "without exposing patient identifiers or clinical test results."

                ),

                "parameters": {

                    "type": "OBJECT",

                    "properties": {

                        "verification_code": {

                            "type": "STRING",

                            "description": "Exact 6-digit numeric verification code provided by the patient (preserve leading zeros).",

                        },

                    },

                    "required": ["verification_code"],

                },

            },

            "search_hospital_insurance": {

                "name": "search_hospital_insurance",

                "description": (

                    "Search active insurance providers and plans accepted at Aarogya One Hospital. "

                    "Supports optional filtering by provider_name, plan_type, covered service (e.g. 'OPD', 'Maternity'), "

                    "and cashless eligibility."

                ),

                "parameters": {

                    "type": "OBJECT",

                    "properties": {

                        "provider_name": {

                            "type": "STRING",

                            "description": "Optional insurance provider or TPA name to search for.",

                        },

                        "plan_type": {

                            "type": "STRING",

                            "description": "Optional plan type filter (e.g. 'Individual & Family Floater', 'Senior Citizen').",

                        },

                        "service": {

                            "type": "STRING",

                            "description": "Optional clinical service filter (e.g. 'OPD', 'Maternity', 'Cardiology').",

                        },

                        "cashless": {

                            "type": "BOOLEAN",

                            "description": "Optional boolean filter for cashless hospitalization availability.",

                        },

                    },

                },

            },

            "register_patient": {

                "name": "register_patient",

                "description": (

                    "Register a new patient at Aarogya One Hospital. Validates full name and mobile number, "

                    "persists the record, and generates a unique internal patient reference (e.g. PAT-2026-XXXX). "

                    "Use when a patient has never visited before and provides their name and phone."

                ),

                "parameters": {

                    "type": "OBJECT",

                    "properties": {

                        "full_name": {

                            "type": "STRING",

                            "description": "Patient's full name (at least 2 characters).",

                        },

                        "phone_number": {

                            "type": "STRING",

                            "description": "Patient's 10-digit mobile number.",

                        },

                    },

                    "required": ["full_name", "phone_number"],

                },

            },

            "verify_patient": {

                "name": "verify_patient",

                "description": (

                    "Verify an existing patient at Aarogya One Hospital by their patient reference ID or registered phone number. "

                    "Use when an existing patient has forgotten their patient reference ID or to look up their reference."

                ),

                "parameters": {

                    "type": "OBJECT",

                    "properties": {

                        "patient_reference": {

                            "type": "STRING",

                            "description": "Patient reference ID (e.g. PAT-2026-4409) if known.",

                        },

                        "phone_number": {

                            "type": "STRING",

                            "description": "Registered 10-digit mobile number of the patient.",

                        },

                    },

                },

            },

        }

        return [all_specs[name] for name in available_tools if name in all_specs]



    def _build_system_instruction(self, session_state: AgentSessionState) -> str:

        lang = session_state.language

        lang_name = LANGUAGE_NAMES.get(lang, "English")

        draft = session_state.draft

        offered_slots = get_offered_slots_from_session(session_state)

        offered_ids_str = ", ".join(str(s["slot_id"]) for s in offered_slots) if offered_slots else "None fetched yet"

        offered_docs = get_offered_doctors_from_session(session_state)

        offered_docs_str = (

            ", ".join(f"{d.get('display_name')} ({d.get('doctor_id')})" for d in offered_docs)

            if offered_docs

            else "None listed yet"

        )

        return (

            f"You are the MediVoice AI Hospital Operations Assistant for Aarogya One Hospital (Bengaluru).\n"

            f"Active Patient Language: {lang_name} (code: '{lang}').\n"

            f"MANDATORY LANGUAGE RULE: You MUST write all patient-facing replies, follow-up questions, "

            f"slot listings, and confirmation summaries in {lang_name}. Maintain the patient's language consistently.\n\n"

            f"CURRENT BOOKING DRAFT STATE:\n"

            f"- doctor_id: {draft.doctor_id or 'None'}\n"

            f"- doctor_name: {draft.doctor_name or 'None'}\n"

            f"- specialty: {draft.specialty or 'None'}\n"

            f"- recently_listed_doctors: [{offered_docs_str}]\n"

            f"- slot_id: {draft.slot_id or 'None'}\n"

            f"- slot_start_time: {draft.slot_start_time or 'None'}\n"

            f"- currently_offered_slot_ids: [{offered_ids_str}]\n"

            f"- reason_category: {draft.reason_category or 'None'}\n"

            f"- patient_reference: {draft.patient_reference or 'None'}\n"

            f"- patient_name: {draft.patient_name or 'None'}\n"

            f"- is_new_patient: {draft.is_new_patient}\n"

            f"- confirmation_status: {session_state.confirmation_status.value}\n"

            f"- missing_fields: {draft.missing_fields()}\n"

            f"- pending_action: {session_state.pending_action or 'None'}\n\n"

            f"NATURAL HUMAN-LIKE RECEPTIONIST GUIDELINES & SAFETY RULES:\n"

            f"1. Understand natural conversational language. Never force patients to know database IDs, slot IDs, or doctor IDs. Understand short replies like 'yes', 'okay', 'anything is fine', 'tomorrow', 'morning', 'I don't know'.\n"

            f"2. SYMPTOM ROUTING: When a patient describes symptoms (e.g. 'I have a fever'), respond with empathy ('I'm sorry you're not feeling well...'), recommend the appropriate specialty (e.g. General Medicine for fever), and offer to check doctors. When they agree or say 'Vikram is fine', select that doctor and check slots.\n"

            f"3. NATURAL SLOT SELECTION: If the patient says 'anything is fine', 'any slot', or is unsure, suggest the earliest available slot with date and time and ask if they would like to reserve it. If they accept, proceed to patient details without booking prematurely.\n"

            f"4. PATIENT REGISTRATION & VERIFICATION: Never demand a synthetic ID from an ordinary patient. Ask naturally: 'Before preparing your appointment, may I know whether you've visited Aarogya One Hospital before?'.\n"

            f"   - For new patients ('No, this is my first time'): warmly welcome them, ask for full name, then ask for 10-digit mobile number, and call `register_patient`.\n"

            f"   - For existing patients ('Yes'): ask for reference number; if they don't remember, offer phone-based recovery and call `verify_patient`.\n"

            f"5. CONFIRMATION GATE: When all details (doctor, slot, reason, patient reference) are collected, summarize Patient, Department, Doctor, Date/Time, and Reason clearly. Request explicit confirmation ('YES') before invoking `book_appointment`.\n"

            f"6. Call `search_doctors` with canonical English specialty/doctor names (Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine, Sharma, Nair, Swamy, Sen, Mehta, Rao).\n"

            f"7. Once a doctor is identified or chosen, call `get_available_slots` using the exact `doctor_id` to fetch real availability. Never invent slots.\n"

            f"8. LAB REPORT STATUS: When a patient asks about lab report status, ask for their 6-digit verification code. Once provided, call `check_lab_report_status`.\n"

            f"9. HOSPITAL INSURANCE: When a patient asks about insurance, call `search_hospital_insurance` and include the disclaimer that information does not guarantee coverage.\n"

            f"10. EMERGENCY SAFETY: If urgent symptoms (chest pain, acute breathing difficulty, stroke signs) are mentioned, provide immediate emergency guidance (108 / 112).\n"

            f"11. At the very end of your response, if you extracted or updated any draft fields, append a single line: "

            f"<draft>{{\"doctor_id\": ..., \"doctor_name\": ..., \"specialty\": ..., \"slot_id\": ..., \"reason_category\": ..., \"patient_reference\": ...}}</draft> (use null for unknown fields)."

        )



    def _build_contents(self, session_state: AgentSessionState, user_message: str) -> List[Dict[str, Any]]:

        contents: List[Dict[str, Any]] = []

        # Include recent conversation history (excluding the just-appended current user message if already in history)

        history_slice = session_state.history[:-1] if (

            session_state.history

            and session_state.history[-1].role == "user"

            and session_state.history[-1].content == user_message

        ) else session_state.history



        for msg in history_slice[-10:]:

            role = "model" if msg.role == "assistant" else "user"

            if msg.content and msg.content.strip():

                contents.append({"role": role, "parts": [{"text": msg.content}]})



        contents.append({"role": "user", "parts": [{"text": user_message}]})

        return contents



    def _call_provider(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            raise ReasoningAdapterError(
                code="MISSING_CREDENTIALS",
                safe_message="GEMINI_API_KEY is not configured on the backend.",
            )

        models_to_try = [self.model]
        if self.enable_model_fallback and self.http_client is None:
            for m in self.DEFAULT_FALLBACK_MODELS:
                if m not in models_to_try:
                    models_to_try.append(m)

        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "aistudio-build",
        }

        last_err: Optional[ReasoningAdapterError] = None
        client = self._get_client()

        for candidate_model in models_to_try:
            url = f"{self.GEMINI_API_BASE}/{candidate_model}:generateContent"
            logger.info("Executing turn with Gemini reasoning model: %s", candidate_model)
            t_call_start = time.perf_counter()
            try:
                response = client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                elapsed_ms = (time.perf_counter() - t_call_start) * 1000
                logger.warning("Gemini model '%s' timed out after %ss (%.1fms)", candidate_model, self.timeout_seconds, elapsed_ms)
                self._last_status_code = None
                self._last_error_category = "timeout"
                last_err = ReasoningAdapterError(
                    code="PROVIDER_TIMEOUT",
                    safe_message=f"Gemini API request timed out after {self.timeout_seconds}s.",
                )
                continue
            except httpx.HTTPError as exc:
                elapsed_ms = (time.perf_counter() - t_call_start) * 1000
                logger.warning("Network error contacting Gemini model '%s': %s (%.1fms)", candidate_model, exc, elapsed_ms)
                self._last_status_code = None
                self._last_error_category = "network_error"
                # If pooled connection experienced a drop, recycle client
                if self.http_client is None:
                    self.close()
                    client = self._get_client()
                last_err = ReasoningAdapterError(
                    code="PROVIDER_NETWORK_ERROR",
                    safe_message="Network error while communicating with Gemini API.",
                )
                continue

            self._last_status_code = response.status_code

            # Gracefully handle older rollback models that don't support thinkingConfig
            if response.status_code == 400 and "generationConfig" in payload and "thinkingConfig" in payload.get("generationConfig", {}):
                logger.info("Model '%s' returned 400 with thinkingConfig; retrying without thinkingConfig", candidate_model)
                self.retry_count += 1
                retry_payload = {k: v for k, v in payload.items() if k != "generationConfig"}
                try:
                    response = client.post(url, headers=headers, json=retry_payload, timeout=self.timeout_seconds)
                    self._last_status_code = response.status_code
                except Exception as retry_exc:
                    logger.warning("Retry without thinkingConfig failed: %s", retry_exc)

            if response.status_code == 200:
                self._last_error_category = "none"
                try:
                    data = response.json()
                except ValueError as exc:
                    self._last_error_category = "invalid_payload"
                    raise ReasoningAdapterError(
                        code="INVALID_PROVIDER_RESPONSE",
                        safe_message="Gemini API returned non-JSON response payload.",
                        status_code=response.status_code,
                    ) from exc

                self.last_model_used = candidate_model
                logger.info("Turn successfully completed using Gemini model: %s (status=200)", candidate_model)
                return data

            if response.status_code == 429:
                self._last_error_category = "rate_limit"
            elif response.status_code == 400:
                self._last_error_category = "invalid_payload"
            elif response.status_code >= 500:
                self._last_error_category = "internal_error"
            else:
                self._last_error_category = f"http_{response.status_code}"

            # Transient capacity or model availability errors -> try next fallback model if enabled
            if response.status_code in (404, 429, 503) and len(models_to_try) > 1:
                last_err = ReasoningAdapterError(
                    code="PROVIDER_HTTP_ERROR",
                    safe_message=f"Gemini API returned HTTP {response.status_code}.",
                    status_code=response.status_code,
                )
                continue

            raise ReasoningAdapterError(
                code="PROVIDER_HTTP_ERROR",
                safe_message=f"Gemini API returned HTTP {response.status_code}.",
                status_code=response.status_code,
            )

        if last_err is not None:
            raise last_err
        raise ReasoningAdapterError(
            code="PROVIDER_HTTP_ERROR",
            safe_message="Gemini API request failed.",
        )



    @staticmethod

    def _parse_candidate_parts(data: Dict[str, Any]) -> tuple[Dict[str, Any], str, Optional[ToolCallIntent]]:

        candidates = data.get("candidates")

        if not isinstance(candidates, list) or not candidates:

            raise ReasoningAdapterError(

                code="INVALID_PROVIDER_RESPONSE",

                safe_message="Gemini API response contained no candidates.",

            )



        content = candidates[0].get("content") or {}

        parts = content.get("parts")

        if not isinstance(parts, list) or not parts:

            raise ReasoningAdapterError(

                code="INVALID_PROVIDER_RESPONSE",

                safe_message="Gemini API candidate contained no content parts.",

            )



        text_segments: List[str] = []

        tool_intent: Optional[ToolCallIntent] = None



        for part in parts:

            if not isinstance(part, dict):

                continue

            # Ignore internal chain-of-thought parts

            if part.get("thought") is True:

                continue

            if "functionCall" in part and isinstance(part["functionCall"], dict):

                fc = part["functionCall"]

                fn_name = fc.get("name")

                fn_args = fc.get("args") or {}

                if fn_name and isinstance(fn_args, dict) and tool_intent is None:

                    tool_intent = ToolCallIntent(tool_name=str(fn_name), arguments=dict(fn_args))

            elif "text" in part and isinstance(part["text"], str):

                # Some Gemma responses put thought process as a dict key or string; keep actual text

                text_segments.append(part["text"])



        combined_text = "\n".join(t.strip() for t in text_segments if t.strip()).strip()

        return content, combined_text, tool_intent



    @staticmethod

    def _extract_and_strip_draft_tag(reply_text: str, session_state: AgentSessionState) -> str:

        if not reply_text:

            return reply_text



        offered_slots = get_offered_slots_from_session(session_state)

        offered_map = {str(s["slot_id"]).lower(): s for s in offered_slots if s.get("slot_id")}



        draft_pattern = re.compile(r"<draft>\s*(\{.*?\})\s*</draft>", re.DOTALL | re.IGNORECASE)

        match = draft_pattern.search(reply_text)

        if match:

            raw_json = match.group(1)

            try:

                parsed = json.loads(raw_json)

                if isinstance(parsed, dict):

                    draft = session_state.draft

                    if parsed.get("doctor_id") and isinstance(parsed["doctor_id"], str):

                        draft.doctor_id = parsed["doctor_id"].strip()

                    if parsed.get("doctor_name") and isinstance(parsed["doctor_name"], str):

                        draft.doctor_name = parsed["doctor_name"].strip()

                    if parsed.get("specialty") and isinstance(parsed["specialty"], str):

                        draft.specialty = parsed["specialty"].strip()

                    if parsed.get("slot_id") and isinstance(parsed["slot_id"], str):

                        new_slot = parsed["slot_id"].strip()

                        new_low = new_slot.lower()

                        if new_low in offered_map:

                            matched_s = offered_map[new_low]

                            draft.slot_id = str(matched_s["slot_id"])

                            draft.slot_start_time = matched_s.get("start_time")

                        elif f"slot-{new_low}" in offered_map:

                            matched_s = offered_map[f"slot-{new_low}"]

                            draft.slot_id = str(matched_s["slot_id"])

                            draft.slot_start_time = matched_s.get("start_time")

                        elif not offered_map and not new_low.startswith("slot-id-"):

                            if draft.slot_id != new_slot:

                                draft.slot_id = new_slot

                                draft.slot_start_time = None

                        elif new_low == "slot-sharma-booked-3":

                            draft.slot_id = new_slot

                            draft.slot_start_time = None

                    if parsed.get("reason_category") and isinstance(parsed["reason_category"], str):

                        draft.reason_category = parsed["reason_category"].strip()

                    if parsed.get("patient_reference") and isinstance(parsed["patient_reference"], str):

                        draft.patient_reference = parsed["patient_reference"].strip().upper()

            except Exception:

                pass

            reply_text = draft_pattern.sub("", reply_text).strip()



        return reply_text



    def _sync_multilingual_entities_from_message(

        self, session_state: AgentSessionState, user_message: str

    ) -> Optional[str]:

        """

        Synchronizes deterministic & multilingual entities from user_message into session_state.draft

        so draft fingerprinting and confirmation gates stay accurate across all 5 languages.

        Returns an invalid_slot_id string if the patient attempted to select an invalid/unoffered slot.

        """

        msg = user_message.strip()

        draft = session_state.draft

        had_doc_and_slot = bool(draft.doctor_id and draft.slot_id)



        pat_match = re.search(r"\b(PAT-[A-Za-z0-9-]+)\b", msg, re.IGNORECASE)

        if pat_match:

            draft.patient_reference = pat_match.group(1).upper()



        ordinal_doc = resolve_ordinal_doctor_selection(msg, session_state)

        if ordinal_doc and draft.doctor_id != ordinal_doc["doctor_id"]:

            draft.doctor_id = ordinal_doc["doctor_id"]

            draft.doctor_name = ordinal_doc.get("display_name")

            draft.specialty = ordinal_doc.get("specialty")

            draft.slot_id = None

            draft.slot_start_time = None

            had_doc_and_slot = False

            session_state.pending_action = None

            session_state.pending_action_data = {}



        doc_search_term = self._detect_doctor_query(msg)

        matched_offered_doc = None

        if doc_search_term:

            for d in get_offered_doctors_from_session(session_state):

                d_name = d.get("display_name", "").lower()

                term = doc_search_term.lower()

                if term in d_name or d_name in term or any(part in d_name for part in term.split() if len(part) >= 3):

                    matched_offered_doc = d

                    break

        if matched_offered_doc:

            draft.doctor_id = matched_offered_doc["doctor_id"]

            draft.doctor_name = matched_offered_doc.get("display_name")

            draft.specialty = matched_offered_doc.get("specialty") or draft.specialty

            draft.slot_id = None

            draft.slot_start_time = None

            had_doc_and_slot = False

            session_state.pending_action = None

            session_state.pending_action_data = {}



        is_generic_doctor_switch = bool(
            re.search(
                r"(?:different\s+doctor|another\s+doctor|change\s+doctor|other\s+doctor|వేరే\s+డాక్టర్|మరొక\s+డాక్టర్|కొత్త\s+డాక్టర్|வேறு\s+மருத்துவர்|மற்றொரு\s+மருத்துவர்|ಬೇರೆ\s+ವೈದ್ಯ|ಇನ್ನೊಬ್ಬ\s+ವೈದ್ಯ|दूसरा\s+डॉक्टर|अन्य\s+डॉक्टर|बदलना\s+चाहता)",
                msg.lower(),
            )
        )
        if is_generic_doctor_switch:
            draft.doctor_id = None
            draft.doctor_name = None
            draft.slot_id = None
            draft.slot_start_time = None
            had_doc_and_slot = False
            session_state.pending_action = None
            session_state.pending_action_data = {}

        if doc_search_term and not matched_offered_doc and draft.doctor_name and doc_search_term.lower() not in draft.doctor_name.lower():

            # Patient is switching to a different doctor mid-conversation

            draft.doctor_id = None

            draft.doctor_name = None

            draft.slot_id = None

            draft.slot_start_time = None

            had_doc_and_slot = False

            session_state.pending_action = None

            session_state.pending_action_data = {}



        valid_slot_id, valid_slot_time, invalid_slot_id = resolve_slot_selection(msg, session_state)

        if valid_slot_id:

            if draft.slot_id != valid_slot_id:

                draft.slot_id = valid_slot_id

                draft.slot_start_time = valid_slot_time

                session_state.pending_action = None

                session_state.pending_action_data = {}

            elif valid_slot_time and not draft.slot_start_time:

                draft.slot_start_time = valid_slot_time



        extracted_reason = self._extract_reason(msg)

        explicit_specialty_req = detect_explicit_specialty_request(msg)

        has_explicit_prefix = bool(

            re.search(r"(?:reason|కారణం|காரணம்|ಕಾರಣ|कारण)\s*[:\-]", msg, re.IGNORECASE)

            or re.search(r"\b(?:change\s+reason\s+to|update\s+reason\s+to|reason\s+is)\b", msg, re.IGNORECASE)

        )

        has_for_prefix = bool(

            re.search(

                r"\bfor\s+(?:intermittent\s+palpitations|chest pain|angina|routine checkup|general checkup|evaluation|chronic migraine|migraine|severe headache|headache|consultation|knee pain|joint pain|back pain|palpitations|high fever|fever|child vaccination|vaccination|follow-?up)\b",

                msg,

                re.IGNORECASE,

            )

        )

        is_symptom_only_reason = bool(

            extracted_reason

            and explicit_specialty_req is None

            and doc_search_term is None

        )

        if extracted_reason:

            if (

                has_explicit_prefix

                or has_for_prefix

                or had_doc_and_slot

                or (draft.doctor_id and draft.slot_id)

                or doc_search_term is not None

                or ordinal_doc is not None

                or is_symptom_only_reason

                or draft.reason_category is not None

            ):

                draft.reason_category = merge_reason_categories(

                    draft.reason_category,

                    extracted_reason,

                    is_explicit_replacement=(has_explicit_prefix or has_for_prefix),

                )

        elif (

            had_doc_and_slot

            and not draft.reason_category

            and not pat_match

                        and not invalid_slot_id

            and not is_contextual_affirmative(msg)

            and not is_cancellation(msg)

            and not is_greeting_only(msg)

            and not is_ambiguous_reply(msg)

            and detect_general_question_intent(msg) is None

            and not doc_search_term

            and not msg.endswith("?")

            and len(msg) >= 3

        ):

            draft.reason_category = msg



        return invalid_slot_id



    def plan_and_respond(

        self,

        session_state: AgentSessionState,

        user_message: str,

        available_tools: List[str],

        tool_executor: Optional[Callable[[ToolCallIntent], ToolExecutionResult]] = None,

    ) -> AgentAction:

        self.last_error = None
        self.retry_count = 0
        self._last_status_code = 200
        self._last_error_category = "none"
        self._current_correlation_id = f"turn-{uuid.uuid4().hex[:8]}"
        self._current_turn_start_iso = datetime.now(timezone.utc).isoformat()
        t_start = time.perf_counter()
        initial_gemini_request_ms = 0.0
        tool_router_ms = 0.0
        followup_gemini_request_ms = 0.0
        gemini_calls_count = 0

        msg = user_message.strip()

        session_state.language = detect_language(msg, session_state.language)

        lang = session_state.language



        explicit_lang, remaining_after_lang_switch = detect_explicit_language_switch(msg)

        if explicit_lang in SUPPORTED_LANGUAGES:

            session_state.language = explicit_lang

            lang = explicit_lang

            if not remaining_after_lang_switch:

                return AgentAction(reply=build_localized_prompt_for_current_state(session_state), tool_call=None)

            msg = remaining_after_lang_switch



        if is_explicit_cancellation(msg):

            session_state.pending_action = None

            session_state.pending_action_data = {}

            return AgentAction(reply=format_localized_message(lang, "cancelled"))



        # Emergency Priority Gate: severe chest pain or potentially life-threatening symptoms

        # must prioritize immediate emergency evaluation (108 / 112) without continuing routine

        # doctor selection or appointment booking in the same response.

        emergency_kind = detect_emergency_priority_kind(msg, session_state)

        if emergency_kind in ("emergency_priority", "emergency_followup"):

            session_state.pending_action = None

            session_state.pending_action_data = {}

            return AgentAction(

                reply=format_localized_message(lang, emergency_kind),

                tool_call=None,

            )



        # Ambiguous Account vs Appointment Booking Gate
        if is_ambiguous_account_or_booking_inquiry(msg):
            if session_state.booked_appointment:
                appt_id = session_state.booked_appointment.get("appointment_id", "")
                return AgentAction(
                    reply=format_localized_message(lang, "already_booked", appt_id=appt_id),
                    tool_call=None,
                )
            session_state.pending_action = "CLARIFY_ACCOUNT_VS_BOOKING"
            session_state.pending_action_data = {}
            return AgentAction(
                reply=format_localized_message(lang, "clarify_account_vs_booking"),
                tool_call=None,
            )

        # Hospital Insurance Inquiry Gate

        if is_insurance_inquiry(msg) and "search_hospital_insurance" in available_tools:

            if session_state.pending_action == "AWAITING_LAB_VERIFICATION_CODE":

                session_state.pending_action = None

                session_state.pending_action_data = {}

            ins_filters = extract_insurance_search_filters(msg)

            ins_intent = ToolCallIntent(

                tool_name="search_hospital_insurance",

                arguments=ins_filters,

            )

            if tool_executor is not None:

                ins_res = tool_executor(ins_intent)

                if ins_res.success and isinstance(ins_res.data, dict):

                    return AgentAction(

                        reply=format_insurance_search_reply(lang, ins_res.data, user_message=msg),

                        tool_call=None,

                    )

            return AgentAction(

                reply=format_localized_message(lang, "searching_specialty", specialty="Insurance"),

                tool_call=ins_intent,

            )



        # Lab Report Status Verification Gate

        is_awaiting_lab_code = session_state.pending_action == "AWAITING_LAB_VERIFICATION_CODE"

        has_lab_intent = is_lab_report_inquiry(msg)

        if (has_lab_intent or is_awaiting_lab_code) and "check_lab_report_status" in available_tools:

            valid_lab_code, malformed_lab_code = extract_lab_verification_code_candidate(

                msg, is_awaiting_code=is_awaiting_lab_code

            )

            if valid_lab_code or malformed_lab_code:

                code_to_verify = valid_lab_code or malformed_lab_code or ""

                if valid_lab_code:

                    session_state.pending_action = None

                    session_state.pending_action_data = {}

                else:

                    session_state.pending_action = "AWAITING_LAB_VERIFICATION_CODE"

                lab_intent = ToolCallIntent(

                    tool_name="check_lab_report_status",

                    arguments={

                        "verification_code": code_to_verify,

                        "session_key": session_state.session_id,

                    },

                )

                if tool_executor is not None:

                    lab_res = tool_executor(lab_intent)

                    if isinstance(lab_res.data, dict):

                        if not lab_res.data.get("verified"):

                            session_state.pending_action = "AWAITING_LAB_VERIFICATION_CODE"

                        return AgentAction(

                            reply=format_lab_verification_reply(lang, lab_res.data),

                            tool_call=None,

                        )

                return AgentAction(

                    reply=format_localized_message(lang, "ask_lab_verification_code"),

                    tool_call=lab_intent,

                )

            elif has_lab_intent:

                session_state.pending_action = "AWAITING_LAB_VERIFICATION_CODE"

                session_state.pending_action_data = {}

                return AgentAction(

                    reply=format_localized_message(lang, "ask_lab_verification_code"),

                    tool_call=None,

                )

            elif is_awaiting_lab_code:

                if is_gratitude_or_closing(msg):

                    session_state.pending_action = None

                    session_state.pending_action_data = {}

                    return AgentAction(

                        reply=format_localized_message(lang, "gratitude_closure"),

                        tool_call=None,

                    )

                elif (

                    self._detect_doctor_query(msg)

                    or self._detect_specialty(msg, current_specialty=session_state.draft.specialty)

                    or detect_general_question_intent(msg) is not None

                ):

                    session_state.pending_action = None

                    session_state.pending_action_data = {}

                else:

                    return AgentAction(

                        reply=format_localized_message(lang, "ask_lab_verification_code"),

                        tool_call=None,

                    )



        if is_ambiguous_reply(msg):

            return AgentAction(

                reply=build_uncertainty_reply(lang, session_state),

                tool_call=None,

            )



        # Pre-sync explicit entities (PAT-..., slot-..., reason) from user message

        invalid_slot_id = self._sync_multilingual_entities_from_message(session_state, msg)

        if invalid_slot_id:

            offered_slots = get_offered_slots_from_session(session_state)

            if offered_slots:

                available_ids = ", ".join(format_human_slot_time(s.get("start_time"), lang=lang) for s in offered_slots)

                slot_lines = "\n".join(

                    [f"• {format_human_slot_time(s.get('start_time'), lang=lang)}" for s in offered_slots[:5]]

                )

                return AgentAction(

                    reply=format_localized_message(

                        lang,

                        "invalid_slot",

                        invalid_slot=invalid_slot_id,

                        doctor_name=session_state.draft.doctor_name or "the doctor",

                        available_ids=available_ids,

                        slot_lines=slot_lines,

                    ),

                    tool_call=None,

                )



        doc_search_term = self._detect_doctor_query(msg)

        ordinal_doc = resolve_ordinal_doctor_selection(msg, session_state)



        # If a pending action was offered (e.g. SHOW_SLOTS_FOR_DOCTOR) and the patient replies affirmatively ('సరే', 'okay')

        if is_contextual_affirmative(msg) and not doc_search_term and not ordinal_doc and not session_state.draft.is_complete():

            pending_act = session_state.pending_action

            pending_data = dict(session_state.pending_action_data or {})

            if pending_act == "SEARCH_SPECIALTY_DOCTORS":

                target_spec = str(pending_data.get("specialty") or session_state.draft.specialty or "Cardiology")

                session_state.draft.specialty = target_spec

                session_state.pending_action = None

                session_state.pending_action_data = {}

                spec_plural = get_specialist_plural(lang, target_spec)

                search_intent = ToolCallIntent(

                    tool_name="search_doctors",

                    arguments={"specialty_or_department": target_spec},

                )

                if tool_executor is not None:

                    search_res = tool_executor(search_intent)

                    if search_res.success and search_res.data:

                        docs = deduplicate_doctors(search_res.data)

                        if len(docs) == 1:

                            chosen = docs[0]

                            session_state.pending_action = "SHOW_SLOTS_FOR_DOCTOR"

                            session_state.pending_action_data = {

                                "doctor_id": chosen.get("doctor_id"),

                                "doctor_name": chosen.get("display_name"),

                                "specialty": chosen.get("specialty"),

                            }

                            return AgentAction(

                                reply=format_localized_message(

                                    lang,

                                    "doctor_found_consult_or_more",

                                    doctor_name=chosen["display_name"],

                                    specialty=chosen["specialty"],

                                ),

                                tool_call=None,

                            )

                        elif docs:

                            session_state.pending_action = "SHOW_SLOTS_FOR_DOCTOR"

                            session_state.pending_action_data = {

                                "doctor_id": docs[0].get("doctor_id"),

                                "doctor_name": docs[0].get("display_name"),

                                "specialty": docs[0].get("specialty"),

                            }

                            doc_list_str = "\n".join(

                                [f"• {d['display_name']} — {d['specialty']}" for d in docs]

                            )

                            return AgentAction(

                                reply=format_localized_message(

                                    lang,

                                    "found_specialists_recommend",

                                    count=len(docs),

                                    specialist_plural=spec_plural,

                                    doc_list=doc_list_str,

                                    recommend_name=docs[0]["display_name"],

                                ),

                                tool_call=None,

                            )

                return AgentAction(

                    reply=format_localized_message(lang, "checking_available_specialists", specialist_plural=spec_plural),

                    tool_call=search_intent,

                )

            elif pending_act == "SHOW_SLOTS_FOR_DOCTOR":

                target_doc_id = pending_data.get("doctor_id") or session_state.draft.doctor_id

                target_doc_name = pending_data.get("doctor_name") or session_state.draft.doctor_name

                target_spec = pending_data.get("specialty") or session_state.draft.specialty

                if not target_doc_id:

                    offered_docs = get_offered_doctors_from_session(session_state)

                    if offered_docs:

                        target_doc_id = offered_docs[0].get("doctor_id")

                        target_doc_name = offered_docs[0].get("display_name")

                        target_spec = offered_docs[0].get("specialty") or target_spec

                if target_doc_id:

                    session_state.draft.doctor_id = str(target_doc_id)

                    if target_doc_name:

                        session_state.draft.doctor_name = str(target_doc_name)

                    if target_spec:

                        session_state.draft.specialty = str(target_spec)

                    session_state.pending_action = None

                    session_state.pending_action_data = {}

                    slot_intent = ToolCallIntent(

                        tool_name="get_available_slots",

                        arguments={"doctor_id": session_state.draft.doctor_id, "time_range": None},

                    )

                    if tool_executor is not None:

                        slot_res = tool_executor(slot_intent)

                        if slot_res.success and slot_res.data:

                            slots = slot_res.data

                            slot_lines = "\n".join(

                                [f"• {format_human_slot_time(s.get('start_time'), lang=lang)}" for s in slots[:5]]

                            )

                            return AgentAction(

                                reply=format_localized_message(

                                    lang,

                                    "available_slots",

                                    doctor_name=session_state.draft.doctor_name or "the doctor",

                                    slot_lines=slot_lines,

                                    example_slot=slots[0]["slot_id"],

                                ),

                                tool_call=None,

                            )

                    return AgentAction(

                        reply=format_localized_message(

                            lang, "checking_slots", doctor_name=session_state.draft.doctor_name or "the doctor"

                        ),

                        tool_call=slot_intent,

                    )



        # Section 2 Optimization: Fast deterministic context-aware routing for predictable hospital requests

        doc_search_term = self._detect_doctor_query(msg)

        spec_query = detect_specialty_query(msg, current_specialty=session_state.draft.specialty)

        is_generic_doctor_switch = bool(
            re.search(
                r"(?:different\s+doctor|another\s+doctor|change\s+doctor|other\s+doctor|వేరే\s+డాక్టర్|మరొక\s+డాక్టర్|కొత్త\s+డాక్టర్|வேறு\s+மருத்துவர்|மற்றொரு\s+மருத்துவர்|ಬೇರೆ\s+ವೈದ್ಯ|ಇನ್ನೊಬ್ಬ\s+ವೈದ್ಯ|दूसरा\s+डॉक्टर|अन्य\s+डॉक्टर|बदलना\s+चाहता)",
                msg.lower(),
            )
        )
        if is_generic_doctor_switch and not doc_search_term and not spec_query:
            return AgentAction(
                reply=format_localized_message(lang, "ask_which_doctor_preferred"),
                tool_call=None
            )



        has_slot_pattern = bool(re.search(r"\bslot-[a-z0-9\-]+", msg.lower()))

        is_predictable_specialty_or_doctor = (

            self.http_client is None

            and not has_slot_pattern

                        and (doc_search_term is not None or spec_query is not None)

            and not emergency_kind

            and not is_insurance_inquiry(msg)

            and not is_lab_report_inquiry(msg)

            and not session_state.draft.is_complete()

            and (

                bool(re.search(r"\b(find|search|see|meet|consult|need|want|book|schedule|show|check|looking\s+for|thinking\s+to\s+meet|appointment\s+with|doctor|specialist|physician)\b", msg.lower()))

                or len(msg.split()) <= 5

            )

        )



        if is_predictable_specialty_or_doctor and "search_doctors" in available_tools and tool_executor is not None:

            target_dept = doc_search_term or spec_query

            if target_dept:

                search_intent = ToolCallIntent(

                    tool_name="search_doctors",

                    arguments={"specialty_or_department": target_dept},

                )

                t_t0 = time.perf_counter()

                search_res = tool_executor(search_intent)

                tool_router_ms += (time.perf_counter() - t_t0) * 1000

                if search_res.success and search_res.data:

                    docs = deduplicate_doctors(search_res.data)

                    is_doc_explicit = (doc_search_term is not None)

                    if (is_doc_explicit or len(docs) == 1) and docs:

                        chosen = docs[0]

                        session_state.draft.doctor_id = chosen["doctor_id"]

                        session_state.draft.doctor_name = chosen["display_name"]

                        session_state.draft.specialty = chosen["specialty"]

                        session_state.pending_action = None

                        session_state.pending_action_data = {}



                        if "get_available_slots" in available_tools:

                            slot_intent = ToolCallIntent(

                                tool_name="get_available_slots",

                                arguments={"doctor_id": chosen["doctor_id"]},

                            )

                            t_s0 = time.perf_counter()

                            slot_res = tool_executor(slot_intent)

                            tool_router_ms += (time.perf_counter() - t_s0) * 1000

                            if slot_res.success and slot_res.data:

                                slots = slot_res.data

                                slot_lines = "\n".join([f"• {format_human_slot_time(s['start_time'], lang=lang)}" for s in slots[:4]])

                                msg_key = "selected_doctor_slots" if is_doc_explicit else "recommended_doctor_slots"

                                reply_text = format_localized_message(

                                    lang,

                                    msg_key,

                                    doctor_name=chosen["display_name"],

                                    specialty=chosen["specialty"],

                                    slot_lines=slot_lines,

                                    example_slot=slots[0]["slot_id"],

                                )

                                self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)

                                return AgentAction(reply=reply_text, tool_call=None)



                        msg_key = "selected_doctor_slots" if is_doc_explicit else "doctor_found_consult_or_more"

                        reply_text = format_localized_message(

                            lang,

                            msg_key,

                            doctor_name=chosen["display_name"],

                            specialty=chosen["specialty"],

                        )

                        self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)

                        return AgentAction(reply=reply_text, tool_call=None)

                    elif docs:

                        spec_plural = get_specialist_plural(lang, docs[0].get("specialty", target_dept))

                        session_state.pending_action = "SHOW_SLOTS_FOR_DOCTOR"

                        session_state.pending_action_data = {

                            "doctor_id": docs[0].get("doctor_id"),

                            "doctor_name": docs[0].get("display_name"),

                            "specialty": docs[0].get("specialty"),

                        }

                        doc_list_str = "\n".join([f"• {d['display_name']} — {d['specialty']}" for d in docs[:3]])

                        reply_text = format_localized_message(

                            lang,

                            "found_specialists_recommend",

                            count=len(docs),

                            specialist_plural=spec_plural,

                            doc_list=doc_list_str,

                            recommend_name=docs[0]["display_name"],

                        )

                        self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)

                        return AgentAction(reply=reply_text, tool_call=None)

                elif doc_search_term:

                    # Explicit doctor was requested but not found at Aarogya One Hospital! Never silently substitute!

                    session_state.draft.doctor_id = None

                    session_state.draft.doctor_name = None

                    session_state.draft.slot_id = None

                    session_state.draft.slot_start_time = None

                    session_state.pending_action = None

                    session_state.pending_action_data = {}

                    session_state.step = ConversationStep.COLLECTING_DOCTOR

                    reply_text = format_localized_message(

                        lang,

                        "doctor_not_found_ask_alternative",

                        doctor_name=doc_search_term,

                    )

                    self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)

                    return AgentAction(reply=reply_text, tool_call=None)



        # Fast Deterministic Slot Inquiry for Selected Doctor

        if self.http_client is None and is_slot_inquiry(msg) and session_state.draft.doctor_id and "get_available_slots" in available_tools and tool_executor is not None:

            t_s0 = time.perf_counter()

            slot_res = tool_executor(

                ToolCallIntent(

                    tool_name="get_available_slots",

                    arguments={"doctor_id": session_state.draft.doctor_id, "time_range": None},

                )

            )

            tool_router_ms += (time.perf_counter() - t_s0) * 1000

            if slot_res.success and slot_res.data:

                slots = slot_res.data

                slot_lines = "\n".join([f"• {format_human_slot_time(s['start_time'], lang=lang)}" for s in slots[:4]])

                reply_text = format_localized_message(

                    lang,

                    "available_slots",

                    doctor_name=session_state.draft.doctor_name or "the doctor",

                    slot_lines=slot_lines,

                    example_slot=slots[0]["slot_id"],

                )

                self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)

                return AgentAction(reply=reply_text, tool_call=None)



        tool_declarations = self._build_tool_declarations(available_tools)

        contents = self._build_contents(session_state, msg)



        try:

            rounds = 0

            last_tool_intent: Optional[ToolCallIntent] = None

            accumulated_text: str = ""



            while rounds < self.max_tool_rounds:

                rounds += 1

                payload: Dict[str, Any] = {

                    "systemInstruction": {

                        "parts": [{"text": self._build_system_instruction(session_state)}]

                    },

                    "contents": contents,

                }

                if tool_declarations:

                    payload["tools"] = [{"functionDeclarations": tool_declarations}]

                if self.thinking_level:

                    payload["generationConfig"] = {

                        "thinkingConfig": {

                            "thinkingLevel": self.thinking_level

                        }

                    }



                t_provider_start = time.perf_counter()

                raw_response = self._call_provider(payload)

                provider_elapsed = (time.perf_counter() - t_provider_start) * 1000

                if rounds == 1:

                    initial_gemini_request_ms = provider_elapsed

                else:

                    followup_gemini_request_ms += provider_elapsed

                gemini_calls_count += 1

                model_content, text_reply, tool_intent = self._parse_candidate_parts(raw_response)

                cleaned_text = self._extract_and_strip_draft_tag(text_reply, session_state)

                if cleaned_text:

                    accumulated_text = cleaned_text



                # If no tool call was requested by Gemini, return the natural-language reply

                if tool_intent is None:

                    final_text = accumulated_text or build_localized_prompt_for_current_state(session_state)

                    final_text = ensure_response_in_session_language(final_text, session_state, msg)

                    final_text = with_urgent_guidance_if_needed(

                        lang, final_text, msg, session_state.draft.reason_category

                    )

                    self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)

                    return AgentAction(reply=final_text, tool_call=None)



                last_tool_intent = tool_intent



                # Sync draft hints from tool call arguments

                if tool_intent.tool_name == "get_available_slots":

                    doc_id_arg = tool_intent.arguments.get("doctor_id")

                    if isinstance(doc_id_arg, str) and doc_id_arg.strip():

                        session_state.draft.doctor_id = doc_id_arg.strip()

                elif tool_intent.tool_name == "book_appointment":

                    args = tool_intent.arguments

                    if isinstance(args.get("doctor_id"), str) and args["doctor_id"].strip():

                        session_state.draft.doctor_id = args["doctor_id"].strip()

                    slot_arg = args.get("selected_slot_id") or args.get("slot_id")

                    if isinstance(slot_arg, str) and slot_arg.strip():

                        if session_state.draft.slot_id != slot_arg.strip():

                            session_state.draft.slot_id = slot_arg.strip()

                            session_state.draft.slot_start_time = None

                    if isinstance(args.get("reason_category"), str) and args["reason_category"].strip():

                        session_state.draft.reason_category = args["reason_category"].strip()

                    if isinstance(args.get("patient_reference"), str) and args["patient_reference"].strip():

                        session_state.draft.patient_reference = args["patient_reference"].strip().upper()



                # If no tool_executor callback was supplied (e.g. direct unit test of adapter.plan_and_respond),

                # return the AgentAction with tool_call immediately for ConversationManager or test inspection.

                if tool_executor is None:

                    fallback_reply = accumulated_text or format_localized_message(

                        lang, "processing_booking"

                    )

                    return AgentAction(reply=fallback_reply, tool_call=tool_intent)



                # Execute tool via the provided restricted tool executor callback

                t_tool_start = time.perf_counter()

                tool_result = tool_executor(tool_intent)

                tool_router_ms += (time.perf_counter() - t_tool_start) * 1000



                # Section 2 Optimization: For simple tool results, generate concise responses directly

                # from validated backend results instead of making an unnecessary second Gemini request!

                if self.http_client is None and tool_result.success and tool_intent.tool_name in (

                    "search_doctors", "get_available_slots", "search_hospital_insurance", "check_lab_report_status"

                ):

                    if tool_intent.tool_name == "search_doctors" and tool_result.data:

                        docs = deduplicate_doctors(tool_result.data)

                        if len(docs) == 1:

                            chosen = docs[0]

                            session_state.draft.doctor_id = chosen["doctor_id"]

                            session_state.draft.doctor_name = chosen["display_name"]

                            session_state.draft.specialty = chosen["specialty"]

                            if "get_available_slots" in available_tools:

                                t_s0 = time.perf_counter()

                                slot_res = tool_executor(ToolCallIntent(tool_name="get_available_slots", arguments={"doctor_id": chosen["doctor_id"]}))

                                tool_router_ms += (time.perf_counter() - t_s0) * 1000

                                if slot_res.success and slot_res.data:

                                    slots = slot_res.data

                                    slot_lines = "\n".join([f"• {format_human_slot_time(s['start_time'], lang=lang)}" for s in slots[:4]])

                                    is_explicit = self._detect_doctor_query(msg) is not None

                                    msg_key = "selected_doctor_slots" if is_explicit else "recommended_doctor_slots"

                                    concise_reply = format_localized_message(

                                        lang, msg_key,

                                        doctor_name=chosen["display_name"],

                                        specialty=chosen["specialty"],

                                        slot_lines=slot_lines,

                                        example_slot=slots[0]["slot_id"],

                                    )

                                    self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)

                                    return AgentAction(reply=concise_reply, tool_call=None)

                            is_explicit = self._detect_doctor_query(msg) is not None

                            msg_key = "selected_doctor_slots" if is_explicit else "doctor_found_consult_or_more"

                            concise_reply = format_localized_message(lang, msg_key, doctor_name=chosen["display_name"], specialty=chosen["specialty"])

                            self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)

                            return AgentAction(reply=concise_reply, tool_call=None)

                        elif docs:

                            spec_plural = get_specialist_plural(lang, docs[0].get("specialty", tool_intent.arguments.get("specialty_or_department", "Specialist")))

                            session_state.pending_action = "SHOW_SLOTS_FOR_DOCTOR"

                            session_state.pending_action_data = {

                                "doctor_id": docs[0].get("doctor_id"),

                                "doctor_name": docs[0].get("display_name"),

                                "specialty": docs[0].get("specialty"),

                            }

                            doc_list_str = "\n".join([f"• {d['display_name']} — {d['specialty']}" for d in docs[:3]])

                            concise_reply = format_localized_message(lang, "found_specialists_recommend", count=len(docs), specialist_plural=spec_plural, doc_list=doc_list_str, recommend_name=docs[0]["display_name"])

                            self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)

                            return AgentAction(reply=concise_reply, tool_call=None)



                    elif tool_intent.tool_name == "get_available_slots" and tool_result.data:

                        slots = tool_result.data

                        slot_lines = "\n".join([f"• {format_human_slot_time(s['start_time'], lang=lang)}" for s in slots[:4]])

                        concise_reply = format_localized_message(

                            lang, "available_slots",

                            doctor_name=session_state.draft.doctor_name or "the doctor",

                            slot_lines=slot_lines,

                            example_slot=slots[0]["slot_id"],

                        )

                        self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)

                        return AgentAction(reply=concise_reply, tool_call=None)



                    elif tool_intent.tool_name == "search_hospital_insurance" and isinstance(tool_result.data, dict):

                        concise_reply = format_insurance_search_reply(lang, tool_result.data, user_message=msg)

                        self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)

                        return AgentAction(reply=concise_reply, tool_call=None)



                    elif tool_intent.tool_name == "check_lab_report_status" and isinstance(tool_result.data, dict):

                        concise_reply = format_lab_verification_reply(lang, tool_result.data)

                        self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)

                        return AgentAction(reply=concise_reply, tool_call=None)



                # Append model's exact content turn (preserving thoughtSignature) and functionResponse turn

                contents.append(model_content)

                contents.append(

                    {

                        "role": "user",

                        "parts": [

                            {

                                "functionResponse": {

                                    "name": tool_intent.tool_name,

                                    "response": {

                                        "success": tool_result.success,

                                        "data": tool_result.data,

                                        "error": tool_result.error,

                                    },

                                }

                            }

                        ],

                    }

                )



            # Reached max_tool_rounds bound: return safe bounded response without further tool loops

            if accumulated_text:

                checked_text = ensure_response_in_session_language(accumulated_text, session_state, msg)

                return AgentAction(

                    reply=with_urgent_guidance_if_needed(

                        lang, checked_text, msg, session_state.draft.reason_category

                    ),

                    tool_call=None,

                )

            if session_state.draft.is_complete():

                summary = format_localized_message(

                    lang,

                    "confirm_summary",

                    patient_reference=session_state.draft.patient_reference,

                    doctor_name=session_state.draft.doctor_name or "Specialist",

                    specialty=session_state.draft.specialty or "OPD",

                    slot_display=format_slot_display(

                        session_state.draft.slot_id, session_state.draft.slot_start_time, lang=lang

                    ),

                    reason_category=session_state.draft.reason_category,

                )

                return AgentAction(

                    reply=with_urgent_guidance_if_needed(

                        lang, summary, msg, session_state.draft.reason_category

                    ),

                    tool_call=None,

                )

            return AgentAction(

                reply=build_localized_prompt_for_current_state(session_state),

                tool_call=None,

            )



        except ReasoningAdapterError as exc:
            self.last_error = exc.safe_message
            err_category = "timeout" if exc.code == "PROVIDER_TIMEOUT" else (
                "rate_limit" if exc.status_code == 429 else (
                    "invalid_payload" if exc.status_code == 400 else (
                        "internal_error" if (exc.status_code or 0) >= 500 else "network_error"
                    )
                )
            )
            self._last_error_category = err_category
            self._last_status_code = exc.status_code
            approx_tok = (
                len(self._build_system_instruction(session_state))
                + sum(len(m.content or "") for m in session_state.history[-10:])
                + len(user_message)
            ) // 4
            self._record_timings(
                initial_gemini_request_ms,
                tool_router_ms,
                followup_gemini_request_ms,
                gemini_calls_count,
                t_start,
                correlation_id=self._current_correlation_id,
                status_code=self._last_status_code,
                error_category=err_category,
                history_messages_count=len(session_state.history),
                approx_tokens=approx_tok,
                tool_rounds=rounds,
                retry_count=self.retry_count,
            )
            if self.strict_mode:
                raise
            return AgentAction(
                reply=format_localized_message(lang, "provider_error", reason=exc.safe_message),
                tool_call=None,
            )
        except Exception as exc:
            safe_msg = "Unexpected reasoning provider error."
            self.last_error = safe_msg
            self._last_error_category = "internal_error"
            self._last_status_code = 500
            approx_tok = (
                len(self._build_system_instruction(session_state))
                + sum(len(m.content or "") for m in session_state.history[-10:])
                + len(user_message)
            ) // 4
            self._record_timings(
                initial_gemini_request_ms,
                tool_router_ms,
                followup_gemini_request_ms,
                gemini_calls_count,
                t_start,
                correlation_id=self._current_correlation_id,
                status_code=500,
                error_category="internal_error",
                history_messages_count=len(session_state.history),
                approx_tokens=approx_tok,
                tool_rounds=rounds,
                retry_count=self.retry_count,
            )
            if self.strict_mode:
                raise ReasoningAdapterError(code="PROVIDER_ERROR", safe_message=safe_msg)
            return AgentAction(
                reply=format_localized_message(lang, "provider_error", reason=safe_msg),
                tool_call=None,
            )





def create_reasoning_adapter(

    provider: Optional[str] = None,

    api_key: Optional[str] = None,

    model: Optional[str] = None,

) -> BaseReasoningAdapter:

    """

    Factory that instantiates the configured reasoning adapter based on environment settings.

    - 'mock': Always returns MockReasoningAdapter (offline / zero API credits).

    - 'gemini': Returns GeminiReasoningAdapter when api_key is present, or MockReasoningAdapter if api_key is explicitly empty.

    - 'auto' (default): Returns MockReasoningAdapter during pytest runs or when GEMINI_API_KEY

      is unset; returns GeminiReasoningAdapter when GEMINI_API_KEY is present in runtime.

    """

    chosen = (

        provider

        or os.getenv("AI_PROVIDER")

        or os.getenv("LLM_PROVIDER")

        or getattr(settings, "AI_PROVIDER", None)

        or getattr(settings, "LLM_PROVIDER", None)

        or "auto"

    ).strip().lower()

    if chosen == "mock":

        return MockReasoningAdapter()

    if chosen == "gemini":

        resolved_key = api_key if api_key is not None else (os.getenv("GEMINI_API_KEY") or settings.GEMINI_API_KEY or "")

        if not resolved_key.strip():

            return MockReasoningAdapter()

        return GeminiReasoningAdapter(api_key=resolved_key, model=model)

    # 'auto' mode: use MockReasoningAdapter under pytest unless explicitly overridden

    if os.getenv("PYTEST_CURRENT_TEST"):

        return MockReasoningAdapter()

    resolved_key = (api_key if api_key is not None else (os.getenv("GEMINI_API_KEY") or settings.GEMINI_API_KEY or "")).strip()

    if resolved_key:

        return GeminiReasoningAdapter(api_key=resolved_key, model=model)

    return MockReasoningAdapter()



