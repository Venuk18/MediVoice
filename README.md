# MediVoice AI — Aarogya One Hospital Operations Platform

**One conversational entry point. Multiple hospital workflows. Controlled, connected operations.**

MediVoice AI is a multilingual conversational assistant (`en`, `te`, `hi`, `ta`, `kn`) integrated with real hospital operational workflows for **Aarogya One Hospital** (a fictional demonstration environment using synthetic data).

---

## Repository Structure

```text
MediVoice-AI/
├── backend/                 # FastAPI + SQLAlchemy 2.x + Pydantic v2 backend
│   ├── alembic/             # Database migrations
│   ├── app/
│   │   ├── agent/           # Multilingual AI agent, adapters, session state & tool router
│   │   ├── api/v1/          # REST API endpoints (auth, doctors, appointments, lab-orders, insurance, maintenance, workflow)
│   │   ├── core/            # Security, RBAC & configuration
│   │   ├── db/              # Database engine & session management
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   └── services/        # Validated domain business logic
│   ├── scripts/             # Idempotent synthetic data seeding (seed_data.py)
│   └── tests/               # Comprehensive pytest test suite
├── frontend/                # Modular React + TypeScript + Tailwind CSS frontend
│   ├── src/
│   │   ├── app/             # Application shell & shared PlatformContext
│   │   ├── components/      # TopNav (3-zone contract) & StaffAuthGate
│   │   ├── features/
│   │   │   ├── patient/     # Colorful, accessible patient website and care workflows
│   │   │   ├── chatbot/     # Embedded & Full-Screen MediVoice AI Conversational Experience
│   │   │   ├── doctor/      # Light Operational Doctor Workspace (/doctor/*)
│   │   │   ├── laboratory/  # Light Operational Laboratory Operator Workspace (/lab/*)
│   │   │   └── maintenance/ # Light Operational Maintenance & Admin Workspace (/maintenance/*)
│   │   ├── services/        # Centralized typed API client (medivoiceApi)
│   │   ├── hooks/           # Multi-page route & workspace state hook
│   │   └── types/           # Complete TypeScript API & domain interfaces
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

---

## Four Connected Hospital Experiences

1. **Patient Hospital Website & MediVoice AI Chatbot (`/`, `/doctors`, `/appointments`, `/lab-status`, `/insurance`, `/support`, `/medivoice`)**
   - Colorful, accessible patient experience with clear appointment, laboratory status, and insurance flows.
   - Hospital overview, clinical wings, specialist directory, two-step explicit appointment confirmation, 6-digit laboratory status verification, document-grounded insurance search, and human-support ticket escalation.
   - Dedicated embedded and full-screen **MediVoice AI** conversational experience in English, Telugu, Hindi, Tamil, and Kannada.
   - Patient appointment records are accessed through an opaque private booking reference saved in the current browser session. Anyone who obtains that reference may view or cancel the appointment; this is a demo capability, not verified patient identity.
2. **Doctor Workspace (`/doctor`, `/doctor/appointments`, `/doctor/calendar`, `/doctor/availability`, `/doctor/profile`)**
   - Refined low-glare light operational theme protected by `DOCTOR` / `ADMIN` role.
   - Daily schedule, consultation completion, follow-up recommendation persistence, and live open slot publishing (`POST /api/v1/doctors/{id}/slots`).
3. **Laboratory Operator Workspace (`/lab`, `/lab/orders`)**
   - Protected by `LAB_OPERATOR` / `ADMIN` role.
   - Diagnostic sample queue, canonical status transitions (`REGISTERED` → `SAMPLE_COLLECTED` → `PROCESSING` → `COMPLETED` / `CANCELLED`), new synthetic order registration, and deterministic overdue SLA escalation.
4. **Hospital Maintenance & Operations Workspace (`/maintenance`, `/maintenance/work-orders`, `/maintenance/new-request`, `/maintenance/doctors`, `/maintenance/insurance`, `/maintenance/tickets`)**
   - Protected by `MAINTENANCE_STAFF` / `ADMIN` role.
   - Facilities & biomedical work-order management enforcing `OPEN → ASSIGNED → IN_PROGRESS → RESOLVED`.
   - **Manage Doctors**: Add new doctors with automatic slot seeding (`POST /api/v1/doctors`) or remove doctors (`DELETE /api/v1/doctors/{id}`).
   - **Manage Insurances**: Add new insurance providers & plans (`POST /api/v1/insurance/providers`) or remove providers (`DELETE /api/v1/insurance/providers/{id}`).
   - **Conflicts & Human-Support Tickets**: Assign and resolve overdue SLA workflow conflicts and escalated patient insurance inquiries.

---

## Project Setup and Verification

This repository includes two Vite frontends: the root app (`work/src`) and the polished frontend module (`work/frontend/src`) used by the preview. Build both after frontend changes:

```powershell
npm install
npm run build
cd frontend
npm install
npm run build
```

For backend setup and checks:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DATABASE_URL = "sqlite:///./medivoice.db"
$env:LLM_PROVIDER = "mock"
python -m pytest -q
```

To start the API after installing backend requirements, open another terminal in `backend`, activate `.venv`, then run `python -m uvicorn app.main:app --reload --port 8001`. Start the frontend from its folder with `npm run dev`.

Use synthetic data only. Demo staff accounts and the local token secret are for development; production deployment requires replacing synthetic accounts with managed credentials, setting a strong `MEDIVOICE_AUTH_SECRET`, and implementing verified patient identity before handling real patient data. The lab verification-code lookup utility is staff-only; patients check status using the private code on their receipt.
