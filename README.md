# MediVoice AI — Voice-First Hospital Operations Platform

**Hospital:** Aarogya One Hospital (fictional multispecialty hospital in Bengaluru)  
**Challenge:** Great Indian AI Internship Challenge  
**Status:** Phase 1 backend foundation and Phase 2 text-first AI agent implemented. The reported backend test suite passes 37/37 tests.

MediVoice AI is a hospital operations assistant designed to streamline doctor discovery, appointment scheduling, lab order tracking, and operational workflows. It currently uses a deterministic mock reasoning adapter, allowing development and testing without external AI API credits.

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
- Doctor and appointment-slot discovery.
- Appointment cancellation and completion.
- Lab order status tracking.
- Deterministic detection and management of overdue lab workflows.
- Synthetic demo data for Aarogya One Hospital.

## Phase 2: Text-First AI Agent

### Agent components

- **Conversation manager:** Maintains multi-turn conversation state and prompts for missing appointment details.
- **Reasoning adapter:** Provider-independent interface with a deterministic mock implementation.
- **Restricted tool router:** Allows only approved doctor search, slot discovery, and appointment booking tools.
- **Confirmation gate:** Requires explicit patient confirmation of the pending booking before executing the booking operation.
- **Booking verification:** Uses the existing transactional service and reports success only after the booking operation succeeds.
- **Session isolation:** Keeps conversation drafts and patient references isolated between sessions.

### Agent API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/agent/chat` | Send a message to the agent |
| GET | `/api/v1/agent/sessions/{session_id}` | Inspect conversation state |
| POST | `/api/v1/agent/sessions/{session_id}/reset` | Reset a conversation session |

The current session store is in memory. Sessions are lost on server restart and are not shared between multiple backend workers.

## Technology Stack

- Frontend: React, TypeScript, Vite
- Backend: Python, FastAPI, Pydantic
- Database: SQLAlchemy with SQLite/PostgreSQL support
- Migrations: Alembic
- Testing: Pytest

## Setup on Windows PowerShell

### 1. Install dependencies

```powershell
py -m pip install -r backend/requirements.txt
npm install
```

### 2. Configure the local database

```powershell
$env:PYTHONPATH="backend"
$env:DATABASE_URL="sqlite:///aarogya_demo.db"
```

Use synthetic demo data only. Keep secrets in local environment files and never commit credentials.

### 3. Run backend tests

```powershell
py -m pytest backend/tests/ -v
```

The latest reported test run completed with 37 passed tests and exit code 0. Re-run the suite to verify the current checkout.

### 4. Run frontend checks

```powershell
npm run lint
npm run build
```

### 5. Start the backend

```powershell
$env:PYTHONPATH="backend"
$env:DATABASE_URL="sqlite:///aarogya_demo.db"
py -m uvicorn app.main:app --app-dir backend --port 8000 --reload
```

### 6. Start the frontend

Open another terminal at the project root:

```powershell
npm run dev
```

Use the local URL printed by Vite. FastAPI's interactive API documentation is available at `http://localhost:8000/docs`.

## Current Limitations and Future Work

- The reasoning adapter is deterministic and does not yet provide genuine LLM reasoning.
- Live Gnani AI/Evon integration and speech-to-text/text-to-speech are planned future enhancements.
- The in-memory conversation store is suitable for an initial demo, not a multi-worker production deployment.
- The project uses synthetic data and is not a production clinical decision-support system.

## Project Safety

MediVoice AI is an educational prototype. It must not be used as a substitute for clinical judgment or as a production system for real patient data.
