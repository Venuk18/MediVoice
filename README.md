# MediVoice AI — Voice-First Hospital Operations Platform
## Phase 1 & Phase 2 Complete: Text-First AI Agent

**Hospital**: Aarogya One Hospital (Fictional Tertiary Care Multi-Specialty Hospital, Bengaluru)  
**Challenge**: Great Indian AI Internship Challenge  
**Status**: Phase 1 Foundation & Phase 2 Text-First AI Agent Fully Implemented & 37/37 Pytest Tests Passing  

---

### Key Deliverables in Phase 2 (Text-First AI Agent)

1. **Stateful Conversation Manager (`backend/app/agent/conversation_manager.py`)**:
   - Manages multi-turn conversation sessions (`session_id`).
   - Identifies and prompts turn-by-turn for missing booking parameters (doctor, slot, reason, patient reference).
   - Strict session isolation: patient references and drafts never leak across sessions.
   - Tied to exact draft fingerprint: changing doctor, slot, reason, or patient ID immediately invalidates previous confirmations (`STALE`).

2. **Reasoning Model Adapter (`backend/app/agent/adapters.py`)**:
   - Clean provider-agnostic interface (`BaseReasoningAdapter`) allowing future integration with Gnani AI, Evon, Gemini, etc.
   - Deterministic `MockReasoningAdapter` for zero external API credit consumption and reproducible test execution.

3. **Restricted Allowlisted Tool Router (`backend/app/agent/tool_router.py`)**:
   - Strictly allowlists only 3 backend tools: `search_doctors`, `get_available_slots`, `book_appointment`.
   - Blocks unauthorized tools and direct SQL / database execution attempts.
   - Validates argument schemas strictly before invoking backend services.

4. **Explicit Confirmation Gate**:
   - The AI agent is prohibited from executing `book_appointment` until all 4 parameters are present AND the patient explicitly confirms ("YES" / "CONFIRM").
   - Re-validates slot availability inside the transactional backend booking service.
   - Reports success only after database transaction commits and returns the confirmed appointment.

5. **Phase 2 Agent API (`backend/app/api/v1/agent.py`)**:
   - `POST /api/v1/agent/chat`: Multi-turn chat with slot filling and confirmation gating.
   - `GET /api/v1/agent/sessions/{session_id}`: Inspect session state.
   - `POST /api/v1/agent/sessions/{session_id}/reset`: Reset session state.

6. **Automated Test Suite (11 New Tests, 37 Total Passing)**:
   - Covers: tool allowlist & argument validation, doctor search, slot discovery, missing details prompts, confirmation gating, stale confirmation invalidation, duplicate confirmation handling, session isolation, unavailable slot conflicts, and transactional DB booking.

---

### Key Deliverables in Phase 1 (Foundation)

1. **Modular Backend Architecture**: FastAPI server with PostgreSQL/SQLite declarative models (`backend/app/models/`).
2. **Database Integrity & Constraints**: `uq_appointment_slot_id` unique constraint preventing double booking.
3. **Transactional Services**: Atomic slot locking and audit event generation in `backend/app/services/`.
4. **Synthetic Seed Data**: Aarogya One Hospital synthetic seed in `backend/scripts/seed_data.py`.

---

### Verification & Local Commands

```powershell
# 1. Run full Pytest suite (37 tests across Phase 1 and Phase 2)
$env:PYTHONPATH="backend"; $env:DATABASE_URL="sqlite:///aarogya_demo.db"; py -m pytest backend/tests/ -v

# 2. Run TypeScript check
npm run lint

# 3. Build Vite production bundle
npm run build

# 4. Start FastAPI server
$env:PYTHONPATH="backend"; $env:DATABASE_URL="sqlite:///aarogya_demo.db"; py -m uvicorn app.main:app --app-dir backend --port 8000 --reload

# 5. Start Frontend Dev Server
npm run dev
```
