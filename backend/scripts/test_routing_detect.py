import os
import sys
import time
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("backend"))
load_dotenv("backend/.env")

from app.core.config import settings
from app.db.session import SessionLocal
from app.agent.adapters import GeminiReasoningAdapter, detect_specialty_query
from app.agent.conversation_manager import ConversationManager
from app.agent.tool_router import RestrictedToolRouter

print("Testing deterministic routing detection:")
test_queries = [
    "Search for a cardiologist",
    "Find a general physician",
    "I need Dr. Vikram Mehta",
    "Do you accept Star Health Insurance?",
    "Check available slots",
]

for q in test_queries:
    spec = detect_specialty_query(q)
    print(f"Query: '{q}' -> Specialty: {spec}")

