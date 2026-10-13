# MediVoice AI — Phase 1: Backend Foundation and Database Design
**Hospital Context:** Aarogya One Hospital (Fictional Tertiary Healthcare Center, Bengaluru)  
**Program:** Great Indian AI Internship Challenge  
**Phase Status:** Phase 1 Foundation Completed & Verified  

---

## 1. Architectural Overview

MediVoice AI is designed as an enterprise, voice-first hospital operations platform. Phase 1 establishes the rock-solid transactional and relational database foundation, ensuring that future reasoning models and speech pipelines interact solely with strictly-typed, validated tool functions and never execute raw SQL or mutate database state directly.

```
                           ┌──────────────────────────────┐
                           │   Future AI Voice Agent      │
                           │ (Gnani Prisma / Timbre / AI) │
                           └──────────────┬───────────────┘
                                          │
                  [Restricted Tool Allowlist & Schema Validation]
                                          │
                                          ▼
                      ┌───────────────────────────────────────┐
                      │        FastAPI REST & Tool API        │
                      │  - search_doctors                     │
                      │  - get_available_slots                │
                      │  - book_appointment (Atomic Tx)       │
                      └──────────────────┬────────────────────┘
                                         │
                         [SQLAlchemy 2.x ORM & Pydantic v2]
                                         │
                                         ▼
                      ┌───────────────────────────────────────┐
                      │    PostgreSQL Database (or SQLite)    │
                      │  - Hospitals / Departments            │
                      │  - Doctors / AppointmentSlots         │
                      │  - Appointments (Unique slot_id)      │
                      │  - LabOrders (Workflow metadata only) │
                      │  - WorkflowExceptions & AuditEvents   │
                      └───────────────────────────────────────┘
```

---

## 2. Directory Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application entrypoint & OpenAPI /docs
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py               # Pydantic Settings & environment configuration
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                 # DeclarativeBase definition
│   │   └── session.py              # Engine creation & session lifecycle dependency
│   ├── models/                     # SQLAlchemy 2.x declarative models
│   │   ├── __init__.py
│   │   ├── hospital.py             # Hospital model
│   │   ├── department.py           # Department model
│   │   ├── doctor.py               # Doctor model
│   │   ├── appointment_slot.py     # Slot availability & unique constraint
│   │   ├── appointment.py          # Appointment records & unique slot constraint
│   │   ├── lab_order.py            # Workflow metadata (no clinical results)
│   │   ├── workflow_exception.py   # Operational exception & resolution model
│   │   └── audit_event.py          # Immutable audit logging for all actions
│   ├── schemas/                    # Pydantic v2 request/response schemas
│   │   ├── __init__.py
│   │   ├── hospital.py
│   │   ├── doctor.py
│   │   ├── appointment.py
│   │   ├── lab_order.py
│   │   └── workflow.py
│   ├── services/                   # Business logic & AI Tool interface boundaries
│   │   ├── __init__.py
│   │   ├── doctor_service.py       # Doctor retrieval & AI tools
│   │   ├── appointment_service.py  # Atomic booking, cancellation & completion
│   │   ├── lab_service.py          # Lab order workflow metadata management
│   │   └── workflow_service.py     # Deterministic overdue order detection & resolution
│   └── api/
│       ├── __init__.py
│       └── v1/
│           ├── __init__.py
│           ├── router.py           # Aggregate v1 API router
│           ├── hospitals.py        # /api/v1/hospitals
│           ├── doctors.py          # /api/v1/doctors and /slots
│           ├── appointments.py     # /api/v1/appointments, /cancel, /complete, /follow-up
│           ├── lab_orders.py       # /api/v1/lab-orders
│           └── workflow.py         # /api/v1/workflow/exceptions, /detect, /assign, /resolve
├── tests/                          # Automated Pytest suite (26 comprehensive tests)
│   ├── __init__.py
│   ├── conftest.py                 # TestClient & in-memory test DB fixtures
│   ├── test_doctors.py             # Doctor query, specialty filter, slots & AI tools
│   ├── test_appointments.py        # Atomic booking, double-booking prevention, cancellations
│   ├── test_lab_orders.py          # Lab status updates & validations
│   └── test_workflow.py            # Overdue detection, assignment, resolution & audit trail
├── scripts/
│   ├── __init__.py
│   └── seed_data.py                # Idempotent synthetic seeding script
├── alembic/
│   ├── env.py                      # Alembic database target metadata configuration
│   ├── script.py.mako              # Migration file template
│   └── versions/
│       └── 0001_initial_schema.py  # Production migration establishing all 8 tables
├── alembic.ini                     # Alembic configuration
├── requirements.txt                # Python dependencies
├── .env.example                    # Template environment variables
└── README.md                       # Architecture & execution guide
```

---

## 3. Database Schema Design

### 3.1 Entities & Relational Guarantees
1. **Hospital**:
   - Primary key: `id` (UUID string)
   - `name`, `description`, `address`, `is_active`, `created_at`
   - Pre-seeded with **Aarogya One Hospital** in Bengaluru.

2. **Department**:
   - `id`, `hospital_id` (FK -> hospitals.id, ON DELETE CASCADE)
   - `name`, `description`, `is_active`, `created_at`
   - Seeded: Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine.

3. **Doctor**:
   - `id`, `hospital_id`, `department_id` (FK -> departments.id)
   - `display_name`, `specialty`, `is_active`, `created_at`
   - Seeded with 6 fictional physicians across departments.

4. **AppointmentSlot**:
   - `id`, `doctor_id` (FK -> doctors.id)
   - `start_time` (indexed), `end_time`, `status` (`AVAILABLE`, `RESERVED`, `BOOKED`, `CANCELLED`), `created_at`
   - **Database-level constraint**: `UniqueConstraint("doctor_id", "start_time", name="uq_doctor_slot_start_time")`.

5. **Appointment**:
   - `id`, `patient_reference` (indexed), `doctor_id` (FK -> doctors.id)
   - `slot_id` (FK -> appointment_slots.id, ON DELETE RESTRICT, **UNIQUE**).
   - **Double-booking protection**: The unique constraint on `slot_id` physically prevents any two appointment rows from referencing the same slot.
   - `appointment_status`: Server controlled (`CONFIRMED`, `COMPLETED`, `CANCELLED`, `NO_SHOW`).
   - `reason_category`, `created_at`, `updated_at`, `visit_completed_at`.
   - `follow_up_recommended`, `follow_up_date`, `follow_up_notes`.

6. **LabOrder**:
   - `id`, `patient_reference`, `ordering_department_id` (FK -> departments.id, ON DELETE SET NULL)
   - `test_category`, `workflow_status` (`Pending`, `Processing`, `Completed`, `Delayed`)
   - `expected_completion_at`, `assigned_team`, `delay_reason`, `created_at`, `updated_at`
   - *Strict boundary: Workflow metadata only; does not store or process clinical laboratory results.*

7. **WorkflowException**:
   - `id`, `exception_type`, `title`, `description`, `priority` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
   - `responsible_department`, `assigned_to`, `status` (`OPEN`, `IN_PROGRESS`, `RESOLVED`, `DISMISSED`)
   - `affected_record_type`, `affected_record_id`, `detected_at`, `updated_at`, `resolved_at`, `resolution_note`

8. **AuditEvent**:
   - `id`, `actor_reference`, `action`, `entity_type`, `entity_id`, `details`, `created_at`
   - Automatically records booking, cancellations, visit completions, follow-up recommendations, exception detections, assignments, and resolutions.

---

## 4. Booking Reliability & Concurrency Safeguards

The `book_appointment` service implements multi-tier validation:
1. **Ownership verification**: Confirms `slot.doctor_id == doctor_id` to prevent cross-physician booking errors.
2. **Temporal validity**: Confirms `slot.start_time > now_utc` (past slots are rejected with HTTP 400).
3. **Availability check**: Confirms `slot.status == 'AVAILABLE'` (non-available slots return HTTP 409 Conflict).
4. **Row-level concurrency lock**: Utilizes `with_for_update()` in PostgreSQL dialects during slot selection.
5. **Database unique constraint**: `uq_appointment_slot_id` ensures that even in race conditions, only one transaction can commit.
6. **Atomic commit & rollback**: Slot status transition to `BOOKED`, appointment record creation, and `AuditEvent` insertion occur in a single atomic transaction.
7. **Consistent cancellation**: Cancelling an appointment sets status to `CANCELLED` and safely reverts slot status back to `AVAILABLE`.

---

## 5. AI Tool Service Interfaces (Section 9)

In preparation for future voice and agent orchestration, typed Python functions are exposed:

### 1. `search_doctors_tool(db, specialty_or_department, hospital_id)`
- **Input**: `specialty_or_department` (str), `hospital_id` (optional str)
- **Output**: List of dicts `[{"doctor_id", "display_name", "specialty", "department_name", "hospital_id"}]`
- **Safety**: Pure query, read-only.

### 2. `get_available_slots_tool(db, doctor_id, requested_date, time_range)`
- **Input**: `doctor_id` (str), `requested_date` (optional "YYYY-MM-DD"), `time_range` (optional "morning"|"afternoon"|"evening")
- **Output**: List of dicts `[{"slot_id", "doctor_id", "doctor_name", "start_time", "end_time", "status"}]`
- **Safety**: Filters exclusively for `status == "AVAILABLE"`.

### 3. `book_appointment_tool(db, patient_reference, doctor_id, selected_slot_id, reason_category)`
- **Input**: `patient_reference` (str), `doctor_id` (str), `selected_slot_id` (str), `reason_category` (str)
- **Output**: Dict with confirmed booking identifier, physician details, and status.
- **Safety**: Client/AI cannot supply status; forced server default `CONFIRMED`. Cannot override doctor-slot ownership or booking constraints.

---

## 6. Setup & Execution Guide

### 6.1 Prerequisites
- Python 3.10+ (Verified on Python 3.11.2)
- PostgreSQL (or local SQLite for zero-daemon testing)

### 6.2 Environment Setup
```bash
# Clone and enter backend directory
cd backend

# Create virtual environment (optional)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

### 6.3 Database Migrations (Alembic)
For PostgreSQL:
```bash
# Apply migrations to configured database
alembic upgrade head
```

### 6.4 Seeding Synthetic Data
```bash
# Populate Aarogya One Hospital synthetic records
python3 scripts/seed_data.py

# Optional: Reset and re-seed from scratch
python3 scripts/seed_data.py --reset
```

### 6.5 Running FastAPI Development Server
```bash
# Start server on port 8000
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive OpenAPI documentation will be accessible at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### 6.6 Running the Test Suite (Pytest)
```bash
PYTHONPATH=. pytest tests/ -v
```
All 26 tests run against an isolated in-memory SQLite fixture and pass in under 1 second.

---

## 7. Example API Requests & Responses

### 7.1 Search Doctors
**Request:**
```http
GET /api/v1/doctors?specialty=Cardiology
```
**Response (200 OK):**
```json
[
  {
    "id": "33333333-0001-0000-0000-000000000001",
    "hospital_id": "11111111-1111-1111-1111-111111111111",
    "department_id": "22222222-0001-0000-0000-000000000001",
    "display_name": "Dr. Rajesh Sharma",
    "specialty": "Cardiology",
    "is_active": true,
    "created_at": "2026-10-12T07:55:00Z",
    "department_name": "Cardiology",
    "hospital_name": "Aarogya One Hospital"
  }
]
```

### 7.2 Book Appointment
**Request:**
```http
POST /api/v1/appointments
Content-Type: application/json

{
  "patient_reference": "PAT-2024-9182",
  "doctor_id": "33333333-0001-0000-0000-000000000001",
  "slot_id": "slot-uuid-here",
  "reason_category": "Chest Pain & Palpitations Evaluation"
}
```
**Response (201 Created):**
```json
{
  "id": "44444444-0001-0000-0000-000000000001",
  "patient_reference": "PAT-2024-9182",
  "doctor_id": "33333333-0001-0000-0000-000000000001",
  "slot_id": "slot-uuid-here",
  "appointment_status": "CONFIRMED",
  "reason_category": "Chest Pain & Palpitations Evaluation",
  "created_at": "2026-10-12T07:55:00Z",
  "updated_at": "2026-10-12T07:55:00Z",
  "visit_completed_at": null,
  "follow_up_recommended": false,
  "follow_up_date": null,
  "follow_up_notes": null,
  "doctor_name": "Dr. Rajesh Sharma",
  "doctor_specialty": "Cardiology",
  "slot_start_time": "2026-10-13T10:00:00Z",
  "slot_end_time": "2026-10-13T10:30:00Z"
}
```

### 7.3 Double Booking Rejection
**Response (409 Conflict):**
```json
{
  "detail": "Slot is no longer available (current status: 'BOOKED')."
}
```

---

## 8. Strict Scope Boundary Compliance

| Feature / Boundary | Phase 1 Status | Note |
|--------------------|----------------|------|
| **SQLAlchemy 2.x Schema & Models** | COMPLETED | All 8 models defined with foreign keys and indexes |
| **Alembic Migration** | COMPLETED | Migration `0001_initial_schema.py` generated |
| **Synthetic Seed Script** | COMPLETED | `scripts/seed_data.py` populates Aarogya One Hospital |
| **Doctor & Slot Retrieval Endpoints** | COMPLETED | `/api/v1/doctors`, `/slots` with filters |
| **Transaction-Safe Booking** | COMPLETED | Atomic booking, unique constraint, rollback on conflict |
| **Controlled Cancellation & Re-release** | COMPLETED | Reverts slot to AVAILABLE, records AuditEvent |
| **Follow-up Recommendation** | COMPLETED | Non-clinical operational recommendation, no auto-booking |
| **AI Tool Python Interfaces** | COMPLETED | `search_doctors_tool`, `get_available_slots_tool`, `book_appointment_tool` |
| **Pytest Suite** | COMPLETED | 26 tests passing (100% test pass rate) |
| **Gnani Prisma STT** | EXCLUDED (Phase 2) | No speech recognition calls |
| **Timbre TTS** | EXCLUDED (Phase 2) | No speech synthesis calls |
| **Evon Reasoning Model** | EXCLUDED (Phase 2) | No external model credit usage |
| **Raw SQL AI Access** | EXCLUDED (Forbidden) | Restricted typed tool boundaries only |
| **Clinical Records / EMR** | EXCLUDED | Only operational scheduling and workflow metadata |
