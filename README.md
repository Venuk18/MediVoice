# MediVoice AI — Voice-First Hospital Operations Platform

**Hospital:** Aarogya One Hospital (fictional multispecialty hospital in Bengaluru)  
**Challenge:** Great Indian AI Internship Challenge  
**Status:** Phase 1 backend foundation, Phase 2 text-first AI agent, and Real Gemini API Multilingual Integration (`te`, `ta`, `kn`, `hi`, `en`) implemented and verified. The backend test suite passes **54/54 tests**.

MediVoice AI is a hospital operations assistant designed to streamline doctor discovery, appointment scheduling, lab order tracking, and operational workflows. It supports both live Gemini API reasoning (`GeminiReasoningAdapter`) and deterministic offline reasoning (`MockReasoningAdapter`) for automated tests without consuming external API credits.

## Phase 1: Backend Foundation

### Architecture

- **FastAPI:** REST API and OpenAPI documentation.
- **SQLAlchemy 2.x:** Database models supporting PostgreSQL and SQLite.
- **Pydantic v2:** Request validation and structured responses.
- **Alembic:** Database migrations.
- **Pytest:** Automated backend tests.

### Key capabilities

- Eight database models covering hospitals, departments, doctors, appointment slots, appointments, lab orders, workflow exceptions, and audit events.
- Transactional appointment booking and database constraints to prevent double booking.
- Doctor and appointment-slot discovery with multilingual alias resolution.
- Appointment cancellation and completion.
- Lab order status tracking.
- Deterministic detection and management of overdue lab workflows.
- Synthetic demo data for Aarogya One Hospital.

## Phase 2+: Multilingual Gemini Agent (`te`, `ta`, `kn`, `hi`, `en`)

### Agent components

- **Conversation manager:** Maintains multi-turn conversation state, active patient language (`en`, `te`, `ta`, `kn`, `hi`), and prompts for missing appointment details.
- **Reasoning adapters:**
  - `GeminiReasoningAdapter`: Official Gemini API (`generateContent` with `functionDeclarations`) using `gemini-3.6-flash` (with automatic fallback to `gemini-3.8-flash` / `gemma-4-26b-a4b-it`), bounded request timeouts, bounded `max_tool_rounds`, and backend-only `GEMINI_API_KEY`.
  - `MockReasoningAdapter`: Deterministic offline reasoning adapter supporting all five languages for zero-credit automated tests.
- **Restricted tool router:** Allows only approved `search_doctors`, `get_available_slots`, and `book_appointment` tools. Blocks direct SQL or unapproved tools.
- **Confirmation gate:** Requires explicit patient confirmation (`YES`, `అవును`, `ஆம்`, `ಹೌದು`, `हाँ`) of the pending booking draft before executing `book_appointment`. Any change to doctor, slot, reason, or patient reference invalidates prior confirmation via SHA-256 draft fingerprinting.
- **Booking verification:** Uses the transactional service and reports success only after the database commit succeeds.
- **Session isolation:** Keeps conversation drafts and patient references isolated between sessions.

### Agent API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/agent/chat` | Send a message to the agent (English, Telugu, Tamil, Kannada, Hindi) |
| GET | `/api/v1/agent/sessions/{session_id}` | Inspect conversation state |
| POST | `/api/v1/agent/sessions/{session_id}/reset` | Reset a conversation session |
| GET | `/api/v1/agent/config` | Inspect active reasoning provider, model, and supported languages (never exposes API key) |

## Setup & Configuration

### 1. Install dependencies

```powershell
py -m pip install -r backend/requirements.txt
npm install
```

### 2. Configure `.env`

Copy `.env.example` to `.env` and set your backend environment variables:

```ini
DATABASE_URL=sqlite:///./aarogya_demo.db
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash
GEMINI_TIMEOUT_SECONDS=15.0
GEMINI_MAX_TOOL_ROUNDS=4
```

### 3. Run backend tests (uses `MockReasoningAdapter`, consumes zero API credits)

```powershell
$env:PYTHONPATH="backend"; py -m pytest backend/tests/ -v
```

### 4. Run frontend checks

```powershell
npm run lint
npm run build
```

### 5. Seed synthetic data and start the backend

```powershell
$env:PYTHONPATH="backend"
$env:DATABASE_URL="sqlite:///./aarogya_demo.db"
$env:LLM_PROVIDER="gemini"
$env:GEMINI_API_KEY="your_gemini_api_key_here"
$env:GEMINI_MODEL="gemini-3.6-flash"
py backend/scripts/seed_data.py
py -m uvicorn app.main:app --app-dir backend --port 8000 --reload
```

### 6. Start the frontend

Open another terminal at the project root:

```powershell
npm run dev
```

## Project Safety

MediVoice AI is an educational prototype using strictly synthetic data. It must not be used as a substitute for clinical judgment or with real patient data.

