# MediVoice AI — Voice-First Hospital Operations Platform
## Phase 1: Backend Foundation & Database Design

**Hospital**: Aarogya One Hospital (Fictional Tertiary Care Multi-Specialty Hospital, Bengaluru)  
**Challenge**: Great Indian AI Internship Challenge  
**Status**: Phase 1 Foundation Fully Implemented & 26/26 Pytest Tests Passing  

---

### Key Deliverables in Phase 1

1. **Modular Backend Architecture**:
   - `backend/app/main.py`: FastAPI server with OpenAPI docs at `/docs`.
   - `backend/app/core/config.py`: Pydantic settings & database configurations.
   - `backend/app/db/`: Base and Session lifecycle with transaction management.
   - `backend/app/models/`: 8 SQLAlchemy 2.x declarative models with PostgreSQL constraints.
   - `backend/app/schemas/`: Pydantic v2 schemas for request validation & responses.
   - `backend/app/services/`: Business services & typed AI tool interfaces.
   - `backend/app/api/v1/`: Full REST endpoints for hospitals, doctors, appointments, lab orders, and workflow.

2. **Database Schema & Reliability**:
   - **Unique Slot Constraint**: `uq_appointment_slot_id` prevents double booking at the database level.
   - **Doctor-Slot Ownership**: Strict validation in transaction before slot locking.
   - **Controlled State Transitions**: Server controls initial appointment status (`CONFIRMED`).
   - **Audit Events**: Full audit trail for booking, cancellation, completion, and workflow exceptions.

3. **AI Tool Interfaces Ready (Section 9)**:
   - `search_doctors_tool`: Structured search by specialty or department.
   - `get_available_slots_tool`: Confirmed open slots with date & time filters.
   - `book_appointment_tool`: Transaction-safe booking with allowlist protection.

4. **Synthetic Seed Data**:
   - Repeatable seed script: `backend/scripts/seed_data.py`.
   - Aarogya One Hospital, 5 departments, 6 doctors, 36 future slots, 3 synthetic appointments, 3 synthetic lab orders (including an overdue Processing order for workflow testing), workflow exceptions, and audit events.

5. **Automated Test Suite**:
   - 26 tests in `backend/tests/` covering all critical operations.
   - Run tests: `PYTHONPATH=backend pytest backend/tests/ -v`.

---

### Quick Start Commands

```bash
# 1. Install Python requirements
pip install -r backend/requirements.txt

# 2. Run seed script (creates demo SQLite or connects to PostgreSQL)
python3 backend/scripts/seed_data.py --reset

# 3. Run Pytest suite
PYTHONPATH=backend pytest backend/tests/ -v

# 4. Start FastAPI server
python3 -m uvicorn app.main:app --app-dir backend --port 8000 --reload
```
