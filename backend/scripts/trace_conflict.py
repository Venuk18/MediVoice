import sys
sys.path.insert(0, "backend")
import httpx
from app.agent.adapters import GeminiReasoningAdapter
from app.agent.conversation_manager import ConversationManager
from app.database import SessionLocal
from tests.conftest import seeded_hospital_data

db = SessionLocal()
def conflict_transport(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "text": (
                                    "Please confirm slot-sharma-booked-3.\n"
                                    '<draft>{"doctor_id": "doc-sharma-1", "doctor_name": "Dr. Rajesh Sharma", '
                                    '"specialty": "Cardiology", "slot_id": "slot-sharma-booked-3", '
                                    '"reason_category": "Checkup", "patient_reference": "PAT-2026-CONF"}</draft>'
                                )
                            }
                        ],
                    }
                }
            ]
        },
    )

mock_client = httpx.Client(transport=httpx.MockTransport(conflict_transport))
adapter = GeminiReasoningAdapter(api_key="mock-key", http_client=mock_client)
manager = ConversationManager(adapter=adapter)
r1 = manager.process_message(db=db, session_id="gemini-conflict-test", message="Book slot-sharma-booked-3")
print("Step:", r1.step)
print("Draft:", r1.draft)
print("Reply:", r1.reply)
db.close()

