from abc import ABC, abstractmethod
import re
from typing import List, Dict, Any, Optional

from app.agent.schemas import (
    AgentAction,
    AgentSessionState,
    ChatMessage,
    ConversationStep,
    ConfirmationStatus,
    ToolCallIntent,
)


def is_cancellation(text: str) -> bool:
    """Detects patient cancellation or abort intent."""
    low = text.strip().lower()
    cancel_patterns = [
        r"\b(cancel|no|stop|abort|nevermind)\b",
        r"\bdon't book\b",
        r"\bdo not book\b",
    ]
    for pattern in cancel_patterns:
        if re.search(pattern, low):
            return True
    return False


def is_affirmative(text: str) -> bool:
    """Detects explicit positive confirmation."""
    low = text.strip().lower()
    affirmatives = [
        r"\b(yes|confirm|proceed|ok|okay|sure|yup|yeah)\b",
        r"\bplease book\b",
        r"\bbook it\b",
        r"\bgo ahead\b",
    ]
    for pattern in affirmatives:
        if re.search(pattern, low):
            return True
    return False


class BaseReasoningAdapter(ABC):
    """
    Abstract interface for reasoning-model adapters.
    Ensures clean decoupling so provider can be switched to Gnani AI, Evon,
    Gemini, or other providers without modifying the conversation manager or tool router.
    """

    @abstractmethod
    def plan_and_respond(
        self,
        session_state: AgentSessionState,
        user_message: str,
        available_tools: List[str],
    ) -> AgentAction:
        """
        Analyzes conversation context, extracts medical/booking entities,
        and returns either an immediate text response or a tool invocation intent.
        """
        pass


class MockReasoningAdapter(BaseReasoningAdapter):
    """
    Deterministic, rule-based reasoning adapter for Phase 2 MVP.
    Consumes zero external AI credits and operates without requiring live speech/LLM APIs.
    Simulates intelligent clinical entity extraction, slot filling, and dialogue state management.
    """

    SPECIALTY_KEYWORDS: Dict[str, List[str]] = {
        "Cardiology": ["heart", "cardio", "cardiology", "chest pain", "palpitation", "palpitations", "angina"],
        "Neurology": ["brain", "neuro", "neurology", "headache", "migraine", "stroke", "seizure", "numbness"],
        "Orthopedics": ["bone", "joint", "ortho", "orthopedics", "knee", "fracture", "spine", "back pain", "arthritis"],
        "Pediatrics": ["child", "children", "pediatric", "pediatrics", "infant", "baby", "kid", "vaccination"],
        "General Medicine": ["fever", "cough", "cold", "flu", "weakness", "general", "physician", "checkup", "routine"],
    }

    DOCTOR_KEYWORDS: List[Dict[str, Any]] = [
        {"search_term": "Sharma", "keywords": ["sharma", "rajesh"]},
        {"search_term": "Nair", "keywords": ["nair", "priya"]},
        {"search_term": "Swamy", "keywords": ["swamy", "arvind"]},
        {"search_term": "Sen", "keywords": ["sen", "ananya"]},
        {"search_term": "Mehta", "keywords": ["mehta", "vikram"]},
        {"search_term": "Rao", "keywords": ["rao", "sunita"]},
    ]

    def plan_and_respond(
        self,
        session_state: AgentSessionState,
        user_message: str,
        available_tools: List[str],
    ) -> AgentAction:
        msg = user_message.strip()
        lower = msg.lower()
        draft = session_state.draft

        # 1. Check for cancellation intent
        if is_cancellation(msg):
            return AgentAction(
                reply="Understood. The appointment booking has been cancelled. Let me know if you would like to explore other doctors or services."
            )

        # 2. Extract Patient Reference (e.g., PAT-2024-9182, PAT-1234, etc.)
        pat_match = re.search(r"\b(PAT-[A-Za-z0-9-]+)\b", msg, re.IGNORECASE)
        if pat_match:
            draft.patient_reference = pat_match.group(1).upper()

        # 3. Detect Slot ID match (e.g. slot-101, slot-sharma-avail-1, slot-sharma-avail-2)
        slot_match = re.search(r"\b(slot-[A-Za-z0-9_-]+)\b", msg, re.IGNORECASE)
        if slot_match:
            new_slot_id = slot_match.group(1)
            if draft.slot_id != new_slot_id:
                draft.slot_id = new_slot_id
                draft.slot_start_time = None

        # 4. Detect Reason mentions
        extracted_reason = self._extract_reason(msg)
        if extracted_reason:
            draft.reason_category = extracted_reason

        # 5. Check if confirmation is pending and user explicitly confirms
        is_confirm = is_affirmative(msg)
        if (
            session_state.confirmation_status in [ConfirmationStatus.PENDING, ConfirmationStatus.CONFIRMED]
            and is_confirm
            and draft.is_complete()
        ):
            return AgentAction(
                reply="Thank you for confirming. Processing your appointment booking now...",
                tool_call=ToolCallIntent(
                    tool_name="book_appointment",
                    arguments={
                        "patient_reference": draft.patient_reference,
                        "doctor_id": draft.doctor_id,
                        "selected_slot_id": draft.slot_id,
                        "reason_category": draft.reason_category,
                    },
                ),
            )

        # 6. Detect Doctor search / selection intent
        doc_search_term = self._detect_doctor_query(lower)
        if doc_search_term and not draft.doctor_id:
            return AgentAction(
                reply=f"Searching for Dr. {doc_search_term}...",
                tool_call=ToolCallIntent(
                    tool_name="search_doctors",
                    arguments={"specialty_or_department": doc_search_term},
                ),
            )

        # 7. Detect Specialty query
        detected_specialty = self._detect_specialty(lower)
        if detected_specialty and not draft.doctor_id:
            draft.specialty = detected_specialty
            return AgentAction(
                reply=f"Searching for available specialists in {draft.specialty}...",
                tool_call=ToolCallIntent(
                    tool_name="search_doctors",
                    arguments={"specialty_or_department": draft.specialty},
                ),
            )

        # 8. If doctor is selected but slot is missing -> query slots
        if draft.doctor_id and not draft.slot_id:
            time_filter = None
            if "morning" in lower:
                time_filter = "morning"
            elif "afternoon" in lower:
                time_filter = "afternoon"
            elif "evening" in lower:
                time_filter = "evening"

            return AgentAction(
                reply=f"Checking open appointment slots for {draft.doctor_name or 'the doctor'}...",
                tool_call=ToolCallIntent(
                    tool_name="get_available_slots",
                    arguments={"doctor_id": draft.doctor_id, "time_range": time_filter},
                ),
            )

        # 9. If doctor and slot selected, but reason missing -> ask reason
        if draft.doctor_id and draft.slot_id and not draft.reason_category:
            return AgentAction(
                reply=(
                    f"You have selected slot '{draft.slot_id}' with {draft.doctor_name or 'the doctor'}. "
                    "What is the clinical reason or symptoms for this visit? (e.g., 'Routine checkup', 'Chest pain evaluation')"
                )
            )

        # 10. If doctor, slot, reason selected, but patient reference missing -> ask patient reference
        if draft.doctor_id and draft.slot_id and draft.reason_category and not draft.patient_reference:
            return AgentAction(
                reply=(
                    "Almost ready. Please provide your synthetic Patient Reference ID "
                    "(e.g., 'PAT-2026-4409' or 'PAT-1234') to prepare the booking."
                )
            )

        # 11. All 4 details present -> Present explicit confirmation summary
        if draft.is_complete():
            summary = (
                f"Please verify and confirm your appointment details:\n"
                f"• Patient Reference: {draft.patient_reference}\n"
                f"• Doctor: {draft.doctor_name or 'Specialist'} ({draft.specialty or 'OPD'})\n"
                f"• Slot: {draft.slot_start_time or draft.slot_id}\n"
                f"• Reason: {draft.reason_category}\n\n"
                f"To confirm this booking, please reply 'YES' or 'CONFIRM'. Reply 'NO' to cancel or change details."
            )
            return AgentAction(reply=summary)

        # 12. Default Greeting if no doctor or specialty identified yet
        return AgentAction(
            reply=(
                "Hello! I am the MediVoice Hospital Assistant for Aarogya One Hospital. "
                "Which specialty or physician do you need consultation for? "
                "(e.g., Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine)"
            )
        )

    def _detect_doctor_query(self, text: str) -> Optional[str]:
        for entry in self.DOCTOR_KEYWORDS:
            for kw in entry["keywords"]:
                if re.search(rf"\b{re.escape(kw)}\b", text):
                    return entry["search_term"]
        return None

    def _detect_specialty(self, text: str) -> Optional[str]:
        for spec, keywords in self.SPECIALTY_KEYWORDS.items():
            for kw in keywords:
                if re.search(rf"\b{re.escape(kw)}\b", text):
                    return spec
        return None

    def _extract_reason(self, text: str) -> Optional[str]:
        m = re.search(r"reason:\s*([^,.\n]+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m2 = re.search(
            r"for\s+(intermittent\s+palpitations|chest pain|angina|routine checkup|evaluation|migraine|consultation|knee pain|palpitations|follow-?up)[^,.\n]*",
            text,
            re.IGNORECASE,
        )
        if m2:
            return m2.group(0).strip()
        return None
