import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, List
from sqlalchemy.orm import Session

from app.agent.schemas import (
    AgentAction,
    AgentSessionState,
    BookingDraft,
    ChatMessage,
    ChatResponse,
    ConversationStep,
    ConfirmationStatus,
    ToolCallIntent,
)
from app.agent.adapters import BaseReasoningAdapter, MockReasoningAdapter, is_cancellation, is_affirmative
from app.agent.tool_router import RestrictedToolRouter
from app.services.doctor_service import get_available_slots_tool


class ConversationManager:
    """
    Stateful multi-turn conversation manager for MediVoice AI text agent.
    
    Responsibilities:
    - Maintains conversation sessions and multi-turn context in an in-memory store.
    - Proactively prompts for missing booking details (doctor, slot, reason, patient reference).
    - Enforces explicit patient confirmation tied to the exact draft fingerprint before booking.
    - Invalidates previous confirmations if any booking parameter changes.
    - Protects session isolation: patient references and chats are never shared across sessions.
    - Executes allowlisted tools via RestrictedToolRouter with the active DB session.
    - Handles concurrent booking conflicts gracefully without fake success or duplicate appointments.
    
    Architecture Note on Session Store:
    For this MVP, an in-memory dictionary is used for simplicity and test isolation.
    Limitations: Not persistent across server restarts, not shared across multi-process workers.
    Production systems should back this with Redis or a persistent session store.
    """

    def __init__(
        self,
        tool_router: Optional[RestrictedToolRouter] = None,
        adapter: Optional[BaseReasoningAdapter] = None,
    ):
        self.tool_router = tool_router or RestrictedToolRouter()
        self.adapter = adapter or MockReasoningAdapter()
        self._sessions: Dict[str, AgentSessionState] = {}

    def get_or_create_session(
        self, session_id: Optional[str] = None, initial_patient_ref: Optional[str] = None
    ) -> AgentSessionState:
        """Retrieves an existing session or creates a fresh, isolated conversation session."""
        if not session_id:
            session_id = str(uuid.uuid4())

        if session_id not in self._sessions:
            draft = BookingDraft()
            if initial_patient_ref:
                draft.patient_reference = initial_patient_ref.strip()
            self._sessions[session_id] = AgentSessionState(
                session_id=session_id,
                draft=draft,
            )
        return self._sessions[session_id]

    def reset_session(self, session_id: str) -> bool:
        """Clears session state and history."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def process_message(
        self,
        db: Session,
        message: str,
        session_id: Optional[str] = None,
        patient_reference: Optional[str] = None,
    ) -> ChatResponse:
        """
        Processes a patient message in an isolated session:
        1. Updates conversation history and draft parameters.
        2. Validates confirmation status against draft fingerprint.
        3. Executes allowlisted tools when needed.
        4. Enforces the explicit confirmation gate before transactional booking.
        """
        session = self.get_or_create_session(session_id, patient_reference)
        session.last_active_at = datetime.now(timezone.utc).isoformat()

        # Update synthetic patient reference if provided in payload and not yet set
        if patient_reference and not session.draft.patient_reference:
            session.draft.patient_reference = patient_reference.strip()

        # Record user message in history
        user_msg_record = ChatMessage(role="user", content=message)
        session.history.append(user_msg_record)

        # Snapshot initial fingerprint before reasoning
        initial_fingerprint = session.draft.get_fingerprint()

        # Check for cancellation / abort intent first
        if is_cancellation(message):
            session.confirmation_status = ConfirmationStatus.REJECTED
            session.step = ConversationStep.CANCELLED
            reply = "Understood. The appointment booking has been cancelled. Let me know if you would like to explore other doctors or services."
            session.history.append(ChatMessage(role="assistant", content=reply))
            return self._build_response(session, reply)

        # If already booked and user is confirming again, prevent duplicate bookings
        if session.step == ConversationStep.BOOKED:
            if is_affirmative(message):
                appt_id = session.booked_appointment.get("appointment_id", "") if session.booked_appointment else ""
                reply = (
                    f"Your appointment is already confirmed and booked (Appointment ID: {appt_id}). "
                    "If you need to book a new appointment, please reset the session or ask to start over."
                )
                session.history.append(ChatMessage(role="assistant", content=reply))
                return self._build_response(session, reply)

        # Plan action via reasoning adapter
        action: AgentAction = self.adapter.plan_and_respond(
            session_state=session,
            user_message=message,
            available_tools=list(self.tool_router.ALLOWED_TOOLS),
        )

        current_fingerprint = session.draft.get_fingerprint()

        # Requirement 3: If booking parameters changed while confirmation was pending, invalidate confirmation!
        if (
            session.confirmation_status in [ConfirmationStatus.PENDING, ConfirmationStatus.CONFIRMED]
            and initial_fingerprint != current_fingerprint
        ):
            session.confirmation_status = ConfirmationStatus.STALE
            session.confirmed_draft_fingerprint = None
            session.step = ConversationStep.AWAITING_CONFIRMATION

        # Handle tool call if requested by adapter
        final_reply = action.reply
        if action.tool_call:
            tool_name = action.tool_call.tool_name

            # STRICT CONFIRMATION GATE for booking
            if tool_name == "book_appointment":
                if not session.draft.is_complete():
                    missing = session.draft.missing_fields()
                    final_reply = f"Cannot book yet. Missing details: {', '.join(missing)}."
                elif (
                    session.confirmation_status != ConfirmationStatus.PENDING
                    and not is_affirmative(message)
                ):
                    final_reply = (
                        "Explicit confirmation is required before booking. "
                        "Please reply 'YES' to confirm or 'NO' to cancel."
                    )
                elif session.confirmed_draft_fingerprint != current_fingerprint:
                    # Stale or changed draft
                    session.confirmation_status = ConfirmationStatus.PENDING
                    session.confirmed_draft_fingerprint = current_fingerprint
                    final_reply = (
                        "Booking details have changed. Please confirm the updated details:\n"
                        f"• Doctor: {session.draft.doctor_name}\n"
                        f"• Slot: {session.draft.slot_start_time or session.draft.slot_id}\n"
                        f"• Reason: {session.draft.reason_category}\n"
                        f"• Patient Reference: {session.draft.patient_reference}\n\n"
                        "Reply 'YES' to finalize booking."
                    )
                else:
                    # All confirmation criteria satisfied -> Execute transactional booking
                    tool_res = self.tool_router.execute_tool(db, action.tool_call)
                    session.tool_trace.append(tool_res)

                    if tool_res.success:
                        # Transaction succeeded and committed in database
                        session.step = ConversationStep.BOOKED
                        session.confirmation_status = ConfirmationStatus.CONFIRMED
                        session.booked_appointment = tool_res.data
                        final_reply = (
                            f"Appointment Confirmed! 🎉\n"
                            f"• Appointment ID: {tool_res.data.get('appointment_id')}\n"
                            f"• Doctor: {tool_res.data.get('doctor_name')}\n"
                            f"• Schedule: {tool_res.data.get('appointment_start_time')}\n"
                            f"• Status: {tool_res.data.get('appointment_status')}\n"
                            f"• Patient Reference: {tool_res.data.get('patient_reference')}\n\n"
                            f"Your booking has been permanently recorded in Aarogya One Hospital's database."
                        )
                    else:
                        # Slot unavailable, concurrent booking conflict, or validation error
                        session.step = ConversationStep.COLLECTING_SLOT
                        session.draft.slot_id = None
                        session.draft.slot_start_time = None
                        session.confirmation_status = ConfirmationStatus.NONE
                        session.confirmed_draft_fingerprint = None
                        final_reply = (
                            f"Booking could not be completed: {tool_res.error}\n"
                            "The selected slot is unavailable or conflict occurred. "
                            "Please choose a different available slot."
                        )

            elif tool_name == "search_doctors":
                tool_res = self.tool_router.execute_tool(db, action.tool_call)
                session.tool_trace.append(tool_res)
                if tool_res.success and tool_res.data:
                    docs = tool_res.data
                    search_arg = action.tool_call.arguments.get("specialty_or_department", "")

                    is_doctor_specific = (
                        self.adapter._detect_doctor_query(message.lower()) is not None  # type: ignore
                    ) and len(docs) > 0

                    if is_doctor_specific and docs:
                        chosen_doc = docs[0]
                        session.draft.doctor_id = chosen_doc["doctor_id"]
                        session.draft.doctor_name = chosen_doc["display_name"]
                        session.draft.specialty = chosen_doc["specialty"]

                        # Chain to get_available_slots for this doctor
                        slot_intent = ToolCallIntent(
                            tool_name="get_available_slots",
                            arguments={"doctor_id": chosen_doc["doctor_id"]},
                        )
                        slot_res = self.tool_router.execute_tool(db, slot_intent)
                        session.tool_trace.append(slot_res)

                        if slot_res.success and slot_res.data:
                            slots = slot_res.data
                            slot_lines = [f"• Slot ID: {s['slot_id']} | Start: {s['start_time']}" for s in slots[:5]]
                            final_reply = (
                                f"Selected {chosen_doc['display_name']} ({chosen_doc['specialty']}).\n"
                                f"Available open slots:\n"
                                + "\n".join(slot_lines)
                                + f"\n\nPlease specify which slot ID you prefer (e.g., 'I want {slots[0]['slot_id']}')."
                            )
                        else:
                            final_reply = (
                                f"No available slots currently found for {chosen_doc['display_name']}. "
                                "Would you like to check another doctor or date?"
                            )
                        session.step = ConversationStep.COLLECTING_SLOT
                    else:
                        doc_list_str = "\n".join(
                            [f"• {d['display_name']} — {d['specialty']} ({d['department_name']})" for d in docs]
                        )
                        final_reply = (
                            f"I found {len(docs)} specialist(s) available at Aarogya One Hospital:\n{doc_list_str}\n\n"
                            f"Which doctor would you like to schedule an appointment with?"
                        )
                        session.step = ConversationStep.COLLECTING_DOCTOR
                else:
                    final_reply = "No matching doctors found for that query. Would you like to check general medicine or another department?"

            elif tool_name == "get_available_slots":
                tool_res = self.tool_router.execute_tool(db, action.tool_call)
                session.tool_trace.append(tool_res)
                if tool_res.success and tool_res.data:
                    slots = tool_res.data
                    if slots and not session.draft.doctor_name:
                        session.draft.doctor_name = slots[0].get("doctor_name")
                        session.draft.specialty = slots[0].get("specialty")

                    slot_lines = [f"• Slot ID: {s['slot_id']} | Start: {s['start_time']}" for s in slots[:5]]
                    final_reply = (
                        f"Available open slots for {session.draft.doctor_name or 'the doctor'}:\n"
                        + "\n".join(slot_lines)
                        + "\n\nPlease specify which slot ID you prefer (e.g., 'I want "
                        + slots[0]["slot_id"]
                        + "')."
                    )
                    session.step = ConversationStep.COLLECTING_SLOT
                else:
                    final_reply = (
                        f"No available slots currently found for {session.draft.doctor_name or 'the selected doctor'}. "
                        "Would you like to check another doctor or date?"
                    )

        # Update dialogue step based on completeness if not booked or cancelled
        if session.step not in [ConversationStep.BOOKED, ConversationStep.CANCELLED]:
            if session.draft.is_complete():
                session.step = ConversationStep.AWAITING_CONFIRMATION
                session.confirmation_status = ConfirmationStatus.PENDING
                session.confirmed_draft_fingerprint = session.draft.get_fingerprint()
            elif not session.draft.doctor_id:
                session.step = ConversationStep.COLLECTING_DOCTOR
            elif not session.draft.slot_id:
                session.step = ConversationStep.COLLECTING_SLOT
            else:
                session.step = ConversationStep.COLLECTING_DETAILS

        # Record assistant reply in history
        session.history.append(ChatMessage(role="assistant", content=final_reply))
        return self._build_response(session, final_reply)

    def _build_response(self, session: AgentSessionState, reply: str) -> ChatResponse:
        return ChatResponse(
            session_id=session.session_id,
            reply=reply,
            step=session.step,
            draft=session.draft,
            missing_details=session.draft.missing_fields(),
            confirmation_status=session.confirmation_status,
            tool_trace=session.tool_trace,
            booked_appointment=session.booked_appointment,
        )


# Global singleton instance for application use
conversation_manager = ConversationManager()
