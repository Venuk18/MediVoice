"""Run a small, synthetic end-to-end voice latency baseline through FastAPI.

Input speech is generated once per language with the configured Gnani Timbre voice,
then replayed for each trial. This measures a repeatable phrase, not speaker variance.
Transcripts are never written or printed. Synthetic WAV inputs are saved and reused
so later runs can compare identical audio. Gemini/Gnani calls are live.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import statistics
import sys
import time
import uuid
import wave
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.adapters import GeminiReasoningAdapter
from app.agent.conversation_manager import conversation_manager
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app
from app import models as _models  # register all SQLAlchemy metadata on Base
from app.services.speech.tts_service import GnaniTimbreTTS


CASES = {
    "en": "I need an appointment, please.",
    "te": "నాకు అపాయింట్‌మెంట్ కావాలి.",
}
FIELDS = [
    "language", "trial", "correlation_id", "audio_duration_ms", "request_wall_ms",
    "audio_read_ms", "transcode_ms", "stt_ms", "language_detection_ms", "agent_ms",
    "initial_gemini_request_ms", "followup_gemini_request_ms", "gemini_calls_count",
    "tool_ms", "tool_router_ms", "tts_ms", "backend_total_ms", "tts_available", "http_status", "error_code",
]


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct / 100
    low, high = math.floor(rank), math.ceil(rank)
    return ordered[low] if low == high else ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, help="Optional directory for reusable synthetic WAV inputs")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if not settings.GNANI_API_KEY.strip() or not settings.GEMINI_API_KEY.strip():
        parser.error("Live GNANI_API_KEY and GEMINI_API_KEY must be configured in the environment")
    if not isinstance(conversation_manager.adapter, GeminiReasoningAdapter):
        parser.error("AI_PROVIDER must select Gemini for this end-to-end baseline")

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = override_db
    rows: list[dict[str, object]] = []
    try:
        with TestClient(fastapi_app) as client:
            tts = GnaniTimbreTTS()
            synthetic_audio = {}
            audio_duration_ms = {}
            for lang, phrase in CASES.items():
                audio_dir = args.audio_dir or args.output.parent / "synthetic_audio"
                audio_dir.mkdir(parents=True, exist_ok=True)
                audio_path = audio_dir / f"baseline-{lang}.wav"
                if audio_path.is_file():
                    wav_bytes = audio_path.read_bytes()
                else:
                    wav_bytes = tts.synthesize(phrase, language=lang)
                    audio_path.write_bytes(wav_bytes)
                # Some provider WAV responses use an unknown-length RIFF data size.
                # Parse the chunks and use actual payload length instead of nframes.
                offset = 12
                sample_rate = byte_rate = data_bytes = 0
                while offset + 8 <= len(wav_bytes):
                    chunk_id = wav_bytes[offset:offset + 4]
                    chunk_size = int.from_bytes(wav_bytes[offset + 4:offset + 8], "little")
                    chunk_start = offset + 8
                    if chunk_id == b"fmt " and chunk_size >= 16:
                        byte_rate = int.from_bytes(wav_bytes[chunk_start + 8:chunk_start + 12], "little")
                        sample_rate = int.from_bytes(wav_bytes[chunk_start + 4:chunk_start + 8], "little")
                    elif chunk_id == b"data":
                        data_bytes = min(chunk_size, max(0, len(wav_bytes) - chunk_start))
                        break
                    offset = chunk_start + chunk_size + (chunk_size % 2)
                if not data_bytes or not byte_rate or not sample_rate:
                    raise RuntimeError(f"Could not determine synthetic WAV duration for {lang}")
                audio_duration_ms[lang] = 1000 * data_bytes / byte_rate
                synthetic_audio[lang] = wav_bytes

            for lang, wav_bytes in synthetic_audio.items():
                for trial in range(1, args.repeats + 1):
                    correlation_id = str(uuid.uuid4())
                    started = time.perf_counter()
                    response = client.post(
                        "/api/v1/voice/respond",
                        files={"file": ("synthetic.wav", wav_bytes, "audio/wav")},
                        data={"language": lang, "session_id": f"baseline-{lang}-{trial}", "correlation_id": correlation_id},
                    )
                    wall_ms = (time.perf_counter() - started) * 1000
                    if response.status_code != 200:
                        try:
                            error_code = response.json().get("detail", {}).get("code", "HTTP_ERROR")
                        except Exception:
                            error_code = "HTTP_ERROR"
                        rows.append({"language": lang, "trial": trial, "correlation_id": correlation_id,
                                     "audio_duration_ms": round(audio_duration_ms[lang], 2),
                                     "request_wall_ms": round(wall_ms, 2), "http_status": response.status_code,
                                     "error_code": error_code})
                        continue
                    payload = response.json()
                    timing = payload.get("timings") or {}
                    rows.append({
                        "language": lang,
                        "trial": trial,
                        "correlation_id": payload.get("correlation_id", correlation_id),
                        "audio_duration_ms": round(audio_duration_ms[lang], 2),
                        "request_wall_ms": round(wall_ms, 2),
                        "audio_read_ms": timing.get("audio_read_ms", ""),
                        "transcode_ms": timing.get("transcode_ms", ""),
                        "stt_ms": timing.get("stt_ms", ""),
                        "language_detection_ms": timing.get("language_detection_ms", ""),
                        "agent_ms": timing.get("agent_ms", ""),
                        "initial_gemini_request_ms": timing.get("initial_gemini_request_ms", ""),
                        "followup_gemini_request_ms": timing.get("followup_gemini_request_ms", ""),
                        "gemini_calls_count": timing.get("gemini_calls_count", ""),
                        "tool_ms": timing.get("tool_ms", ""),
                        "tool_router_ms": timing.get("tool_router_ms", ""),
                        "tts_ms": timing.get("tts_ms", ""),
                        "backend_total_ms": timing.get("total_turn_ms", ""),
                        "tts_available": payload.get("tts_available", False),
                        "http_status": response.status_code,
                        "error_code": "",
                    })
                    # Avoid conversation state carrying across repetitions.
                    conversation_manager.reset_session(payload.get("session_id", f"baseline-{lang}-{trial}"))
    finally:
        fastapi_app.dependency_overrides.clear()
        engine.dispose()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    completed = [row for row in rows if row.get("http_status") == 200]
    failed = [row for row in rows if row.get("http_status") != 200]
    print(f"Trials: {len(rows)} ({len(completed)} succeeded, {len(failed)} failed); raw audio and transcript omitted")
    for lang in CASES:
        vals = [float(row["request_wall_ms"]) for row in completed if row["language"] == lang]
        if not vals:
            print(f"{lang}: no successful trials")
            continue
        stages = {
            name: statistics.median(float(row[name]) for row in completed if row["language"] == lang and row[name] not in ("", None))
            for name in ("stt_ms", "agent_ms", "tool_ms", "tts_ms", "backend_total_ms")
            if any(row["language"] == lang and row[name] not in ("", None) for row in rows)
        }
        summary = {"request_wall_ms": statistics.median(vals), **stages}
        if len(vals) >= 20:
            pct_summary = {name: {f"p{pct}": round(percentile([float(row[name]) for row in completed if row["language"] == lang and row[name] not in ("", None)], pct), 2)
                                  for pct in (50, 90, 95)}
                           for name in ("request_wall_ms", "stt_ms", "agent_ms", "initial_gemini_request_ms", "tts_ms", "backend_total_ms")}
            print(f"{lang}: percentile_summary={pct_summary}")
        else:
            print(f"{lang}: medians_ms={summary}; request_range_ms=({min(vals):.1f}, {max(vals):.1f}); n={len(vals)} (p90/p95 omitted)")
    print(f"Per-trial timing CSV: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
