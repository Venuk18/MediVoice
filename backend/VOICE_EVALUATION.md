# MediVoice voice evaluation protocol

## Prisma transcript scoring

Use only consented or synthetic audio, and manually verify each reference transcript against the recording before adding it to the manifest. Keep audio as WAV and keep samples under Prisma's documented 30-second REST limit for `prisma-v3.0`.

Create a CSV manifest with these required columns:

```csv
sample_id,audio_path,reference_transcript,requested_language,consent_or_synthetic,speech_style,noise_condition
synthetic-te-01,audio/synthetic-te-01.wav,"నాకు అపాయింట్‌మెంట్ కావాలి.",te,synthetic,natural,quiet
```

Use distinct sample IDs and cover Telugu native script, Romanized Telugu, Telugu-English code-mix, short confirmations, names and spoken numbers, natural phrases, and varied speaking rates. Include equivalent English clips for latency comparisons. Do not put real patient data in the manifest.

Run from `backend` after setting `GNANI_API_KEY` in the environment:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_voice_samples.py path\to\manifest.csv --output path\to\results.csv
```

The per-sample results CSV records the reference and actual transcripts, requested/provider language, duration, STT latency, WER, and CER. The script prints aggregate WER/CER and latency percentiles without printing transcripts. Preserve the manifest, audio, and result CSV together to reproduce a run. Compare language classification separately from WER/CER.

Optional manual VAD labels can be added as columns: `reference_speech_onset_ms`, `detected_speech_onset_ms`, `reference_speech_end_ms`, `detected_speech_end_ms`, `first_word_preserved`, `false_trigger`, and `silence_submitted`. Record each sample under quiet, fan, traffic, conversation, or low-volume conditions. Label from the actual browser recording; this STT harness does not simulate browser capture or claim to remove noise.

## Voice latency diagnostics

Enable backend timing logs with `VOICE_DIAGNOSTICS_ENABLED=true`. In the browser console, run `localStorage.setItem('medivoice.voiceDiagnostics', 'true')` and reload. Browser logs use the same correlation ID for frontend request submission, request duration, response arrival, first playback, complete playback, microphone resume, and audio finalization. Backend logs record audio read, conversion, Prisma, language detection, ConversationManager, Gemini calls, tool routing, Timbre, and total request time. Logs omit transcript/audio content and patient identifiers.

Collect at least 20 independent turns per language before treating p90/p95 estimates as stable; keep utterance types and environment conditions consistent between runs. `first_audible_response_ms` on the backend measures until generated audio is ready, while the browser `speech_end_to_first_audio_ms` measures until playback begins. These are different endpoints and should be reported separately.

For a repeatable backend baseline using the same saved synthetic utterance per language and an isolated in-memory database, run:

```powershell
$env:VOICE_DIAGNOSTICS_ENABLED='true'
.\.venv\Scripts\python.exe scripts\benchmark_voice_latency.py --repeats 20 --audio-dir benchmark_runs\synthetic_audio --output benchmark_runs\latency.csv
```

This calls live Gnani STT/TTS and Gemini and can incur provider usage. It stores only the two synthetic WAV inputs and a timing CSV; it never writes transcripts. It does not exercise browser VAD, audio playback, microphone restart, or patient database records.
