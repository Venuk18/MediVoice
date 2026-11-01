"""Reproducible Prisma STT and manually labeled browser VAD evaluation.

Manifest CSV columns: sample_id,audio_path,reference_transcript,requested_language,
consent_or_synthetic,speech_style,noise_condition. Optional VAD columns:
reference_speech_onset_ms,detected_speech_onset_ms,reference_speech_end_ms,
detected_speech_end_ms,first_word_preserved,false_trigger,silence_submitted.

Only use consented recordings or synthetic speech. Transcript values are written to
the requested result CSV for scoring; they are never printed to stdout or logs.
Audio must be WAV so duration is measured without another decoder dependency.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import statistics
import sys
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.speech.stt_service import GnaniPrismaSTT


REQUIRED_COLUMNS = {
    "sample_id", "audio_path", "reference_transcript", "requested_language",
    "consent_or_synthetic", "speech_style", "noise_condition",
}


def normalize(text: str) -> list[str]:
    return " ".join(text.casefold().split()).split()


def edit_distance(left: Iterable[str], right: Iterable[str]) -> int:
    a, b = list(left), list(right)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    words = normalize(reference)
    return edit_distance(words, normalize(hypothesis)) / max(1, len(words))


def character_error_rate(reference: str, hypothesis: str) -> float:
    ref = list("".join(normalize(reference)))
    hyp = list("".join(normalize(hypothesis)))
    return edit_distance(ref, hyp) / max(1, len(ref))


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct / 100
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def wav_duration(path: Path) -> float:
    data = path.read_bytes()
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    offset = 12
    byte_rate = data_bytes = 0
    while offset + 8 <= len(data):
        chunk_id = data[offset:offset + 4]
        chunk_size = int.from_bytes(data[offset + 4:offset + 8], "little")
        chunk_start = offset + 8
        if chunk_id == b"fmt " and chunk_size >= 16:
            byte_rate = int.from_bytes(data[chunk_start + 8:chunk_start + 12], "little")
        elif chunk_id == b"data":
            data_bytes = min(chunk_size, max(0, len(data) - chunk_start))
            break
        offset = chunk_start + chunk_size + (chunk_size % 2)
    if not byte_rate or not data_bytes:
        raise ValueError("missing usable WAV format/data chunk")
    return data_bytes / byte_rate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="CSV manifest with reference transcripts")
    parser.add_argument("--output", type=Path, required=True, help="Per-sample result CSV")
    args = parser.parse_args()

    with args.manifest.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            parser.error(f"Manifest missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)

    if not rows:
        parser.error("Manifest contains no samples")
    if any(row["consent_or_synthetic"].strip().casefold() not in {"consented", "synthetic"} for row in rows):
        parser.error("Every row must be marked 'consented' or 'synthetic'")

    stt = GnaniPrismaSTT()
    if not stt.is_live_configured:
        parser.error("Gnani is not configured; set GNANI_API_KEY without placing it in the manifest")

    output_rows: list[dict[str, str]] = []
    latencies: list[float] = []
    word_errors = char_errors = reference_words = reference_chars = 0
    vad_groups: dict[str, dict[str, object]] = {}

    for row in rows:
        audio_path = (args.manifest.parent / row["audio_path"]).resolve()
        if not audio_path.is_file():
            parser.error(f"Audio file not found for sample {row['sample_id']}")
        try:
            duration = wav_duration(audio_path)
        except (OSError, ValueError) as exc:
            parser.error(f"Sample {row['sample_id']} must be a readable WAV file: {exc}")
        result = stt.transcribe(audio_path.read_bytes(), language=row["requested_language"], content_type="audio/wav")
        reference = row["reference_transcript"].strip()
        transcript = result["transcript"].strip()
        ref_words = normalize(reference)
        ref_chars = list("".join(ref_words))
        w_edits = edit_distance(ref_words, normalize(transcript))
        c_edits = edit_distance(ref_chars, list("".join(normalize(transcript))))
        latency = float(result.get("stt_ms", 0.0))
        latencies.append(latency)
        word_errors += w_edits
        char_errors += c_edits
        reference_words += len(ref_words)
        reference_chars += len(ref_chars)
        output = {
            "sample_id": row["sample_id"],
            "reference_transcript": reference,
            "actual_transcript": transcript,
            "requested_language": row["requested_language"],
            "provider_detected_language": result.get("language_code", ""),
            "audio_duration_seconds": f"{duration:.3f}",
            "stt_latency_ms": f"{latency:.2f}",
            "word_error_rate": f"{w_edits / max(1, len(ref_words)):.6f}",
            "character_error_rate": f"{c_edits / max(1, len(ref_chars)):.6f}",
            "speech_style": row["speech_style"],
            "noise_condition": row["noise_condition"],
        }
        for name in ("reference_speech_onset_ms", "detected_speech_onset_ms", "reference_speech_end_ms", "detected_speech_end_ms", "first_word_preserved", "false_trigger", "silence_submitted"):
            output[name] = row.get(name, "")
        output_rows.append(output)

        if row.get("first_word_preserved", "").strip():
            condition = row["noise_condition"]
            group = vad_groups.setdefault(condition, {"samples": 0, "first_word_preserved": 0, "false_triggers": 0,
                                                       "premature_truncations": 0, "silence_submissions": 0,
                                                       "onset_error_ms": [], "end_error_ms": []})
            group["samples"] += 1
            group["first_word_preserved"] += row["first_word_preserved"].strip().lower() in {"true", "1", "yes"}
            group["false_triggers"] += row.get("false_trigger", "").strip().lower() in {"true", "1", "yes"}
            group["silence_submissions"] += row.get("silence_submitted", "").strip().lower() in {"true", "1", "yes"}
            if row.get("reference_speech_onset_ms") and row.get("detected_speech_onset_ms"):
                group["onset_error_ms"].append(float(row["detected_speech_onset_ms"]) - float(row["reference_speech_onset_ms"]))
            if row.get("reference_speech_end_ms") and row.get("detected_speech_end_ms"):
                end_error = float(row["detected_speech_end_ms"]) - float(row["reference_speech_end_ms"])
                group["end_error_ms"].append(end_error)
                group["premature_truncations"] += end_error < 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Samples: {len(output_rows)}")
    print(f"Aggregate WER: {word_errors / max(1, reference_words):.4f}")
    print(f"Aggregate CER: {char_errors / max(1, reference_chars):.4f}")
    print("STT latency ms: " + ", ".join(f"p{p}={percentile(latencies, p):.2f}" for p in (50, 90, 95)))
    for condition, group in vad_groups.items():
        onset = group["onset_error_ms"]
        end = group["end_error_ms"]
        print(f"Manual VAD {condition}: samples={group['samples']}, first_word_preserved={group['first_word_preserved']}, "
              f"false_triggers={group['false_triggers']}, premature_truncations={group['premature_truncations']}, "
              f"silence_submissions={group['silence_submissions']}, "
              f"median_onset_error_ms={statistics.median(onset) if onset else 'n/a'}, "
              f"median_end_error_ms={statistics.median(end) if end else 'n/a'}")
    print(f"Per-sample transcript results saved to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
