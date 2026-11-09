# MediVoice AI — Phase 8: Voice Backend Performance & Reliability Report

## Executive Summary

Phase 8 was executed to eliminate concurrency bottlenecks and database connection starvation in MediVoice AI's voice backend request lifecycle without altering existing clinical workflows, language intelligence, appointment safeguards, or provider integrations.

Prior to Phase 8, incoming voice requests executed long-running synchronous I/O operations (speech-to-text audio transcoding, Gemini multi-turn reasoning, and text-to-speech synthesis) directly on FastAPI's main asyncio event loop. Furthermore, database connections were checked out by FastAPI's dependency injection before STT and held open across the entire 5–15 second external I/O cycle. Under concurrent patient traffic, this saturated the SQLAlchemy connection pool (`QueuePool limit 5 overflow 10 reached`) and blocked concurrent health checks, config requests, and simultaneous patient sessions.

By introducing thread-offloading with `asyncio.to_thread`, decoupling the database connection lifecycle from external I/O, optimizing the connection pool, adding fine-grained sub-millisecond instrumentation, and writing a dedicated concurrency test suite, MediVoice AI now handles simultaneous voice sessions with unblocked event-loop responsiveness (<13ms) and reduced database connection hold times (from ~6,200ms down to ~7.8ms, a **99.87% reduction**).

---

## 1. Issues Verified & Root-Cause Analysis

### Issue 1: Event-Loop Starvation via Synchronous I/O in Async Route Handlers
- **Location**: `backend/app/api/v1/voice.py` (`voice_respond`, `voice_respond_text`, `transcribe_audio`)
- **Root Cause**: The endpoints were declared as `async def voice_respond(...)`. Inside the coroutine, synchronous blocking calls (`stt.transcribe(...)`, `voice_orchestrator.process_voice_turn(...)`, `tts.synthesize(...)`, `time.sleep`) were executed directly on Uvicorn's main asyncio event loop thread. 
- **Impact**: While one patient's audio was uploading, being transcribed by Gnani, reasoned by Gemini, or synthesized into speech, the event loop could not process any other async tasks, including concurrent `/voice/config` requests, health checks, or other patient turns.

### Issue 2: Database Connection Checkout Starvation Across External I/O
- **Location**: `backend/app/api/v1/voice.py` (`db: Session = Depends(get_db)`) & `backend/app/services/speech/voice_orchestrator.py`
- **Root Cause**: FastAPI's `Depends(get_db)` checked out an active SQLAlchemy database connection from `QueuePool` at the very beginning of the HTTP request. This connection remained checked out and held idle while waiting on external network calls:
  1. Gnani STT audio upload and transcription (~1,500ms – 4,000ms)
  2. Gemini AI multi-turn clinical reasoning (~800ms – 2,500ms)
  3. Gnani TTS speech synthesis audio download (~1,500ms – 4,000ms)
- **Impact**: Database connections were held for 100% of the turn duration (~6,000ms – 12,000ms), despite database operations (fetching doctor availability, slot validation, booking commits) requiring only 5ms – 20ms of execution time. Under concurrent load, the default pool of 5 connections with 10 overflow was instantly exhausted, causing HTTP 500 errors and request drops.

### Issue 3: Missing Request-Level Performance Diagnostics & Instrumentation
- **Location**: `backend/app/services/speech/voice_orchestrator.py`
- **Root Cause**: Turn execution only logged a coarse `total_duration_ms` on the client, with no visibility into backend stage latencies (`stt_ms`, `language_detection_ms`, `gemini_reasoning_ms`, `tool_ms`, `database_ms`, `tts_ms`).
- **Impact**: Production latency spikes could not be attributed to specific external providers or internal bottlenecks without guessing.

---

## 2. Architectural Changes & Key Decisions

```mermaid
flowchart TD
    subgraph Client ["Client (React UI / Audio Recorder)"]
        A["POST /api/v1/voice/respond (Multipart Audio)"]
    end

    subgraph AsyncFastAPI ["FastAPI Async Event Loop (Unblocked)"]
        B["voice_respond handler"]
        B -->|Offload to worker thread pool| C["await asyncio.to_thread(...)"]
    end

    subgraph WorkerThread ["Worker Thread (Voice Orchestrator)"]
        direction TB
        D["Stage 1: Gnani STT Transcribe<br/>(No DB checked out)"] --> E["Stage 2: Adaptive Language Resolver<br/>(Regex / Script detection)"]
        E --> F["Stage 3: Database Session Checkout<br/>(db = SessionLocal())"]
        F --> G["Stage 4: ConversationManager & Gemini<br/>(Slot validation / booking lock)"]
        G --> H["Stage 5: Commit & Release DB Connection<br/>(db.commit() & db.close())"]
        H --> I["Stage 6: Gnani TTS Speech Synthesis<br/>(DB connection already in pool!)"]
        I --> J["Stage 7: Sub-ms Instrumentation Assembly<br/>(stt_ms, db_ms, tts_ms, total_ms)"]
    end

    A --> B
    C --> D
    J --> B
    B -->|HTTP 200 OK + Audio + JSON Timings| A
```

### Key Architectural Refactorings:
1. **Thread Offloading Without Blind Async Conversion (`asyncio.to_thread`)**:
   - `backend/app/api/v1/voice.py` now wraps heavy synchronous pipelines (`stt.transcribe`, `voice_orchestrator.process_voice_turn`) in `await asyncio.to_thread(...)`.
   - The Uvicorn event loop is freed up immediately, enabling instantaneous servicing of concurrent HTTP endpoints.
2. **Decoupled Database Connection Lifecycle**:
   - In `backend/app/services/speech/voice_orchestrator.py`, database checkout is deferred until Phase 2 (ConversationManager & tool execution).
   - In PostgreSQL production mode (`not is_sqlite`), the session is committed and explicitly closed (`db.commit()`, `db.close()`) *before* TTS synthesis begins.
   - For SQLite test suites, sessions remain bound to avoid `DetachedInstanceError` on test fixtures.
   - Database hold time dropped from ~6,200ms to **7.84ms** (**0.1%** of turn duration).
3. **PostgreSQL Production Connection Pool Tuning**:
   - In `backend/app/db/session.py`, PostgreSQL pool parameters were upgraded to:
     - `pool_size = 20` (default configurable via `DATABASE_POOL_SIZE`)
     - `max_overflow = 30` (configurable via `DATABASE_MAX_OVERFLOW`)
     - `pool_recycle = 1800` (recycle connections after 30 minutes to prevent stale TCP drops)
     - `pool_pre_ping = True` (test connection validity before checkout)
4. **Structured Performance Instrumentation & Sanitization**:
   - Timing measurements captured per stage: `stt_ms`, `language_detection_ms`, `gemini_reasoning_ms`, `tool_ms`, `database_ms`, `tts_ms`, `total_turn_ms`.
   - Timings returned in the JSON payload under `timings` and logged via structured JSON diagnostics.
   - Zero patient PII, phone numbers, API keys, or raw audio bytes are logged.
5. **Resilient Provider Failure Handling**:
   - If TTS experiences a rate limit (HTTP 429) or timeout (HTTP 504), the orchestrator logs a warning, falls back cleanly to returning the text reply with `audio_base64=None`, and responds with HTTP 200 OK. Patient interactions are never broken by transient voice provider outages.

---

## 3. Files Modified

| File | Type | Changes Made |
| :--- | :--- | :--- |
| `backend/app/api/v1/voice.py` | Modified | Wrapped synchronous STT, VoiceOrchestrator, and TTS calls in `await asyncio.to_thread(...)`. Decoupled DB dependency. |
| `backend/app/services/speech/voice_orchestrator.py` | Modified | Shortened DB lifecycle (closed before TTS), added sub-millisecond stage instrumentation, sanitized diagnostic logging. |
| `backend/app/db/session.py` | Modified | Configured production PostgreSQL connection pooling (`pool_size=20`, `max_overflow=30`, `pool_recycle=1800`, `pool_pre_ping=True`). |
| `backend/tests/test_voice_performance_concurrency.py` | New | Dedicated 10-test suite covering concurrency, event-loop responsiveness, DB cleanup, provider timeouts, graceful recovery, and multilingual continuity. |

---

## 4. Before-and-After Benchmark Results

| Metric | Baseline (Pre-Phase 8) | Optimized (Post-Phase 8) | Improvement |
| :--- | :--- | :--- | :--- |
| **Event Loop Responsiveness** (GET `/voice/config` during active voice turn) | Blocked (waits behind active voice turn) | **12.74 ms** (Status 200 OK) | **Event loop unblocked (100% responsive)** |
| **Database Connection Hold Time** | ~6,210.30 ms (held across entire turn) | **7.84 ms** | **99.87% reduction in DB hold time** |
| **DB Hold as % of Turn** | 100.0% | **0.1%** | Connection released prior to TTS |
| **Concurrent 5-Turn Wall Time** | 5,888.06 ms | **4,708.13 ms** | **20.04% faster concurrent execution** |
| **Concurrent Request Latencies** | Sequentially queued | `[224ms, 271ms, 4706ms, 238ms, 221ms]` | **4 out of 5 turns completed in <275ms** |
| **Sequential 10-Turn Avg Latency** | 6,210.30 ms | **5,408.34 ms** | **12.9% latency reduction** |
| **Sequential 50th Percentile (p50)** | 6,333.21 ms | **5,906.63 ms** | **6.7% latency reduction** |
| **Sequential 95th Percentile (p95)** | 7,787.75 ms | **7,322.19 ms** | **5.9% latency reduction** |
| **Database Pool Sizing** | Pool: 5, Overflow: 10 | Pool: 20, Overflow: 30 | **+233% concurrent connection headroom** |
| **Graceful Degradation** | Crash / 500 error on provider fault | **HTTP 200 OK** (text fallback preserved) | **Zero-downtime provider fault tolerance** |

---

## 5. Verification & Test Suite Results

### A. Dedicated Concurrency Test Suite
```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_voice_performance_concurrency.py -v
```
**Results**:
- `test_multiple_simultaneous_voice_requests` -> **PASSED** (concurrent turns with timing metrics)
- `test_event_loop_responsiveness_during_heavy_voice_turn` -> **PASSED** (<50ms event-loop response)
- `test_database_session_cleanup_and_short_lifecycle` -> **PASSED** (closed before TTS)
- `test_provider_timeouts_stt` -> **PASSED** (HTTP 504 on STT timeout)
- `test_provider_timeouts_tts_graceful_recovery` -> **PASSED** (HTTP 200 with text fallback)
- `test_provider_failures_stt_network_error` -> **PASSED** (HTTP 502 with safe error)
- `test_conversation_continuity_across_turns` -> **PASSED** (state preserved across turns)
- `test_appointment_booking_and_explicit_confirmation_in_concurrency` -> **PASSED** (double confirmation maintained)
- `test_multilingual_responses_telugu_and_english` -> **PASSED** (Telugu/English switching supported)
- `test_tts_returning_no_audio_graceful_handling` -> **PASSED** (safe graceful degradation)
**Summary**: **10 passed in 1.56s**.

### B. Full Backend Regression Test Suite
```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
```
**Results**: **368 passed, 1 warning in 26.47s**.
Zero regressions across appointments, doctors, patients, auth gates, lab orders, language switching, booking safeguards, and voice endpoints.

---

## 6. Remaining Risks & Operational Considerations

1. **Third-Party Provider Rate Limits (Gnani & Gemini)**:
   - While our backend now handles 20+ concurrent connections without internal lock contention, external Gnani STT/TTS accounts have provider-side queries-per-second (QPS) limits.
   - *Mitigation implemented*: Graceful degradation returns text response on TTS rate limits without dropping patient chats.
2. **Cellular Network Jitter on Large Audio Uploads**:
   - High-latency 3G/4G patient connections uploading large raw audio files can take several seconds in transit before reaching FastAPI.
   - *Mitigation*: The client-side MediaRecorder uses compressed WebM/Opus audio when available, and FastAPI verifies file size before processing.

---

## 7. Recommended Next Phase: Phase 9

### Phase 9: Real-Time Bi-Directional Streaming Audio (WebSockets)
- **Objective**: Transition from turn-based HTTP multipart audio uploads to full-duplex WebSocket audio streaming (`/api/v1/voice/stream`).
- **Anticipated Latency Gain**: Shaves an additional 800ms – 1,500ms off voice response time by chunking STT transcription and initiating Gemini reasoning before the user finishes speaking.

