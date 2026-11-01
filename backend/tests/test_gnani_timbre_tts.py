import json
import httpx
import pytest

from app.services.speech.tts_service import (
    GnaniTimbreTTS,
    clean_text_for_speech,
    generate_synthetic_wav,
    normalize_tts_language,
)
from app.services.speech.stt_service import SpeechServiceError


def test_clean_text_for_speech():
    raw_md = (
        "Here is the details:\n"
        "- Specialist: [Dr. Rajesh Sharma](file:///dr-sharma)\n"
        "• Status: *Available*\n"
        "<draft>{\"doctor_id\": \"doc-1\"}</draft>"
    )
    cleaned = clean_text_for_speech(raw_md)
    assert "<draft>" not in cleaned
    assert "file:///" not in cleaned
    assert "Dr. Rajesh Sharma" in cleaned
    assert "*" not in cleaned
    assert "•" not in cleaned


def test_generate_synthetic_wav():
    wav_bytes = generate_synthetic_wav(duration_seconds=0.5, frequency=440.0)
    assert len(wav_bytes) > 44
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"
    assert wav_bytes[12:16] == b"fmt "
    assert b"data" in wav_bytes


def test_tts_offline_mock_mode():
    """Without GNANI_API_KEY, TTS generates playable WAV audio."""
    tts = GnaniTimbreTTS(api_key="")
    assert not tts.is_live_configured

    audio = tts.synthesize("Welcome to Aarogya One Hospital", language="en")
    assert len(audio) > 44
    assert audio[:4] == b"RIFF"
    assert audio[8:12] == b"WAVE"


def test_tts_empty_text_error():
    tts = GnaniTimbreTTS(api_key="mock-key")
    with pytest.raises(SpeechServiceError) as exc_info:
        tts.synthesize("   <draft>{}</draft>   ")
    assert exc_info.value.code == "EMPTY_TEXT"
    assert exc_info.value.status_code == 400


def test_tts_live_request():
    captured = {}
    synthetic_wav = generate_synthetic_wav(1.0)

    def mock_tts_transport(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            content=synthetic_wav,
            headers={"Content-Type": "audio/wav"},
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_tts_transport))
    tts = GnaniTimbreTTS(
        api_key="gnani-secret-tts-key",
        model="timbre-v3.0",
        default_voice="Ananya",
        http_client=mock_client,
    )

    audio = tts.synthesize(
        text="నమస్కారం, మీకు ఎలా సహాయపడగలను?",
        language="te-IN",
    )

    assert captured["url"] == "https://api.vachana.ai/api/v1/tts/inference"
    assert captured["headers"]["x-api-key-id"] == "gnani-secret-tts-key"
    assert captured["payload"]["voice"] == "Ananya"
    assert captured["payload"]["language"] == "te-IN"
    assert captured["payload"]["model"] == "timbre-v3.0"
    assert audio == synthetic_wav


def test_tts_auth_failure():
    def auth_err_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Unauthorized"})

    mock_client = httpx.Client(transport=httpx.MockTransport(auth_err_transport))
    tts = GnaniTimbreTTS(api_key="bad-key", http_client=mock_client)

    with pytest.raises(SpeechServiceError) as exc_info:
        tts.synthesize("Hello", language="en")
    assert exc_info.value.code == "AUTHENTICATION_FAILURE"
    assert exc_info.value.status_code == 401


def test_tts_rate_limit():
    def rate_limit_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "Rate limit exceeded"})

    mock_client = httpx.Client(transport=httpx.MockTransport(rate_limit_transport))
    tts = GnaniTimbreTTS(api_key="valid-key", http_client=mock_client)

    with pytest.raises(SpeechServiceError) as exc_info:
        tts.synthesize("Hello", language="en")
    assert exc_info.value.code == "RATE_LIMIT_EXCEEDED"
    assert exc_info.value.status_code == 429


def test_tts_timeout():
    def timeout_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout waiting for Gnani Timbre")

    mock_client = httpx.Client(transport=httpx.MockTransport(timeout_transport))
    tts = GnaniTimbreTTS(api_key="valid-key", http_client=mock_client)

    with pytest.raises(SpeechServiceError) as exc_info:
        tts.synthesize("Hello", language="en")
    assert exc_info.value.code == "PROVIDER_TIMEOUT"
    assert exc_info.value.status_code == 504


def test_greeting_audio_caching():
    from app.services.speech.tts_service import (
        is_fixed_greeting,
        clear_greeting_cache,
        get_greeting_cache_info,
        FIXED_HOSPITAL_GREETINGS,
    )

    clear_greeting_cache()
    greeting_en = "Welcome to Aarogya One Hospital! How can I help you today?"
    dynamic_text = "Your appointment with Dr. Rajesh Sharma has been booked."

    assert is_fixed_greeting(greeting_en) is True
    assert is_fixed_greeting(dynamic_text) is False

    call_count = {"count": 0}
    synthetic_wav = generate_synthetic_wav(1.0)

    def counting_transport(request: httpx.Request) -> httpx.Response:
        call_count["count"] += 1
        return httpx.Response(200, content=synthetic_wav, headers={"Content-Type": "audio/wav"})

    mock_client = httpx.Client(transport=httpx.MockTransport(counting_transport))
    tts = GnaniTimbreTTS(api_key="gnani-key", http_client=mock_client)

    # First call: cache miss, provider invoked
    audio1 = tts.synthesize(greeting_en, language="en")
    assert call_count["count"] == 1
    assert audio1 == synthetic_wav

    # Second call: cache hit, provider NOT invoked (0ms)
    audio2 = tts.synthesize(greeting_en, language="en")
    assert call_count["count"] == 1
    assert audio2 == synthetic_wav

    # Dynamic text: never cached, provider always invoked
    tts.synthesize(dynamic_text, language="en")
    assert call_count["count"] == 2
    tts.synthesize(dynamic_text, language="en")
    assert call_count["count"] == 3

    # Invalidation by voice change
    tts.synthesize(greeting_en, language="en", voice="CustomVoice")
    assert call_count["count"] == 4

    clear_greeting_cache()
    assert get_greeting_cache_info()["cached_count"] == 0


def _sse_event(name, payload):
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"


def test_tts_stream_preserves_order_and_language_configuration():
    pcm1, pcm2 = b"\x01\x00" * 3, b"\x02\x00" * 2
    events = (
        _sse_event("start", {"text": "provider metadata is not forwarded"})
        + _sse_event("chunk", {"chunk_index": 1, "audio": __import__("base64").b64encode(pcm1).decode()})
        + _sse_event("chunk", {"chunk_index": 2, "audio": __import__("base64").b64encode(pcm2).decode()})
        + _sse_event("complete", {})
    ).encode()
    captured = {}

    def transport(request):
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, content=events, headers={"content-type": "text/event-stream"})

    client = httpx.Client(transport=httpx.MockTransport(transport))
    tts = GnaniTimbreTTS(api_key="secret", model="timbre-v3.0", http_client=client)
    result = list(tts.stream_synthesize("నమస్కారం", language="te"))
    assert [x["type"] for x in result] == ["start", "chunk", "chunk", "complete"]
    assert [x["chunk_index"] for x in result if x["type"] == "chunk"] == [1, 2]
    assert [x["audio"] for x in result if x["type"] == "chunk"] == [pcm1, pcm2]
    assert captured["url"].endswith("/api/v1/tts/sse")
    assert captured["payload"]["language"] == "te-IN"
    assert captured["payload"]["voice"] == "Lakshmi"
    assert captured["payload"]["audio_config"] == {
        "container": "raw", "encoding": "linear_pcm", "sample_rate": 16000,
        "num_channels": 1, "sample_width": 2,
    }


@pytest.mark.parametrize("event_data,expected_code", [
    (_sse_event("complete", {}), "EMPTY_AUDIO_STREAM"),
    (_sse_event("chunk", {"chunk_index": 2, "audio": "AQ=="}), "OUT_OF_ORDER_AUDIO_CHUNK"),
    (_sse_event("error", {"message": "sensitive provider text"}), "PROVIDER_STREAM_ERROR"),
])
def test_tts_stream_rejects_empty_malformed_order_and_provider_error(event_data, expected_code):
    body = (event_data if "event: complete" in event_data else _sse_event("start", {}) + event_data).encode()
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, content=body, headers={"content-type": "text/event-stream"}
    )))
    tts = GnaniTimbreTTS(api_key="secret", http_client=client)
    with pytest.raises(SpeechServiceError) as exc_info:
        list(tts.stream_synthesize("Hello", language="en"))
    assert exc_info.value.code == expected_code


def test_tts_stream_requires_live_credentials():
    tts = GnaniTimbreTTS(api_key="")
    with pytest.raises(SpeechServiceError) as exc_info:
        list(tts.stream_synthesize("Hello"))
    assert exc_info.value.code == "STREAMING_UNAVAILABLE"


def test_tts_stream_closes_provider_response_when_consumer_cancels():
    import base64

    class TrackedStream(httpx.SyncByteStream):
        def __init__(self, content):
            self.content = content
            self.closed = False

        def __iter__(self):
            yield self.content

        def close(self):
            self.closed = True

    body = (
        _sse_event("start", {})
        + _sse_event("chunk", {"chunk_index": 1, "audio": base64.b64encode(b"\x01\x00").decode()})
        + _sse_event("complete", {})
    ).encode()
    provider_stream = TrackedStream(body)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, stream=provider_stream, headers={"content-type": "text/event-stream"}
    )))
    tts = GnaniTimbreTTS(api_key="secret", http_client=client)
    events = tts.stream_synthesize("Hello")
    assert next(events)["type"] == "start"
    assert next(events)["type"] == "chunk"
    events.close()
    assert provider_stream.closed is True
