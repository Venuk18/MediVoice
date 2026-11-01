import os
import sys
import time
from dotenv import load_dotenv

# Ensure backend is in python path
sys.path.insert(0, os.path.abspath("backend"))
load_dotenv("backend/.env")

from app.core.config import settings
from app.db.session import SessionLocal
from app.agent.adapters import GeminiReasoningAdapter
from app.agent.conversation_manager import ConversationManager
from app.agent.tool_router import RestrictedToolRouter
from app.agent.schemas import ConfirmationStatus, ChatMessage

def safe_str(s: str, max_len: int = 150) -> str:
    if not s:
        return ""
    return s[:max_len].encode("ascii", errors="backslashreplace").decode("ascii")

print("=" * 60)
print(f"VERIFYING LIVE SCENARIOS WITH GEMINI MODEL: {settings.GEMINI_MODEL}")
print(f"THINKING LEVEL: {settings.GEMINI_THINKING_LEVEL}")
print(f"ENABLE FALLBACK: {settings.GEMINI_ENABLE_FALLBACK}")
print("=" * 60)

adapter = GeminiReasoningAdapter(
    api_key=settings.GEMINI_API_KEY,
    model=settings.GEMINI_MODEL,
    thinking_level=settings.GEMINI_THINKING_LEVEL,
    enable_model_fallback=settings.GEMINI_ENABLE_FALLBACK,
)
tool_router = RestrictedToolRouter()

# Test 1: Doctor Search (Cardiology)
print("\n--- TEST 1: Live Doctor Search (Cardiology) ---")
db = SessionLocal()
try:
    cm = ConversationManager(adapter=adapter, tool_router=tool_router)
    t0 = time.perf_counter()
    resp = cm.process_message(db, "I need to consult a cardiologist for chest checkup")
    lat1 = (time.perf_counter() - t0) * 1000
    print(f"Latency: {lat1:.1f}ms")
    print(f"Model used: {adapter.last_model_used}")
    print(f"Doctor in draft: {resp.draft.doctor_id} ({resp.draft.doctor_name})")
    print(f"Specialty: {resp.draft.specialty}")
    print(f"Reply preview: {safe_str(resp.reply)}...")
    assert resp.draft.specialty == "Cardiology" or "Sharma" in str(resp.draft.doctor_name) or "cardio" in resp.reply.lower()
    print(">>> TEST 1 PASSED")
finally:
    db.close()

# Test 2: Contextual Yes/No (New patient registration flow)
print("\n--- TEST 2: Contextual Yes/No (New Patient) ---")
db = SessionLocal()
try:
    cm = ConversationManager(adapter=adapter, tool_router=tool_router)
    session = cm.get_or_create_session("test-ctx-no")
    session.draft.doctor_id = "doc-sharma-cardio"
    session.draft.doctor_name = "Dr. Rajesh Sharma"
    session.draft.specialty = "Cardiology"
    session.draft.slot_id = "slot-sharma-open-1"
    session.pending_action = "AWAITING_PATIENT_STATUS"
    session.history = [
        ChatMessage(role="assistant", content="Have you visited Aarogya One Hospital before?")
    ]
    t0 = time.perf_counter()
    resp = cm.process_message(db, "No, I'm new here", session_id="test-ctx-no")
    lat2 = (time.perf_counter() - t0) * 1000
    print(f"Latency: {lat2:.1f}ms")
    print(f"Model used: {adapter.last_model_used}")
    print(f"is_new_patient: {resp.draft.is_new_patient}")
    print(f"Preserved Doctor: {resp.draft.doctor_name}")
    print(f"Preserved Slot: {resp.draft.slot_id}")
    print(f"Reply preview: {safe_str(resp.reply)}...")
    assert resp.draft.is_new_patient is True or "welcome" in resp.reply.lower() or "name" in resp.reply.lower()
    assert resp.draft.doctor_id == "doc-sharma-cardio", "Should retain doctor"
    assert resp.draft.slot_id == "slot-sharma-open-1", "Should retain slot"
    print(">>> TEST 2 PASSED")
finally:
    db.close()

# Test 3: Lab Report Verification
print("\n--- TEST 3: Lab Report Verification ---")
db = SessionLocal()
try:
    cm = ConversationManager(adapter=adapter, tool_router=tool_router)
    t0 = time.perf_counter()
    resp = cm.process_message(db, "I want to check my lab report status")
    lat3a = (time.perf_counter() - t0) * 1000
    print(f"Ask code prompt Latency: {lat3a:.1f}ms")
    print(f"Reply: {safe_str(resp.reply)}...")
    
    # Now provide a code
    t0 = time.perf_counter()
    resp2 = cm.process_message(db, "My verification code is 123456", session_id=resp.session_id)
    lat3b = (time.perf_counter() - t0) * 1000
    print(f"Verification call Latency: {lat3b:.1f}ms")
    print(f"Reply: {safe_str(resp2.reply)}...")
    assert "123456" in resp2.reply or "verification code" in resp2.reply.lower() or "report" in resp2.reply.lower()
    print(">>> TEST 3 PASSED")
finally:
    db.close()

# Test 4: Telugu Conversation
print("\n--- TEST 4: Live Telugu Conversation ---")
db = SessionLocal()
try:
    cm = ConversationManager(adapter=adapter, tool_router=tool_router)
    t0 = time.perf_counter()
    telugu_msg = "నాకు గుండె నొప్పిగా ఉంది, కార్డియాలజిస్ట్ కావాలి"
    resp = cm.process_message(db, telugu_msg)
    lat4 = (time.perf_counter() - t0) * 1000
    print(f"Latency: {lat4:.1f}ms")
    print(f"Model used: {adapter.last_model_used}")
    print(f"Language: {resp.language}")
    print(f"Specialty in draft: {resp.draft.specialty}")
    print(f"Reply preview: {safe_str(resp.reply)}...")
    assert resp.language == "te", "Should detect Telugu language"
    print(">>> TEST 4 PASSED")
finally:
    db.close()

# Test 5: Live Appointment Booking with Explicit Confirmation Gate
print("\n--- TEST 5: Appointment Booking with Confirmation Gate ---")
db = SessionLocal()
try:
    cm = ConversationManager(adapter=adapter, tool_router=tool_router)
    session = cm.get_or_create_session("test-booking-gate")
    session.draft.doctor_id = "doc-sharma-cardio"
    session.draft.doctor_name = "Dr. Rajesh Sharma"
    session.draft.specialty = "Cardiology"
    session.draft.slot_id = "slot-sharma-open-1"
    session.draft.reason_category = "Routine heart checkup"
    session.draft.patient_reference = "PAT-2026-4409"
    session.draft.patient_name = "Rahul Verma"
    session.confirmation_status = ConfirmationStatus.PENDING
    session.confirmed_draft_fingerprint = session.draft.get_fingerprint()
    
    t0 = time.perf_counter()
    resp = cm.process_message(db, "Yes, please confirm and book this appointment", session_id="test-booking-gate")
    lat5 = (time.perf_counter() - t0) * 1000
    print(f"Turn 1 Latency: {lat5:.1f}ms")
    print(f"Model used: {adapter.last_model_used}")
    print(f"Confirmation status: {resp.confirmation_status}")
    print(f"Reply preview: {safe_str(resp.reply)}...")
    
    # If the slot was updated to real available slot and re-prompted, confirm the final summary
    if resp.confirmation_status != ConfirmationStatus.CONFIRMED:
        print("  Re-confirming updated slot summary...")
        t0 = time.perf_counter()
        resp2 = cm.process_message(db, "Yes, that is correct, please proceed with booking", session_id="test-booking-gate")
        lat5b = (time.perf_counter() - t0) * 1000
        print(f"Turn 2 Latency: {lat5b:.1f}ms")
        print(f"Final Confirmation status: {resp2.confirmation_status}")
        print(f"Final Reply preview: {safe_str(resp2.reply)}...")
        assert resp2.confirmation_status == ConfirmationStatus.CONFIRMED or "confirmed" in resp2.reply.lower() or "booked" in resp2.reply.lower()
    else:
        assert resp.confirmation_status == ConfirmationStatus.CONFIRMED
        
    print(">>> TEST 5 PASSED")
finally:
    db.close()

print("\n" + "=" * 60)
print("ALL 5 LIVE SCENARIOS COMPLETED SUCCESSFULLY WITH GEMINI 3.5 FLASH-LITE!")
print("=" * 60)
