import time
import logging
import os
import re
from typing import Dict, Optional, Tuple, Any
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class SpeechServiceError(Exception):
    """Domain exception for Speech-to-Text and Text-to-Speech operations."""

    def __init__(
        self,
        code: str,
        safe_message: str,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.status_code = status_code
        self.details = details or {}


# Canonical language code mappings for Gnani Prisma STT
GNANI_STT_LANGUAGE_MAP: Dict[str, str] = {
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
    "indic-auto": "indic-auto",
    "auto": "indic-auto",
}

# Reverse mapping from Gnani language code to internal 2-letter code
INTERNAL_LANG_MAP: Dict[str, str] = {
    "en-in": "en",
    "en": "en",
    "te-in": "te",
    "te": "te",
    "hi-in": "hi",
    "hi": "hi",
    "ta-in": "ta",
    "ta": "ta",
    "kn-in": "kn",
    "kn": "kn",
}

# Supported audio MIME types for upload
ALLOWED_AUDIO_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/webm",
    "audio/ogg",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/m4a",
    "audio/flac",
    "application/octet-stream",  # frequently sent by browsers when recording blobs
}

# Maximum audio upload size (15 MB ~ approx 2 minutes of uncompressed audio)
MAX_AUDIO_BYTES = 15 * 1024 * 1024


def normalize_stt_language(lang: Optional[str]) -> str:
    """Normalizes an incoming language string to a supported Gnani Prisma language code."""
    if not lang:
        return settings.GNANI_DEFAULT_LANGUAGE
    normalized = lang.strip().lower()
    return GNANI_STT_LANGUAGE_MAP.get(normalized, settings.GNANI_DEFAULT_LANGUAGE)


def map_to_internal_language(gnani_lang: Optional[str]) -> str:
    """Maps a Gnani language code back to our internal language identifier ('en', 'te', etc.)."""
    if not gnani_lang:
        return "en"
    clean = gnani_lang.strip().lower()
    return INTERNAL_LANG_MAP.get(clean, "en")


def convert_audio_to_wav(audio_bytes: bytes, content_type: Optional[str] = None) -> Tuple[bytes, str, str]:
    """
    Ensures audio is in 16kHz mono 16-bit PCM WAV format.
    Gnani Prisma STT requires standard audio formats (wav, mp3, aac, ogg, flac, m4a - rejecting WebM).
    Returns (wav_bytes, safe_filename, mime_type).
    """
    # If already a valid WAV with RIFF header, return as-is
    if len(audio_bytes) >= 44 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return audio_bytes, "patient_recording.wav", "audio/wav"

    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        logger.warning("imageio_ffmpeg not available: %s", exc)
        safe_name = "audio.wav" if (content_type and "wav" in content_type) else "audio.webm"
        return audio_bytes, safe_name, content_type or "audio/wav"

    import subprocess
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", "pipe:0",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=audio_bytes,
            capture_output=True,
            check=True,
            timeout=15.0,
        )
        if proc.stdout and len(proc.stdout) >= 44 and proc.stdout[:4] == b"RIFF":
            return proc.stdout, "patient_recording.wav", "audio/wav"
    except Exception as pipe_exc:
        logger.warning("FFmpeg pipe conversion failed (%s), attempting temp file fallback...", pipe_exc)
        import tempfile
        ext = ".webm" if (content_type and "webm" in content_type) else ".bin"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as in_f:
            in_f.write(audio_bytes)
            in_path = in_f.name
        out_path = in_path + ".wav"
        try:
            cmd_file = [
                ffmpeg_exe,
                "-y",
                "-i", in_path,
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                out_path,
            ]
            subprocess.run(cmd_file, capture_output=True, check=True, timeout=15.0)
            with open(out_path, "rb") as out_f:
                converted = out_f.read()
            if converted and len(converted) >= 44 and converted[:4] == b"RIFF":
                return converted, "patient_recording.wav", "audio/wav"
        except Exception as file_exc:
            logger.error("FFmpeg file conversion failed: %s", file_exc)
        finally:
            for p in [in_path, out_path]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

    safe_name = "audio.wav" if (content_type and "wav" in content_type) else "audio.webm"
    return audio_bytes, safe_name, content_type or "audio/wav"


class GnaniPrismaSTT:
    """
    Client for Gnani Prisma Speech-to-Text (STT) API v3.
    
    Features:
    - Transcribes Indian multilingual patient voice input (English, Telugu, Hindi, Tamil, Kannada).
    - Validates audio format, size, and duration constraints.
    - Authenticates exclusively on the backend using X-API-Key-ID.
    - Handles timeouts, rate limits, empty audio, and malformed provider responses.
    - Provides a zero-cost local mock mode for development and testing.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        http_client: Optional[httpx.Client] = None,
    ):
        resolved_key = api_key if api_key is not None else (os.getenv("GNANI_API_KEY") or settings.GNANI_API_KEY)
        self.api_key: str = (resolved_key or "").strip()

        resolved_base = api_base or os.getenv("GNANI_API_BASE") or settings.GNANI_API_BASE
        self.api_base: str = (resolved_base or "https://api.vachana.ai").rstrip("/")

        resolved_model = model or os.getenv("GNANI_STT_MODEL") or settings.GNANI_STT_MODEL or "prisma-v3.0"
        self.model: str = resolved_model.strip()

        raw_timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.getenv("VOICE_REQUEST_TIMEOUT_SECONDS") or settings.VOICE_REQUEST_TIMEOUT_SECONDS or 20.0)
        )
        self.timeout_seconds: float = min(max(float(raw_timeout), 1.0), 60.0)

        self.http_client = http_client

    @property
    def is_live_configured(self) -> bool:
        """Indicates whether a non-empty Gnani API key is configured."""
        return bool(self.api_key)

    def validate_audio(self, audio_bytes: bytes, content_type: Optional[str] = None) -> None:
        """Validates incoming audio bytes and content type."""
        if not audio_bytes or len(audio_bytes) < 32:
            raise SpeechServiceError(
                code="EMPTY_AUDIO",
                safe_message="Received empty or truncated audio data. Please record and try again.",
                status_code=400,
            )

        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise SpeechServiceError(
                code="AUDIO_TOO_LARGE",
                safe_message="Audio recording exceeds maximum allowed size (15 MB).",
                status_code=413,
            )

        if content_type:
            # Strip parameters like '; codecs=opus'
            base_type = content_type.split(";")[0].strip().lower()
            if base_type not in ALLOWED_AUDIO_MIME_TYPES:
                raise SpeechServiceError(
                    code="INVALID_AUDIO_FORMAT",
                    safe_message=f"Unsupported audio format '{content_type}'. Please use WAV, WebM, OGG, or MP3.",
                    status_code=415,
                )

    def _mock_transcribe(self, audio_bytes: bytes, language_code: str) -> Dict[str, Any]:
        """Provides simulated transcription for testing and offline local development."""
        lang_internal = map_to_internal_language(language_code)
        
        # Check if the audio contains an ASCII marker from tests
        raw_text = ""
        try:
            decoded = audio_bytes.decode("utf-8", errors="ignore")
            if "MOCK_AUDIO_CONTENT:" in decoded:
                raw_text = decoded.split("MOCK_AUDIO_CONTENT:")[1].strip()
        except Exception:
            pass

        if not raw_text:
            default_phrases = {
                "te": "నాకు గుండె నొప్పిగా ఉంది కార్డియాలజిస్ట్ కావాలి",
                "ta": "எனக்கு நெஞ்சு வலி உள்ளது இருதய மருத்துவரை பார்க்க வேண்டும்",
                "kn": "ನನಗೆ ಎದೆ ನೋವು ಇದೆ ಕಾರ್ಡಿಯಾಲಜಿಸ್ಟ್ ಬೇಕು",
                "hi": "मुझे सीने में दर्द है हृदय रोग विशेषज्ञ चाहिए",
                "en": "I have chest pain and need to see a cardiologist",
            }
            raw_text = default_phrases.get(lang_internal, "I need to book an appointment with a doctor")

        return {
            "transcript": raw_text,
            "full_transcript": raw_text,
            "language_code": language_code,
            "detected_language": lang_internal,
            "confidence": 0.96,
            "model": "mock-prisma",
            "transcode_ms": 0.0,
            "stt_ms": 1.0,
        }

    def transcribe(
        self,
        audio_bytes: bytes,
        language: Optional[str] = None,
        content_type: Optional[str] = "audio/wav",
        filename: Optional[str] = "audio.wav",
    ) -> Dict[str, Any]:
        """
        Transcribes audio data using Gnani Prisma STT API v3.
        Returns a dictionary with 'transcript', 'language_code', 'detected_language', and metadata.
        """
        self.validate_audio(audio_bytes, content_type)
        gnani_lang = normalize_stt_language(language)

        # Check if running in automated test suite or if mock audio marker is supplied
        is_automated_test = bool(
            os.getenv("PYTEST_CURRENT_TEST")
            or b"MOCK_AUDIO_CONTENT:" in audio_bytes
            or os.getenv("TESTING", "").lower() in ("1", "true")
        )

        # In mock mode (no key configured) or explicit offline automated test without mock HTTP client
        if not self.is_live_configured or (self.http_client is None and is_automated_test):
            return self._mock_transcribe(audio_bytes, gnani_lang)

        url = f"{self.api_base}/stt/v3"
        headers = {
            "X-API-Key-ID": self.api_key,
            "User-Agent": "MediVoice-AI-PrismaClient/1.0",
        }

        # Convert audio to 16kHz mono WAV if not already standard WAV (e.g. WebM/Opus from browser)
        t_tc_start = time.perf_counter()
        upload_bytes, safe_filename, upload_mime = convert_audio_to_wav(audio_bytes, content_type)
        transcode_ms = (time.perf_counter() - t_tc_start) * 1000

        form_data = {
            "model": self.model,
            "language_code": gnani_lang,
            "format": "transcribe",
        }

        files = {
            "audio_file": (safe_filename, upload_bytes, upload_mime),
        }

        t_http_start = time.perf_counter()
        try:
            if self.http_client is not None:
                response = self.http_client.post(
                    url,
                    headers=headers,
                    data=form_data,
                    files=files,
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(
                        url,
                        headers=headers,
                        data=form_data,
                        files=files,
                    )
        except httpx.TimeoutException as exc:
            raise SpeechServiceError(
                code="PROVIDER_TIMEOUT",
                safe_message=f"Gnani Prisma STT request timed out after {self.timeout_seconds}s.",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise SpeechServiceError(
                code="PROVIDER_NETWORK_ERROR",
                safe_message="Network communication error while reaching Gnani Prisma STT.",
                status_code=502,
            ) from exc

        # Handle HTTP status codes
        if response.status_code == 401 or response.status_code == 403:
            raise SpeechServiceError(
                code="AUTHENTICATION_FAILURE",
                safe_message="Gnani API authentication failed. Verify GNANI_API_KEY.",
                status_code=response.status_code,
            )
        elif response.status_code == 429:
            raise SpeechServiceError(
                code="RATE_LIMIT_EXCEEDED",
                safe_message="Gnani Prisma STT rate limit exceeded. Please wait a moment and try again.",
                status_code=429,
            )
        elif response.status_code >= 500:
            raise SpeechServiceError(
                code="PROVIDER_ERROR",
                safe_message=f"Gnani Prisma STT service error (HTTP {response.status_code}).",
                status_code=response.status_code,
            )
        elif response.status_code != 200:
            err_msg = f"Gnani Prisma STT returned HTTP {response.status_code}."
            err_type = "UNKNOWN"
            try:
                err_json = response.json()
                if "error" in err_json and isinstance(err_json["error"], dict):
                    err_type = err_json["error"].get("type", err_type)
                    err_msg = err_json["error"].get("message", err_msg)
            except Exception:
                pass
            logger.error(
                "Gnani STT error [%s - HTTP %s]: %s (sent %d bytes as %s)",
                err_type,
                response.status_code,
                err_msg,
                len(upload_bytes),
                upload_mime,
            )
            raise SpeechServiceError(
                code=f"PROVIDER_{err_type}" if err_type != "UNKNOWN" else "PROVIDER_HTTP_ERROR",
                safe_message=f"Speech recognition error: {err_msg}",
                status_code=response.status_code,
                details={"error_type": err_type, "response": response.text[:500]},
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise SpeechServiceError(
                code="INVALID_PROVIDER_RESPONSE",
                safe_message="Gnani Prisma STT returned malformed non-JSON response.",
                status_code=502,
            ) from exc

        # Extract transcript from various Gnani response formats
        transcript = ""
        if isinstance(data, dict):
            if "full_transcript" in data and isinstance(data["full_transcript"], str):
                transcript = data["full_transcript"]
            elif "transcript" in data and isinstance(data["transcript"], str):
                transcript = data["transcript"]
            elif "segments" in data and isinstance(data["segments"], list):
                segment_texts = [s.get("text", "") for s in data["segments"] if isinstance(s, dict)]
                transcript = " ".join(t.strip() for t in segment_texts if t.strip())

        transcript = transcript.strip()

        if not transcript:
            raise SpeechServiceError(
                code="EMPTY_TRANSCRIPTION",
                safe_message="No clear speech was recognized in the audio. Please speak clearly into the microphone.",
                status_code=422,
                details={"raw_response": data},
            )

        # Prisma can return an explicit detected_language_code. Prefer it over the
        # submitted language hint; otherwise language metadata falsely mirrors input.
        resolved_lang_code = data.get("detected_language_code") or data.get("language_code") or gnani_lang
        detected_internal = map_to_internal_language(resolved_lang_code)

        stt_ms = (time.perf_counter() - t_http_start) * 1000
        return {
            "transcript": transcript,
            "full_transcript": transcript,
            "language_code": resolved_lang_code,
            "detected_language": detected_internal,
            "confidence": data.get("confidence", 0.95),
            "model": self.model,
            "segments": data.get("segments", []),
            "transcode_ms": round(transcode_ms, 2),
            "stt_ms": round(stt_ms, 2),
        }
