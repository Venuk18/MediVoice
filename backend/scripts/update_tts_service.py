# -*- coding: utf-8 -*-
file_path = "backend/app/services/speech/tts_service.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read().replace("\r\n", "\n")

old_top = """import math
import os
import re
import struct
from typing import Dict, Optional, Any
import httpx

from app.core.config import settings
from app.services.speech.stt_service import SpeechServiceError"""

new_top = """import hashlib
import logging
import math
import os
import re
import struct
from typing import Dict, Optional, Tuple, Any
import httpx

from app.core.config import settings
from app.services.speech.stt_service import SpeechServiceError

logger = logging.getLogger(__name__)

# Canonical fixed hospital welcome greetings eligible for zero-latency static caching
FIXED_HOSPITAL_GREETINGS = {
    "Welcome to Aarogya One Hospital! How can I help you today?",
    "ఆరోగ్య వన్ హాస్పిటల్‌కు స్వాగతం! ఈరోజు నేను మీకు ఎలా సహాయపడగలను?",
    "आरोग्य वन अस्पताल में आपका स्वागत है! आज मैं आपकी क्या मदद कर सकता हूँ?",
    "ஆரோக்யா ஒன் மருத்துவமனைக்கு வரவேற்கிறோம்! இன்று நான் உங்களுக்கு எவ்வாறு உதவ முடியும்?",
    "ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಗೆ ಸುಸ್ವಾಗತ! ಇಂದು ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
}

# In-memory cache for fixed greeting audio: (language, voice, speed, text_hash) -> bytes
_GREETING_AUDIO_CACHE: Dict[Tuple[str, str, float, str], bytes] = {}


def is_fixed_greeting(text: str) -> bool:
    if not text:
        return False
    raw = text.strip()
    if raw in FIXED_HOSPITAL_GREETINGS:
        return True
    cleaned = clean_text_for_speech(text)
    return any(cleaned == clean_text_for_speech(g) for g in FIXED_HOSPITAL_GREETINGS)


def get_greeting_cache_info() -> Dict[str, Any]:
    return {
        "cached_count": len(_GREETING_AUDIO_CACHE),
        "keys": [f"{k[0]}:{k[1]}:{k[2]}" for k in _GREETING_AUDIO_CACHE.keys()],
    }


def clear_greeting_cache() -> None:
    _GREETING_AUDIO_CACHE.clear()"""

assert old_top in content, "old_top not found"
content = content.replace(old_top, new_top, 1)

old_synth = """        chosen_voice = self.resolve_voice(gnani_lang, voice)
        chosen_speed = float(speed) if speed is not None else self.speed

        is_automated_test = bool(
            os.getenv("PYTEST_CURRENT_TEST")
            or os.getenv("TESTING", "").lower() in ("1", "true")
        )

        # If live credentials are missing or in offline automated test mode (without an explicit mock HTTP client), return playable synthetic WAV
        if not self.is_live_configured or (self.http_client is None and is_automated_test):
            # Duration approximates word count (150 words per minute ~ 2.5 words per second)
            word_count = len(cleaned_text.split())
            approx_duration = max(0.5, min(word_count / 2.5, 4.0))
            return generate_synthetic_wav(duration_seconds=approx_duration, frequency=523.25)"""

new_synth = """        chosen_voice = self.resolve_voice(gnani_lang, voice)
        chosen_speed = float(speed) if speed is not None else self.speed

        # Zero-latency cache lookup for fixed hospital welcome greeting
        cache_key = None
        if is_fixed_greeting(text):
            text_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()[:16]
            cache_key = (gnani_lang, chosen_voice, round(chosen_speed, 2), text_hash)
            if cache_key in _GREETING_AUDIO_CACHE:
                cached_bytes = _GREETING_AUDIO_CACHE[cache_key]
                logger.info(
                    "Served cached greeting audio for lang=%s voice=%s (%d bytes, 0ms latency)",
                    gnani_lang, chosen_voice, len(cached_bytes),
                )
                return cached_bytes

        is_automated_test = bool(
            os.getenv("PYTEST_CURRENT_TEST")
            or os.getenv("TESTING", "").lower() in ("1", "true")
        )

        # If live credentials are missing or in offline automated test mode (without an explicit mock HTTP client), return playable synthetic WAV
        if not self.is_live_configured or (self.http_client is None and is_automated_test):
            # Duration approximates word count (150 words per minute ~ 2.5 words per second)
            word_count = len(cleaned_text.split())
            approx_duration = max(0.5, min(word_count / 2.5, 4.0))
            synth_audio = generate_synthetic_wav(duration_seconds=approx_duration, frequency=523.25)
            if cache_key:
                _GREETING_AUDIO_CACHE[cache_key] = synth_audio
            return synth_audio"""

assert old_synth in content, "old_synth not found"
content = content.replace(old_synth, new_synth, 1)

old_return = """        content = response.content
        if not content or len(content) < 44:
            raise SpeechServiceError(
                code="INVALID_PROVIDER_RESPONSE",
                safe_message="Gnani Timbre TTS returned invalid or empty audio payload.",
                status_code=502,
            )

        return content"""

new_return = """        content = response.content
        if not content or len(content) < 44:
            raise SpeechServiceError(
                code="INVALID_PROVIDER_RESPONSE",
                safe_message="Gnani Timbre TTS returned invalid or empty audio payload.",
                status_code=502,
            )

        if cache_key:
            _GREETING_AUDIO_CACHE[cache_key] = content
            logger.info(
                "Cached fixed greeting audio for lang=%s voice=%s (%d bytes)",
                gnani_lang, chosen_voice, len(content),
            )

        return content"""

assert old_return in content, "old_return not found"
content = content.replace(old_return, new_return, 1)

with open(file_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(content)

print("Successfully updated tts_service.py with fixed greeting cache")
