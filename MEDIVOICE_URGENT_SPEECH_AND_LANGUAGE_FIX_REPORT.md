# MediVoice AI — Urgent English/Telugu Speech Recognition & Language Detection Fix Report

**Date:** November 9, 2026  
**Status:** Completed & Verified  
**Primary Languages:** English (`en`), Telugu (`te`), and English-Telugu Code-Mixing  
**Test Results:** 395/395 Backend Tests Passing (100%) | 70/70 Frontend Tests Passing (100%) | 0 TypeScript Errors | Vite Production Build Succeeded (1.15s)

---

## 1. Executive Summary

During live voice interactions with MediVoice AI, users speaking English or Telugu experienced unexpected language drift and incorrect transcriptions:
- A Telugu confirmation was transcribed by Gnani STT in Gujarati script: `હા, સારી સારી જરૂર છે।`
- A Telugu utterance was transcribed in Malayalam script: `ആ, അപ്പോൾ അതിൻ്റെ పేര്?`
- Unclear/noisy audio was transcribed in Bengali script: `আর তুলতে পেরেছি সবাই।`
- The downstream language resolver switched the entire session to **Hindi** after the Gujarati transcription.
- A subsequent Telugu utterance was misclassified as **English** after the Malayalam transcription.

This investigation traced the issue through the entire speech-to-text, language resolution, voice orchestration, and conversational safety pipeline. The root causes were identified, isolated, and resolved with zero credit consumption on live external APIs and zero regressions across the 395 backend tests and 70 frontend tests.

---

## 2. Confirmed Root Causes

The system failures resulted from four compounding defects across the STT layer, resolver heuristics, Unicode handling, and conversation safety gates:

### Root Cause 1: Gnani STT `indic-auto` Multilingual Acoustic Hallucination
- **Mechanism:** In `backend/app/services/speech/stt_service.py`, `normalize_stt_language("auto")` maps `"auto"` to `"indic-auto"`.
- When `indic-auto` is sent to the Gnani Prisma STT v3 API, the acoustic model performs unconstrained recognition across all 12+ Indic languages (including Gujarati, Malayalam, Bengali, Punjabi, Marathi, Odia).
- For Telugu-English code-mixed speech, quiet audio, or background acoustic reflections, the unconstrained acoustic model occasionally hallucinates phoneme sequences matching foreign Indic languages, returning transcripts in Gujarati (`0x0A80-0x0AFF`), Malayalam (`0x0D00-0x0D7F`), or Bengali (`0x0980-0x09FF`).

### Root Cause 2: Devanagari Danda (`।`) False Hindi Identification
- **Mechanism:** In `backend/app/agent/language_resolver.py`, `detect_script_language` inspected the Unicode block `0x0900 <= cp <= 0x097F` for Hindi (`hi`).
- This block includes the Devanagari danda `।` (`U+0964`) and double danda `॥` (`U+0965`), which are standard full stops across Sanskrit, Hindi, Gujarati, Marathi, and Bengali.
- For the Gujarati transcription `હા, સારી સારી જરૂર છે।`, all Gujarati characters were skipped, but the terminating danda `।` matched `0x0900 <= cp <= 0x097F`, causing `counts["hi"] = 1`.
- Because `counts["hi"]` was the highest (and only) matching Indic counter, `detect_script_language` classified the transcript as Hindi (`"hi"`), permanently flipping the session language to Hindi!

### Root Cause 3: Foreign Language Fallback Silently Defaulting to English
- **Mechanism:** In `backend/app/services/speech/stt_service.py`, `map_to_internal_language(gnani_lang)` mapped incoming language codes using `INTERNAL_LANG_MAP.get(clean, "en")`.
- When Gnani reported `detected_language_code: "ml-IN"` or `"ml"` (Malayalam), `INTERNAL_LANG_MAP` had no entry for Malayalam, causing the function to silently return `"en"`.
- When passed to `resolve_adaptive_language`, step 7 saw `stt_detected_language = "en"`. Since `"en"` was in `SUPPORTED_LANGUAGES`, it flipped the active Telugu session to English, explaining why Telugu speech transcribed as Malayalam was classified as English.

### Root Cause 4: Lack of Foreign Script Filtering & Session Latching
- The language resolver had no mechanism to detect unsupported Indian scripts (Gujarati, Malayalam, Bengali, Gurmukhi, Odia).
- A single noisy or hallucinated turn was allowed to override the established conversation language.
- Furthermore, during critical operations (e.g. `AWAITING_CONFIRMATION`), foreign-script hallucinations were not explicitly flagged, presenting a reliability risk where an unverified transcript could be interpreted as a positive affirmation.

---

## 3. Files Modified

| File | Nature of Change |
| :--- | :--- |
| `backend/app/agent/language_resolver.py` | Added foreign script detector (`detect_unsupported_foreign_script`), fixed Devanagari danda exclusion in `detect_script_language`, implemented `resolve_adaptive_language_with_details` with structured telemetry, added short affirmation safeguards, and enforced session language retention on foreign/ambiguous input. |
| `backend/app/services/speech/stt_service.py` | Updated `map_to_internal_language` to return `None` (not `"en"`) for unmapped foreign languages; set `detected_language` to `"uncertain"` instead of defaulting to `"en"`. |
| `backend/app/agent/adapters.py` | Enhanced `is_affirmative` and `is_contextual_affirmative` with `detect_unsupported_foreign_script` check to strictly reject foreign script transcripts from triggering appointment bookings. |
| `backend/app/agent/conversation_manager.py` | Added foreign script safeguard at turn start: prompts user for clear repetition during appointment confirmation, patient registration, and general inquiries; guarantees no appointment is booked on noisy STT output. |
| `backend/app/services/speech/voice_orchestrator.py` | Integrated `resolve_adaptive_language_with_details`, wired up Phase 6 privacy-safe diagnostics logging (correlation ID, requested STT lang, provider lang, resolver decision, script class, duration, zero raw audio or patient identifiers). |
| `backend/tests/test_speech_recognition_and_language_fix.py` | New comprehensive regression test suite containing 15 deterministic tests covering all 14 required cases and structured observability telemetry. |
| `backend/tests/test_voice_tts_consistency_and_identity.py` | Updated hardcoded slot test fixture start date from fixed past date (`2026-11-08`) to dynamic future date (`datetime.now() + timedelta(days=2)`). |

---

## 4. Exact STT Behavior Before and After

| Aspect | Before | After |
| :--- | :--- | :--- |
| **Foreign Language Code Mapping** | `map_to_internal_language("ml-IN")` returned `"en"` | Returns `None`; STT `detected_language` becomes `"uncertain"` |
| **Gujarati Transcript** (`હા, સારી સારી જરૂર છે।`) | Danda `।` counted as Hindi (`0x0900 <= cp <= 0x097F`). Switched session to `hi`. | Excluded danda from Hindi count; detected `gujarati` script via `detect_unsupported_foreign_script`; retains active session language (`en` or `te`). |
| **Malayalam Transcript** (`ആ, అപ്പോൾ അതിൻ്റെ పేര്?`) | Script check missed Malayalam; STT reported `ml-IN` which defaulted to `en`; session flipped to `en`. | Detected `malayalam` script; STT code mapped to `uncertain`; protects active session (`te` remains `te`). |
| **Bengali Transcript** (`আর তুলতে পেরেছি সবাই।`) | Danda `।` counted as Hindi; session switched to `hi`. | Detected `bengali` script; danda excluded; retains active session language. |
| **Short Affirmation ("ok", "yes")** | Could trigger English conversational detection and flip Telugu session to English. | Entity / short affirmation safeguard catches single-word acknowledgments; retains session language (`te` stays `te`). |
| **Confirmation Safety Gate** | Potential for foreign script or ambiguous affirmative to trigger booking. | `is_affirmative` strictly returns `False` on foreign scripts; triggers repetition prompt; NEVER books an appointment. |

---

## 5. Language Resolver Changes

### 1. Unsupported Foreign Script Detection
```python
def detect_unsupported_foreign_script(text: str) -> Optional[str]:
    """
    Detects if text contains characters from unsupported Indian scripts:
    - Gujarati: 0x0A80 - 0x0AFF
    - Malayalam: 0x0D00 - 0x0D7F
    - Bengali/Assamese: 0x0980 - 0x09FF
    - Gurmukhi: 0x0A00 - 0x0A7F
    - Odia: 0x0B00 - 0x0B7F
    Returns script name if >= 2 characters are found, else None.
    """
```

### 2. Devanagari Danda Exclusion in `detect_script_language`
```python
elif (0x0904 <= cp <= 0x0939) or (0x0958 <= cp <= 0x0961) or (0x093E <= cp <= 0x094F):
    # True Devanagari alphabet letters and matras only (excluding danda \u0964, \u0965 and digits)
    counts["hi"] += 1
```
Hindi classification now requires at least 3 genuine Devanagari alphabetical letters, preventing single punctuation marks or stray characters from overriding conversation language.

### 3. Resolution Priority Order
1. **Explicit Language Switch Commands:** Phrases like "speak in english", "తెలుగులో మాట్లాడండి", "switch to auto" immediately set the target language.
2. **Manual Mode Preference:** Pinned language is honored if user manually chose a language.
3. **Unsupported Foreign Script Safeguard:** If foreign script (Gujarati, Malayalam, Bengali) is present, **retain `current_session_language`**.
4. **Native Indian Script Detection:** Genuine Telugu (`te`), Tamil (`ta`), Kannada (`kn`), or Hindi (`hi`) script resolves to that language.
5. **Entity / Affirmation Safeguard:** Doctor names, specialties, dates, times, patient info, and short tokens ("ok", "yes") retain active session language.
6. **Romanized Indic Detection:** Tenglish / Hinglish conversational markers (e.g., `naaku`, `kavali`, `garitho`, `repu`, `entha`) resolve to the respective Indic language.
7. **English Conversational Detection:** English grammatical cues (require >= 1 cues and >= 2 words) resolve to `en`.
8. **Reliable STT Fallback:** Supported languages only; protects Telugu against false `"en"` when no English words exist.
9. **Safe Fallback:** Preserves current session language.

---

## 6. Regression Test Results (Phase 5)

All 15 deterministic tests in `backend/tests/test_speech_recognition_and_language_fix.py` passed:

```
backend/tests/test_speech_recognition_and_language_fix.py::test_1_english_only_speech_remains_english PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_2_telugu_only_speech_remains_telugu PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_3_english_telugu_code_mixing PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_4_gujarati_script_does_not_switch_to_gujarati_or_hindi PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_5_malayalam_script_does_not_switch_to_malayalam_or_english PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_6_bengali_script_does_not_switch_to_bengali_or_hindi PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_7_short_ambiguous_affirmations_retain_session_language PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_8_english_doctor_names_in_telugu_sentences PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_9_telugu_sentences_with_english_medical_terms PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_10_genuine_english_to_telugu_switch PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_11_genuine_telugu_to_english_switch PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_12_single_noisy_turn_does_not_corrupt_session_language PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_13_ambiguous_appointment_confirmation_triggers_clarification PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_14_empty_or_unusable_stt_results_handled_safely PASSED
backend/tests/test_speech_recognition_and_language_fix.py::test_15_observability_diagnostics_structure PASSED
```

---

## 7. Full Suite Test Verification

### Backend Verification
- **Command:** `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -q`
- **Result:** **395 passed, 1 warning in 20.78s**
- **Regressions:** 0

### Frontend Verification
- **Command:** `npm --prefix frontend run test`
- **Result:** **70 passed, 0 failed in 512ms**
- **Command:** `npm --prefix frontend run lint` (`tsc --noEmit`)
- **Result:** **Exit code 0 (Zero TypeScript errors)**
- **Command:** `npm --prefix frontend run build` (`vite build`)
- **Result:** **Built in 1.15s (dist created cleanly)**

---

## 8. Observability & Telemetry (Phase 6)

Structured logging was added to `backend/app/services/speech/voice_orchestrator.py`:
- **Logged Attributes:**
  - `correlation_id` (UUID per turn)
  - `session_id` (session tracker)
  - `requested_stt_lang` (`auto`, `te`, `en`, etc.)
  - `provider_reported_lang` (Gnani reported language code)
  - `resolver_selected_lang` (final resolved language)
  - `script_classification` (`te`, `hi`, `gujarati`, `malayalam`, `bengali`, `latin`)
  - `previous_session_lang` (session language before turn)
  - `resolver_decision` (e.g. `unsupported_foreign_script_retained`, `script_detected`, `entity_safeguard_retained`)
  - `confidence` (provider confidence score)
  - `stt_ms` (STT processing duration)
  - `total_ms` (end-to-end voice turn duration)
- **Privacy Guarantees:**
  - NO raw audio bytes logged.
  - NO patient names or phone numbers logged.
  - NO raw patient transcripts logged in production logging lines.

---

## 9. Limitations & Real Gnani Provider Considerations

1. **Acoustic Hallucination vs. Pipeline Rejection:**
   - The application-level safeguards implemented here guarantee that when Gnani outputs Gujarati, Malayalam, or Bengali transcripts, the application will **never switch language** and will **never book an appointment or store invalid patient data**.
   - However, because Gnani's `indic-auto` endpoint performs acoustic recognition across 12+ Indic languages on the server side, noisy audio or microphone clipping can still cause Gnani's server to generate a Gujarati or Malayalam transcription string.
   - When this happens, our system now gracefully asks the patient to repeat their request in Telugu or English, maintaining complete conversation integrity.
2. **Explicit Language Hints in Live Deployment:**
   - If a patient explicitly selects "Telugu" or "English" from the frontend language toggle, `language="te"` or `"en"` is passed to the backend, which forwards `te-IN` or `en-IN` directly to Gnani STT. This completely bypasses `indic-auto` and eliminates foreign-script hallucinations at the provider level.
   - In automatic mode, our newly added script rejection and session retention safeguards ensure that temporary acoustic noise does not derail the conversation.

