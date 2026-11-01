import hashlib
import base64
import json
import logging
import math
import os
import re
import struct
from typing import Dict, Optional, Tuple, Any, Iterator
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
    _GREETING_AUDIO_CACHE.clear()


# Canonical voice mapping per language for Gnani Timbre v3.0
GNANI_DEFAULT_VOICES: Dict[str, str] = {
    "en": "Shivani",
    "en-IN": "Shivani",
    "te": "Lakshmi",
    "te-IN": "Lakshmi",
    "hi": "Shivani",
    "hi-IN": "Shivani",
    "ta": "Kalpana",
    "ta-IN": "Kalpana",
    "kn": "Chetana",
    "kn-IN": "Chetana",
}

GNANI_TTS_LANGUAGE_MAP: Dict[str, str] = {
    "en": "en-IN",
    "en-in": "en-IN",
    "te": "te-IN",
    "te-in": "te-IN",
    "hi": "hi-IN",
    "hi-in": "hi-IN",
    "ta": "ta-IN",
    "ta-in": "ta-IN",
    "kn": "kn-IN",
    "kn-in": "kn-IN",
}


def normalize_tts_language(lang: Optional[str]) -> str:
    """Normalizes an incoming language string to a supported Gnani Timbre language code."""
    if not lang:
        return settings.GNANI_DEFAULT_LANGUAGE
    normalized = lang.strip().lower()
    return GNANI_TTS_LANGUAGE_MAP.get(normalized, settings.GNANI_DEFAULT_LANGUAGE)


def clean_text_for_speech(text: str) -> str:
    """
    Cleans raw markdown or metadata formatting from text so it sounds natural when synthesized.
    - Strips HTML comments <!-- ... -->
    - Strips internal <draft>...</draft> and HTML tags
    - Strips markdown links [text](url) -> text
    - Strips bold/italics markers (*, _)
    - Strips bullet points (•, -)
    - Strips internal technical IDs (slot-xxx, doc-xxx, PAT-xxx, APT-xxx)
    - Collapses multiple whitespace
    """
    if not text:
        return ""
    # Strip HTML comments
    cleaned = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Strip <draft> tags
    cleaned = re.sub(r"<draft>.*?</draft>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    # Strip any remaining HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    # Strip markdown links
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    # Strip technical slot/doctor/patient IDs and prefixes
    cleaned = re.sub(r"\b(?:Slot\s*ID|Doctor\s*ID|Patient\s*ID|Reference\s*ID)\s*[:#-]?\s*[A-Za-z0-9_-]+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:slot|doc)-[A-Za-z0-9_-]+\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bPAT-\d+-[A-Za-z0-9-]+\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bAPT-\d+-[A-Za-z0-9-]+\b", "", cleaned, flags=re.IGNORECASE)
    # Strip asterisks, hashes, backticks, bullet symbols
    cleaned = re.sub(r"[*#`_~•]", " ", cleaned)
    # Collapse consecutive whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n", cleaned)
    cleaned = cleaned.strip()

    # Optimization: Strip repetitive introductory conversational filler for spoken responses
    # so speech generation begins directly with the key information without wasting TTS cycles
    filler_patterns = [
        r"^welcome to aarogya one hospital[.,! ]+(?:i am medivoice ai[.,! ]+)?(?:how can i (?:help|assist) you today\??)?",
        r"^(?:hello|hi|namaste|greetings)[.,! ]+(?:welcome to aarogya one hospital[.,! ]+)?",
        r"^(?:i would be (?:pleased|happy|glad) to (?:help|assist) you with (?:scheduling|booking) an appointment with)\s+",
        r"^(?:i can (?:certainly|definitely) help you (?:schedule|book) an appointment with)\s+",
        r"^(?:certainly|sure)[,! ]+(?:let me check (?:the|his|her) available appointments?[.,! ]+)?",
    ]
    for pat in filler_patterns:
        subbed = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
        # Only apply if sufficient content remains (prevent stripping standalone greetings)
        if len(subbed.split()) >= 4:
            cleaned = subbed

    return cleaned


def generate_synthetic_wav(duration_seconds: float = 1.0, frequency: float = 440.0) -> bytes:
    """
    Generates a valid, browser-compatible 16-bit PCM WAV audio sequence (single channel, 16kHz).
    Provides offline and test audio responses that can be genuinely decoded and played by HTML5 Audio.
    """
    sample_rate = 16000
    num_samples = int(sample_rate * max(0.2, min(duration_seconds, 5.0)))
    audio_data = bytearray()
    
    # Generate smooth pleasant chime with envelope
    for i in range(num_samples):
        envelope = min(1.0, i / 800.0, (num_samples - i) / 800.0)
        # Primary tone with gentle harmonic
        sample_val = 0.8 * math.sin(2 * math.pi * frequency * i / sample_rate) + \
                     0.2 * math.sin(4 * math.pi * frequency * i / sample_rate)
        sample = int(12000 * envelope * sample_val)
        clamped = max(-32768, min(32767, sample))
        audio_data.extend(struct.pack("<h", clamped))

    data_size = len(audio_data)
    comment_data = b"MOCK_AUDIO_CONTENT:"
    info_chunk = b"LIST" + struct.pack("<I", len(comment_data) + 4) + b"INFO" + comment_data
    total_size = 36 + data_size + len(info_chunk)

    header = bytearray()
    header.extend(b"RIFF")
    header.extend(struct.pack("<I", total_size))
    header.extend(b"WAVEfmt ")
    header.extend(struct.pack("<I", 16))          # Subchunk1Size for PCM
    header.extend(struct.pack("<H", 1))           # AudioFormat 1 = PCM
    header.extend(struct.pack("<H", 1))           # NumChannels = 1 (Mono)
    header.extend(struct.pack("<I", sample_rate)) # SampleRate
    header.extend(struct.pack("<I", sample_rate * 2)) # ByteRate = SampleRate * NumChannels * BitsPerSample/8
    header.extend(struct.pack("<H", 2))           # BlockAlign = NumChannels * BitsPerSample/8
    header.extend(struct.pack("<H", 16))          # BitsPerSample = 16
    header.extend(b"data")
    header.extend(struct.pack("<I", data_size))

    return bytes(header + audio_data + info_chunk)


class GnaniTimbreTTS:
    """
    Client for Gnani Timbre Text-to-Speech (TTS) API.
    
    Features:
    - Synthesizes multilingual assistant speech across 5 hospital languages (English, Telugu, Hindi, Tamil, Kannada).
    - Cleans Markdown and clinical metadata before synthesis.
    - Authenticates exclusively on the backend using X-API-Key-ID.
    - Handles timeouts, rate limits, audio content-type headers, and errors.
    - Provides a zero-cost local mock mode that generates playable WAV audio for local testing.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        default_voice: Optional[str] = None,
        speed: float = 1.0,
        timeout_seconds: Optional[float] = None,
        http_client: Optional[httpx.Client] = None,
    ):
        resolved_key = api_key if api_key is not None else (os.getenv("GNANI_API_KEY") or settings.GNANI_API_KEY)
        self.api_key: str = (resolved_key or "").strip()

        resolved_base = api_base or os.getenv("GNANI_API_BASE") or settings.GNANI_API_BASE
        self.api_base: str = (resolved_base or "https://api.vachana.ai").rstrip("/")

        resolved_model = model or os.getenv("GNANI_TTS_MODEL") or settings.GNANI_TTS_MODEL or "timbre-v3.0"
        self.model: str = resolved_model.strip()

        self._custom_default_voice: bool = default_voice is not None
        self.default_voice: str = default_voice or os.getenv("GNANI_TTS_VOICE") or settings.GNANI_TTS_VOICE or "Shivani"
        self.speed: float = float(speed)

        raw_timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.getenv("VOICE_REQUEST_TIMEOUT_SECONDS") or settings.VOICE_REQUEST_TIMEOUT_SECONDS or 20.0)
        )
        self.timeout_seconds: float = min(max(float(raw_timeout), 1.0), 60.0)

        raw_sr = os.getenv("GNANI_TTS_SAMPLE_RATE") or getattr(settings, "GNANI_TTS_SAMPLE_RATE", 16000)
        self.sample_rate: int = int(raw_sr)

        self.http_client = http_client
        self._persistent_client: Optional[httpx.Client] = None

    @property
    def is_live_configured(self) -> bool:
        """Indicates whether a non-empty Gnani API key is configured."""
        return bool(self.api_key)

    def _get_client(self) -> httpx.Client:
        """Reuses a persistent HTTP client with keep-alive connection pooling to eliminate TLS handshake overhead."""
        if self.http_client is not None:
            return self.http_client
        if self._persistent_client is None or self._persistent_client.is_closed:
            self._persistent_client = httpx.Client(
                timeout=self.timeout_seconds,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10, keepalive_expiry=60.0),
            )
        return self._persistent_client

    def close(self) -> None:
        """Closes persistent HTTP connection pool."""
        if self._persistent_client is not None and not self._persistent_client.is_closed:
            self._persistent_client.close()
            self._persistent_client = None

    def resolve_voice(self, language_code: str, voice: Optional[str] = None) -> str:
        """Resolves the best voice name for a target language."""
        if voice and voice.strip():
            return voice.strip()
        if self._custom_default_voice and self.default_voice:
            return self.default_voice
        # Language specific default
        lang_short = language_code.split("-")[0].lower()
        return GNANI_DEFAULT_VOICES.get(language_code) or GNANI_DEFAULT_VOICES.get(lang_short) or self.default_voice

    def synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> bytes:
        """
        Synthesizes text into audio bytes using Gnani Timbre TTS API.
        Returns binary audio/wav bytes.
        """
        cleaned_text = clean_text_for_speech(text)
        if not cleaned_text:
            raise SpeechServiceError(
                code="EMPTY_TEXT",
                safe_message="Cannot synthesize empty text into speech.",
                status_code=400,
            )

        gnani_lang = normalize_tts_language(language)
        chosen_voice = self.resolve_voice(gnani_lang, voice)
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
            return synth_audio

        url = f"{self.api_base}/api/v1/tts/inference"
        headers = {
            "X-API-Key-ID": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "MediVoice-AI-TimbreClient/1.0",
        }

        payload = {
            "text": cleaned_text,
            "voice": chosen_voice,
            "model": self.model,
            "language": gnani_lang,
            "speed": chosen_speed,
            "audio_config": {
                "container": "wav",
                "encoding": "linear_pcm",
                "sample_rate": self.sample_rate,
                "num_channels": 1,
                "sample_width": 2,
            },
        }

        try:
            client = self._get_client()
            response = client.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise SpeechServiceError(
                code="PROVIDER_TIMEOUT",
                safe_message=f"Gnani Timbre TTS request timed out after {self.timeout_seconds}s.",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise SpeechServiceError(
                code="PROVIDER_NETWORK_ERROR",
                safe_message="Network communication error while reaching Gnani Timbre TTS.",
                status_code=502,
            ) from exc

        if response.status_code == 401 or response.status_code == 403:
            raise SpeechServiceError(
                code="AUTHENTICATION_FAILURE",
                safe_message="Gnani API authentication failed. Verify GNANI_API_KEY.",
                status_code=response.status_code,
            )
        elif response.status_code == 429:
            raise SpeechServiceError(
                code="RATE_LIMIT_EXCEEDED",
                safe_message="Gnani Timbre TTS rate limit exceeded. Please wait a moment and try again.",
                status_code=429,
            )
        elif response.status_code >= 500:
            raise SpeechServiceError(
                code="PROVIDER_ERROR",
                safe_message=f"Gnani Timbre TTS service error (HTTP {response.status_code}).",
                status_code=response.status_code,
            )
        elif response.status_code != 200:
            raise SpeechServiceError(
                code="PROVIDER_HTTP_ERROR",
                safe_message=f"Gnani Timbre TTS returned HTTP {response.status_code}.",
                status_code=response.status_code,
            )

        content = response.content
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

        return content

    def stream_synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield ordered raw PCM chunks from Gnani Timbre's REST SSE endpoint.

        The provider SSE envelopes are parsed here and audio base64 is decoded.
        The MediVoice API layer can then re-encode only the final patient-facing
        audio chunks, without forwarding provider text or error details.
        """
        cleaned_text = clean_text_for_speech(text)
        if not cleaned_text:
            raise SpeechServiceError(
                code="EMPTY_TEXT",
                safe_message="Cannot synthesize empty text into speech.",
                status_code=400,
            )

        if not self.is_live_configured:
            raise SpeechServiceError(
                code="STREAMING_UNAVAILABLE",
                safe_message="Gnani Timbre streaming is unavailable without live provider credentials.",
                status_code=503,
            )

        gnani_lang = normalize_tts_language(language)
        chosen_voice = self.resolve_voice(gnani_lang, voice)
        chosen_speed = float(speed) if speed is not None else self.speed
        url = f"{self.api_base}/api/v1/tts/sse"
        headers = {
            "X-API-Key-ID": self.api_key,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "MediVoice-AI-TimbreClient/1.0",
        }
        payload = {
            "text": cleaned_text,
            "voice": chosen_voice,
            "model": self.model,
            "language": gnani_lang,
            "speed": chosen_speed,
            "audio_config": {
                "container": "raw",
                "encoding": "linear_pcm",
                "sample_rate": self.sample_rate,
                "num_channels": 1,
                "sample_width": 2,
            },
        }

        client = self._get_client()
        try:
            with client.stream("POST", url, headers=headers, json=payload, timeout=self.timeout_seconds) as response:
                if response.status_code != 200:
                    code = "PROVIDER_HTTP_ERROR"
                    if response.status_code in (401, 403):
                        code = "AUTHENTICATION_FAILURE"
                    elif response.status_code == 429:
                        code = "RATE_LIMIT_EXCEEDED"
                    elif response.status_code >= 500:
                        code = "PROVIDER_ERROR"
                    logger.warning("Gnani Timbre SSE rejected request (HTTP %s)", response.status_code)
                    raise SpeechServiceError(
                        code=code,
                        safe_message=f"Gnani Timbre streaming request failed (HTTP {response.status_code}).",
                        status_code=response.status_code if response.status_code >= 400 else 502,
                    )

                if "text/event-stream" not in response.headers.get("content-type", "").lower():
                    raise SpeechServiceError(
                        code="INVALID_PROVIDER_RESPONSE",
                        safe_message="Gnani Timbre returned an unexpected streaming content type.",
                        status_code=502,
                    )

                current_event = "message"
                data_lines: list[str] = []
                expected_chunk_index = 1
                output_chunk_index = 1
                received_audio = False
                completed = False

                for line in response.iter_lines():
                    if not line:
                        if not data_lines:
                            current_event = "message"
                            continue
                        try:
                            event_data = json.loads("\n".join(data_lines))
                        except (TypeError, ValueError) as exc:
                            raise SpeechServiceError(
                                code="INVALID_PROVIDER_RESPONSE",
                                safe_message="Gnani Timbre returned a malformed streaming event.",
                                status_code=502,
                            ) from exc
                        data_lines = []

                        if current_event == "start":
                            yield {"type": "start"}
                        elif current_event == "chunk":
                            try:
                                chunk_index = int(event_data["chunk_index"])
                                encoded_audio = event_data.get("audio", "")
                                audio_chunk = base64.b64decode(encoded_audio, validate=True) if encoded_audio else b""
                            except (KeyError, TypeError, ValueError) as exc:
                                raise SpeechServiceError(
                                    code="INVALID_PROVIDER_RESPONSE",
                                    safe_message="Gnani Timbre returned an invalid audio chunk.",
                                    status_code=502,
                                ) from exc
                            if chunk_index != expected_chunk_index:
                                raise SpeechServiceError(
                                    code="OUT_OF_ORDER_AUDIO_CHUNK",
                                    safe_message="Gnani Timbre audio chunks arrived out of order.",
                                    status_code=502,
                                )
                            expected_chunk_index += 1
                            if audio_chunk:
                                received_audio = True
                                yield {"type": "chunk", "chunk_index": output_chunk_index, "audio": audio_chunk}
                                output_chunk_index += 1
                        elif current_event == "complete":
                            if event_data.get("audio"):
                                try:
                                    chunk_index = int(event_data["chunk_index"])
                                    audio_chunk = base64.b64decode(event_data["audio"], validate=True)
                                except (KeyError, TypeError, ValueError) as exc:
                                    raise SpeechServiceError(
                                        code="INVALID_PROVIDER_RESPONSE",
                                        safe_message="Gnani Timbre returned an invalid final audio chunk.",
                                        status_code=502,
                                    ) from exc
                                if chunk_index != expected_chunk_index:
                                    raise SpeechServiceError(
                                        code="OUT_OF_ORDER_AUDIO_CHUNK",
                                        safe_message="Gnani Timbre final audio chunk arrived out of order.",
                                        status_code=502,
                                    )
                                expected_chunk_index += 1
                                if audio_chunk:
                                    received_audio = True
                                    yield {"type": "chunk", "chunk_index": output_chunk_index, "audio": audio_chunk}
                                    output_chunk_index += 1
                            if not received_audio:
                                raise SpeechServiceError(
                                    code="EMPTY_AUDIO_STREAM",
                                    safe_message="Gnani Timbre completed without audio.",
                                    status_code=502,
                                )
                            completed = True
                            yield {"type": "complete", "chunk_index": output_chunk_index - 1}
                            return
                        elif current_event == "error":
                            raise SpeechServiceError(
                                code="PROVIDER_STREAM_ERROR",
                                safe_message="Gnani Timbre could not complete streaming synthesis.",
                                status_code=502,
                            )
                        current_event = "message"
                        continue

                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].strip())

                if data_lines:
                    raise SpeechServiceError(
                        code="INCOMPLETE_PROVIDER_EVENT",
                        safe_message="Gnani Timbre stream ended in an incomplete event.",
                        status_code=502,
                    )
                if not completed:
                    raise SpeechServiceError(
                        code="INCOMPLETE_AUDIO_STREAM",
                        safe_message="Gnani Timbre stream ended before completion.",
                        status_code=502,
                    )
        except httpx.TimeoutException as exc:
            raise SpeechServiceError(
                code="PROVIDER_TIMEOUT",
                safe_message="Gnani Timbre streaming request timed out.",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise SpeechServiceError(
                code="PROVIDER_NETWORK_ERROR",
                safe_message="Network communication error while reaching Gnani Timbre streaming.",
                status_code=502,
            ) from exc
