import httpx
import pytest

from app.services.speech.stt_service import (
    GnaniPrismaSTT,
    SpeechServiceError,
    normalize_stt_language,
    map_to_internal_language,
)


def test_normalize_stt_language_and_internal_mapping():
    assert normalize_stt_language("te") == "te-IN"
    assert normalize_stt_language("te-IN") == "te-IN"
    assert normalize_stt_language("hi") == "hi-IN"
    assert normalize_stt_language("ta") == "ta-IN"
    assert normalize_stt_language("kn") == "kn-IN"
    assert normalize_stt_language("en") == "en-IN"
    assert normalize_stt_language("auto") == "indic-auto"
    assert normalize_stt_language("") == "en-IN"

    assert map_to_internal_language("te-IN") == "te"
    assert map_to_internal_language("hi-IN") == "hi"
    assert map_to_internal_language("ta-IN") == "ta"
    assert map_to_internal_language("kn-IN") == "kn"
    assert map_to_internal_language("en-IN") == "en"


def test_stt_audio_validation():
    stt = GnaniPrismaSTT(api_key="mock-key")

    # Empty audio
    with pytest.raises(SpeechServiceError) as exc_empty:
        stt.validate_audio(b"")
    assert exc_empty.value.code == "EMPTY_AUDIO"
    assert exc_empty.value.status_code == 400

    # Truncated audio (< 32 bytes)
    with pytest.raises(SpeechServiceError) as exc_trunc:
        stt.validate_audio(b"RIFF" + b"\x00" * 10)
    assert exc_trunc.value.code == "EMPTY_AUDIO"

    # Unsupported format
    with pytest.raises(SpeechServiceError) as exc_fmt:
        stt.validate_audio(b"RIFF" + b"\x00" * 40, content_type="image/png")
    assert exc_fmt.value.code == "INVALID_AUDIO_FORMAT"
    assert exc_fmt.value.status_code == 415

    # Oversized audio
    with pytest.raises(SpeechServiceError) as exc_large:
        stt.validate_audio(b"X" * (16 * 1024 * 1024))
    assert exc_large.value.code == "AUDIO_TOO_LARGE"
    assert exc_large.value.status_code == 413


def test_stt_offline_mock_mode():
    """When GNANI_API_KEY is unset or empty, mock mode provides simulated transcription."""
    stt = GnaniPrismaSTT(api_key="")
    assert not stt.is_live_configured

    fake_audio = b"RIFF" + b"\x00" * 50
    result = stt.transcribe(fake_audio, language="te", content_type="audio/wav")
    assert result["transcript"]
    assert result["detected_language"] == "te"
    assert result["language_code"] == "te-IN"
    assert result["model"] == "mock-prisma"

    # Custom test marker inside audio payload
    custom_audio = b"RIFF" + b"MOCK_AUDIO_CONTENT:I need Dr. Sharma appointment"
    res_custom = stt.transcribe(custom_audio, language="en")
    assert res_custom["transcript"] == "I need Dr. Sharma appointment"


def test_stt_live_request_parsing():
    """GnaniPrismaSTT successfully sends multipart form request and parses full_transcript."""
    captured = {}

    def mock_gnani_transport(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "full_transcript": "నాకు కార్డియాలజిస్ట్ కావాలి",
                "language_code": "te-IN",
                "confidence": 0.98,
                "segments": [
                    {"segment_id": 0, "start_time": 0.0, "end_time": 1.5, "text": "నాకు కార్డియాలజిస్ట్ కావాలి"}
                ],
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_gnani_transport))
    stt = GnaniPrismaSTT(
        api_key="gnani-secret-key-12345",
        model="prisma-v3.0",
        http_client=mock_client,
    )

    fake_audio = b"RIFF" + b"\x00" * 60
    result = stt.transcribe(fake_audio, language="te-IN")

    assert captured["url"] == "https://api.vachana.ai/stt/v3"
    assert captured["headers"]["x-api-key-id"] == "gnani-secret-key-12345"
    assert result["transcript"] == "నాకు కార్డియాలజిస్ట్ కావాలి"
    assert result["detected_language"] == "te"
    assert result["confidence"] == 0.98


def test_stt_prefers_provider_detected_language_over_request_hint():
    """A provider detection label must win over the selected language hint."""
    def mock_gnani_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "full_transcript": "Hello, I need an appointment",
            "language_code": "te-IN",
            "detected_language_code": "en-IN",
        })

    client = httpx.Client(transport=httpx.MockTransport(mock_gnani_transport))
    stt = GnaniPrismaSTT(api_key="test-key", http_client=client)
    result = stt.transcribe(b"RIFF" + b"\x00" * 60, language="te-IN")

    assert result["language_code"] == "en-IN"
    assert result["detected_language"] == "en"


def test_stt_empty_transcription_error():
    """Empty transcript returned by provider raises EMPTY_TRANSCRIPTION (422)."""
    def empty_transcript_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"full_transcript": "   ", "language_code": "en-IN"},
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(empty_transcript_transport))
    stt = GnaniPrismaSTT(api_key="valid-key", http_client=mock_client)

    with pytest.raises(SpeechServiceError) as exc_info:
        stt.transcribe(b"RIFF" + b"\x00" * 60)
    assert exc_info.value.code == "EMPTY_TRANSCRIPTION"
    assert exc_info.value.status_code == 422


def test_stt_authentication_failure():
    """HTTP 401 from Gnani raises AUTHENTICATION_FAILURE."""
    def auth_fail_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API Key"})

    mock_client = httpx.Client(transport=httpx.MockTransport(auth_fail_transport))
    stt = GnaniPrismaSTT(api_key="bad-key", http_client=mock_client)

    with pytest.raises(SpeechServiceError) as exc_info:
        stt.transcribe(b"RIFF" + b"\x00" * 60)
    assert exc_info.value.code == "AUTHENTICATION_FAILURE"
    assert exc_info.value.status_code == 401


def test_stt_rate_limit_exceeded():
    """HTTP 429 from Gnani raises RATE_LIMIT_EXCEEDED."""
    def rate_limit_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "Quota exceeded"})

    mock_client = httpx.Client(transport=httpx.MockTransport(rate_limit_transport))
    stt = GnaniPrismaSTT(api_key="valid-key", http_client=mock_client)

    with pytest.raises(SpeechServiceError) as exc_info:
        stt.transcribe(b"RIFF" + b"\x00" * 60)
    assert exc_info.value.code == "RATE_LIMIT_EXCEEDED"
    assert exc_info.value.status_code == 429


def test_stt_timeout_handling():
    """Network timeout raises PROVIDER_TIMEOUT."""
    def timeout_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout waiting for Gnani Prisma")

    mock_client = httpx.Client(transport=httpx.MockTransport(timeout_transport))
    stt = GnaniPrismaSTT(api_key="valid-key", http_client=mock_client)

    with pytest.raises(SpeechServiceError) as exc_info:
        stt.transcribe(b"RIFF" + b"\x00" * 60)
    assert exc_info.value.code == "PROVIDER_TIMEOUT"
    assert exc_info.value.status_code == 504


def test_stt_malformed_response():
    """Malformed non-JSON provider response raises INVALID_PROVIDER_RESPONSE."""
    def non_json_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Bad Gateway HTML")

    mock_client = httpx.Client(transport=httpx.MockTransport(non_json_transport))
    stt = GnaniPrismaSTT(api_key="valid-key", http_client=mock_client)

    with pytest.raises(SpeechServiceError) as exc_info:
        stt.transcribe(b"RIFF" + b"\x00" * 60)
    assert exc_info.value.code == "INVALID_PROVIDER_RESPONSE"
    assert exc_info.value.status_code == 502
