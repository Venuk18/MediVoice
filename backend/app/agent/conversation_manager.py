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
    ToolExecutionResult,
)
from app.agent.adapters import (
    BaseReasoningAdapter,
    MockReasoningAdapter,
    GeminiReasoningAdapter,
    create_reasoning_adapter,
    detect_emergency_priority_kind,
    detect_language,
    ensure_response_in_session_language,
    format_insurance_search_reply,
    format_lab_verification_reply,
    format_localized_message,
    format_slot_display,
    is_cancellation,
    is_affirmative,
    is_insurance_inquiry,
    is_lab_report_inquiry,
    resolve_ordinal_doctor_selection,
    with_urgent_guidance_if_needed,
)
from app.agent.tool_router import RestrictedToolRouter


class ConversationManager:
    """
    Stateful multi-turn conversation manager for MediVoice AI text agent.
    
    Responsibilities:
    - Maintains conversation sessions, language preference, and multi-turn context in an in-memory store.
    - Proactively prompts for missing booking details (doctor, slot, reason, patient reference).
    - Enforces explicit patient confirmation tied to the exact draft fingerprint before booking.
    - Invalidates previous confirmations if any booking parameter changes.
    - Protects session isolation: patient references and chats are never shared across sessions.
    - Executes allowlisted tools via RestrictedToolRouter with the active DB session.
    - Handles concurrent booking conflicts gracefully without fake success or duplicate appointments.
    """

    def __init__(
        self,
        tool_router: Optional[RestrictedToolRouter] = None,
        adapter: Optional[BaseReasoningAdapter] = None,
    ):
        self.tool_router = tool_router or RestrictedToolRouter()
        self.adapter = adapter or create_reasoning_adapter()
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

    def _hydrate_doctor_from_trace_or_db(self, db: Session, session: AgentSessionState, message: str) -> None:
        """
        If user selects a doctor (by name or ordinal reference like 'first doctor') that was
        previously listed in search_doctors tool_trace, populate or update doctor fields.
        """
        ordinal_doc = resolve_ordinal_doctor_selection(message, session)
        if ordinal_doc:
            if session.draft.doctor_id != ordinal_doc["doctor_id"]:
                session.draft.doctor_id = ordinal_doc["doctor_id"]
                session.draft.doctor_name = ordinal_doc.get("display_name")
                session.draft.specialty = ordinal_doc.get("specialty")
                session.draft.slot_id = None
                session.draft.slot_start_time = None
            return

        doc_query = self.adapter._detect_doctor_query(message)
        if not doc_query:
            return

        # If already selected this exact doctor, keep current state
        if session.draft.doctor_id and session.draft.doctor_name and doc_query.lower() in session.draft.doctor_name.lower():
            return

        # Check if doctor was already found in previous search_doctors tool_trace
        for tr in reversed(session.tool_trace):
            if tr.tool_name == "search_doctors" and tr.success and isinstance(tr.data, list):
                for d in tr.data:
                    if doc_query.lower() in str(d.get("display_name", "")).lower():
                        if session.draft.doctor_id != d["doctor_id"]:
                            session.draft.doctor_id = d["doctor_id"]
                            session.draft.doctor_name = d["display_name"]
                            session.draft.specialty = d["specialty"]
                            session.draft.slot_id = None
                            session.draft.slot_start_time = None
                        return

    def _hydrate_slot_from_trace(self, session: AgentSessionState) -> None:
        """Populates slot_start_time if slot_id matches a slot returned in tool_trace."""
        if not session.draft.slot_id:
            return
        for tr in reversed(session.tool_trace):
            if tr.tool_name == "get_available_slots" and tr.success and isinstance(tr.data, list):
                for s in tr.data:
                    if s.get("slot_id") == session.draft.slot_id:
                        session.draft.slot_start_time = s.get("start_time")
                        if not session.draft.doctor_name and s.get("doctor_name"):
                            session.draft.doctor_name = s.get("doctor_name")
                        if not session.draft.specialty and s.get("specialty"):
                            session.draft.specialty = s.get("specialty")
                        return

    def process_message(
        self,
        db: Session,
        message: str,
        session_id: Optional[str] = None,
        patient_reference: Optional[str] = None,
    ) -> ChatResponse:
        """
        Processes a patient message in an isolated session:
        1. Updates conversation history, language, and draft parameters.
        2. Validates confirmation status against draft fingerprint.
        3. Executes allowlisted tools when needed.
        4. Enforces the explicit confirmation gate before transactional booking.
        """
        session = self.get_or_create_session(session_id, patient_reference)
        session.last_active_at = datetime.now(timezone.utc).isoformat()
        session.language = detect_language(message, session.language)
        lang = session.language

        # Update synthetic patient reference if provided in payload and not yet set
        if patient_reference and not session.draft.patient_reference:
            session.draft.patient_reference = patient_reference.strip()

        # Record user message in history
        user_msg_record = ChatMessage(role="user", content=message)
        session.history.append(user_msg_record)

        # Snapshot initial state before reasoning
        initial_fingerprint = session.draft.get_fingerprint()
        initial_confirmation_status = session.confirmation_status
        initial_confirmed_fingerprint = session.confirmed_draft_fingerprint

        # Check for cancellation / abort intent first
        if is_cancellation(message):
            session.confirmation_status = ConfirmationStatus.REJECTED
            session.step = ConversationStep.CANCELLED
            session.pending_action = None
            session.pending_action_data = {}
            reply = format_localized_message(lang, "cancelled")
            session.history.append(ChatMessage(role="assistant", content=reply))
            return self._build_response(session, reply)

        # If session was previously cancelled and user sends a new non-cancellation message, reopen session cleanly
        if session.step == ConversationStep.CANCELLED:
            preserved_pat_ref = session.draft.patient_reference
            session.draft = BookingDraft(patient_reference=preserved_pat_ref)
            session.confirmation_status = ConfirmationStatus.NONE
            session.confirmed_draft_fingerprint = None
            session.pending_action = None
            session.pending_action_data = {}
            session.step = ConversationStep.COLLECTING_DOCTOR

        # If already booked and user is confirming again, prevent duplicate bookings
        if session.step == ConversationStep.BOOKED:
            if is_affirmative(message):
                appt_id = session.booked_appointment.get("appointment_id", "") if session.booked_appointment else ""
                reply = format_localized_message(lang, "already_booked", appt_id=appt_id)
                session.history.append(ChatMessage(role="assistant", content=reply))
                return self._build_response(session, reply)

        emergency_kind = detect_emergency_priority_kind(message, session)

        # Pre-populate doctor from prior search trace if user selected one by name or ordinal (skip during emergency priority)
        if not emergency_kind:
            self._hydrate_doctor_from_trace_or_db(db, session, message)

        booking_attempted_in_turn = False
        booking_gate_blocked_reason: Optional[str] = None
        last_booking_result: Optional[ToolExecutionResult] = None
        tools_executed_in_callback: List[str] = []
        is_non_booking_info_turn = False

        def execute_tool_from_adapter(intent: ToolCallIntent) -> ToolExecutionResult:
            nonlocal booking_attempted_in_turn, booking_gate_blocked_reason, last_booking_result, is_non_booking_info_turn
            t_name = intent.tool_name.strip()
            tools_executed_in_callback.append(t_name)
            if t_name in ("check_lab_report_status", "search_hospital_insurance"):
                is_non_booking_info_turn = True

            if t_name == "book_appointment":
                booking_attempted_in_turn = True
                curr_fp = session.draft.get_fingerprint()

                if not session.draft.is_complete():
                    missing = session.draft.missing_fields()
                    booking_gate_blocked_reason = format_localized_message(
                        lang, "missing_details_error", missing=", ".join(missing)
                    )
                    return ToolExecutionResult(
                        tool_name="book_appointment",
                        success=False,
                        error=booking_gate_blocked_reason,
                    )

                if initial_fingerprint != curr_fp or initial_confirmed_fingerprint != curr_fp:
                    session.confirmation_status = ConfirmationStatus.PENDING
                    session.confirmed_draft_fingerprint = curr_fp
                    session.step = ConversationStep.AWAITING_CONFIRMATION
                    booking_gate_blocked_reason = with_urgent_guidance_if_needed(
                        lang,
                        format_localized_message(
                            lang,
                            "changed_reconfirm",
                            doctor_name=session.draft.doctor_name or "Specialist",
                            slot_display=format_slot_display(session.draft.slot_id, session.draft.slot_start_time),
                            reason_category=session.draft.reason_category,
                            patient_reference=session.draft.patient_reference,
                        ),
                        message,
                        session.draft.reason_category,
                    )
                    return ToolExecutionResult(
                        tool_name="book_appointment",
                        success=False,
                        error="Confirmation invalidated because booking parameters changed. Explicit confirmation required.",
                    )

                if initial_confirmation_status != ConfirmationStatus.PENDING or not is_affirmative(message):
                    booking_gate_blocked_reason = format_localized_message(lang, "explicit_confirm_required")
                    return ToolExecutionResult(
                        tool_name="book_appointment",
                        success=False,
                        error=booking_gate_blocked_reason,
                    )

                # Confirmed and validated -> execute via RestrictedToolRouter using verified draft fields
                verified_intent = ToolCallIntent(
                    tool_name="book_appointment",
                    arguments={
                        "patient_reference": session.draft.patient_reference,
                        "doctor_id": session.draft.doctor_id,
                        "selected_slot_id": session.draft.slot_id,
                        "reason_category": session.draft.reason_category,
                    },
                )
                tool_res = self.tool_router.execute_tool(db, verified_intent)
                session.tool_trace.append(tool_res)
                last_booking_result = tool_res

                if tool_res.success:
                    session.step = ConversationStep.BOOKED
                    session.confirmation_status = ConfirmationStatus.CONFIRMED
                    session.booked_appointment = tool_res.data
                else:
                    session.step = ConversationStep.COLLECTING_SLOT
                    session.draft.slot_id = None
                    session.draft.slot_start_time = None
                    session.confirmation_status = ConfirmationStatus.NONE
                    session.confirmed_draft_fingerprint = None

                return tool_res

            # Non-booking tools (search_doctors, get_available_slots, or rejected unauthorized tools)
            tool_res = self.tool_router.execute_tool(db, intent)
            session.tool_trace.append(tool_res)

            if t_name == "search_doctors" and tool_res.success and tool_res.data:
                docs = tool_res.data
                is_doc_specific = self.adapter._detect_doctor_query(message) is not None and len(docs) > 0
                if is_doc_specific:
                    chosen_doc = docs[0]
                    session.draft.doctor_id = chosen_doc["doctor_id"]
                    session.draft.doctor_name = chosen_doc["display_name"]
                    session.draft.specialty = chosen_doc["specialty"]
                    session.pending_action = None
                    session.pending_action_data = {}
                else:
                    if not session.draft.specialty and docs:
                        session.draft.specialty = docs[0].get("specialty")
                    if docs:
                        session.pending_action = "SHOW_SLOTS_FOR_DOCTOR"
                        session.pending_action_data = {
                            "doctor_id": docs[0].get("doctor_id"),
                            "doctor_name": docs[0].get("display_name"),
                            "specialty": docs[0].get("specialty"),
                        }

            elif t_name == "get_available_slots" and tool_res.success and tool_res.data:
                slots = tool_res.data
                session.pending_action = None
                session.pending_action_data = {}
                if slots:
                    if not session.draft.doctor_id:
                        session.draft.doctor_id = slots[0].get("doctor_id")
                    if not session.draft.doctor_name:
                        session.draft.doctor_name = slots[0].get("doctor_name")
                    if not session.draft.specialty:
                        session.draft.specialty = slots[0].get("specialty")

            return tool_res

        # Plan action via reasoning adapter
        # Pass tool_executor when using GeminiReasoningAdapter so multi-round tool calls execute within the turn
        use_multi_round_callback = isinstance(self.adapter, GeminiReasoningAdapter)
        action: AgentAction = self.adapter.plan_and_respond(
            session_state=session,
            user_message=message,
            available_tools=list(self.tool_router.ALLOWED_TOOLS),
            tool_executor=execute_tool_from_adapter if use_multi_round_callback else None,
        )

        self._hydrate_slot_from_trace(session)
        current_fingerprint = session.draft.get_fingerprint()

        # Requirement: If booking parameters changed while confirmation was pending, invalidate confirmation!
        if (
            initial_confirmation_status in [ConfirmationStatus.PENDING, ConfirmationStatus.CONFIRMED]
            and initial_fingerprint != current_fingerprint
        ):
            session.confirmation_status = ConfirmationStatus.STALE
            session.confirmed_draft_fingerprint = None
            session.step = ConversationStep.AWAITING_CONFIRMATION

        final_reply = action.reply

        # If a Gemini turn received an explicit affirmative confirmation on an unchanged pending complete draft
        # and the model replied without invoking book_appointment yet, trigger the booking gate now
        if (
            use_multi_round_callback
            and not booking_attempted_in_turn
            and action.tool_call is None
            and initial_confirmation_status == ConfirmationStatus.PENDING
            and initial_confirmed_fingerprint == current_fingerprint
            and initial_fingerprint == current_fingerprint
            and session.draft.is_complete()
            and is_affirmative(message)
        ):
            action.tool_call = ToolCallIntent(
                tool_name="book_appointment",
                arguments={
                    "patient_reference": session.draft.patient_reference,
                    "doctor_id": session.draft.doctor_id,
                    "selected_slot_id": session.draft.slot_id,
                    "reason_category": session.draft.reason_category,
                },
            )

        # If Gemini searched for a specific doctor and found 1 match but didn't chain get_available_slots yet
        if (
            use_multi_round_callback
            and "search_doctors" in tools_executed_in_callback
            and "get_available_slots" not in tools_executed_in_callback
            and session.draft.doctor_id
            and not session.draft.slot_id
        ):
            slot_intent = ToolCallIntent(
                tool_name="get_available_slots",
                arguments={"doctor_id": session.draft.doctor_id},
            )
            slot_res = self.tool_router.execute_tool(db, slot_intent)
            session.tool_trace.append(slot_res)
            if slot_res.success and slot_res.data:
                slots = slot_res.data
                slot_lines = "\n".join([f"• Slot ID: {s['slot_id']} | Start: {s['start_time']}" for s in slots[:5]])
                final_reply = format_localized_message(
                    lang,
                    "selected_doctor_slots",
                    doctor_name=session.draft.doctor_name or "Doctor",
                    specialty=session.draft.specialty or "Specialist",
                    slot_lines=slot_lines,
                    example_slot=slots[0]["slot_id"],
                )
                session.step = ConversationStep.COLLECTING_SLOT

        # Handle outcomes when booking was attempted inside multi-round callback
        if booking_attempted_in_turn:
            if booking_gate_blocked_reason:
                final_reply = booking_gate_blocked_reason
            elif last_booking_result is not None:
                if last_booking_result.success and last_booking_result.data:
                    d_res = last_booking_result.data
                    # Ensure the reply clearly contains the committed appointment details
                    if str(d_res.get("appointment_id", "")) not in final_reply:
                        final_reply = format_localized_message(
                            lang,
                            "booking_confirmed",
                            appointment_id=d_res.get("appointment_id"),
                            doctor_name=d_res.get("doctor_name"),
                            appointment_start_time=d_res.get("appointment_start_time"),
                            appointment_status=d_res.get("appointment_status"),
                            patient_reference=d_res.get("patient_reference"),
                        )
                else:
                    final_reply = format_localized_message(
                        lang,
                        "booking_failed",
                        error=last_booking_result.error or "Slot conflict",
                    )

        # Handle single-step tool call if returned by adapter (MockReasoningAdapter or direct action.tool_call)
        if action.tool_call and not booking_attempted_in_turn:
            tool_name = action.tool_call.tool_name

            # STRICT CONFIRMATION GATE for booking
            if tool_name == "book_appointment":
                if not session.draft.is_complete():
                    missing = session.draft.missing_fields()
                    final_reply = format_localized_message(
                        lang, "missing_details_error", missing=", ".join(missing)
                    )
                elif (
                    session.confirmation_status != ConfirmationStatus.PENDING
                    or not is_affirmative(message)
                ):
                    final_reply = format_localized_message(lang, "explicit_confirm_required")
                elif session.confirmed_draft_fingerprint != current_fingerprint or initial_fingerprint != current_fingerprint:
                    # Stale or changed draft
                    session.confirmation_status = ConfirmationStatus.PENDING
                    session.confirmed_draft_fingerprint = current_fingerprint
                    final_reply = with_urgent_guidance_if_needed(
                        lang,
                        format_localized_message(
                            lang,
                            "changed_reconfirm",
                            doctor_name=session.draft.doctor_name,
                            slot_display=format_slot_display(session.draft.slot_id, session.draft.slot_start_time),
                            reason_category=session.draft.reason_category,
                            patient_reference=session.draft.patient_reference,
                        ),
                        message,
                        session.draft.reason_category,
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
                        session.pending_action = None
                        session.pending_action_data = {}
                        final_reply = format_localized_message(
                            lang,
                            "booking_confirmed",
                            appointment_id=tool_res.data.get("appointment_id"),
                            doctor_name=tool_res.data.get("doctor_name"),
                            appointment_start_time=tool_res.data.get("appointment_start_time"),
                            appointment_status=tool_res.data.get("appointment_status"),
                            patient_reference=tool_res.data.get("patient_reference"),
                        )
                    else:
                        # Slot unavailable, concurrent booking conflict, or validation error
                        session.step = ConversationStep.COLLECTING_SLOT
                        session.draft.slot_id = None
                        session.draft.slot_start_time = None
                        session.confirmation_status = ConfirmationStatus.NONE
                        session.confirmed_draft_fingerprint = None
                        final_reply = format_localized_message(
                            lang,
                            "booking_failed",
                            error=tool_res.error,
                        )

            elif tool_name == "search_doctors":
                tool_res = self.tool_router.execute_tool(db, action.tool_call)
                session.tool_trace.append(tool_res)
                if tool_res.success and tool_res.data:
                    docs = tool_res.data
                    is_doctor_specific = (
                        self.adapter._detect_doctor_query(message) is not None
                    ) and len(docs) > 0

                    if is_doctor_specific and docs:
                        chosen_doc = docs[0]
                        session.draft.doctor_id = chosen_doc["doctor_id"]
                        session.draft.doctor_name = chosen_doc["display_name"]
                        session.draft.specialty = chosen_doc["specialty"]
                        session.pending_action = None
                        session.pending_action_data = {}

                        # Chain to get_available_slots for this doctor
                        slot_intent = ToolCallIntent(
                            tool_name="get_available_slots",
                            arguments={"doctor_id": chosen_doc["doctor_id"]},
                        )
                        slot_res = self.tool_router.execute_tool(db, slot_intent)
                        session.tool_trace.append(slot_res)

                        if slot_res.success and slot_res.data:
                            slots = slot_res.data
                            slot_lines = "\n".join(
                                [f"• Slot ID: {s['slot_id']} | Start: {s['start_time']}" for s in slots[:5]]
                            )
                            final_reply = format_localized_message(
                                lang,
                                "selected_doctor_slots",
                                doctor_name=chosen_doc["display_name"],
                                specialty=chosen_doc["specialty"],
                                slot_lines=slot_lines,
                                example_slot=slots[0]["slot_id"],
                            )
                        else:
                            final_reply = format_localized_message(
                                lang,
                                "no_slots",
                                doctor_name=chosen_doc["display_name"],
                            )
                        session.step = ConversationStep.COLLECTING_SLOT
                    else:
                        if not session.draft.specialty and docs:
                            session.draft.specialty = docs[0].get("specialty")
                        if docs:
                            session.pending_action = "SHOW_SLOTS_FOR_DOCTOR"
                            session.pending_action_data = {
                                "doctor_id": docs[0].get("doctor_id"),
                                "doctor_name": docs[0].get("display_name"),
                                "specialty": docs[0].get("specialty"),
                            }
                        doc_list_str = "\n".join(
                            [f"• {d['display_name']} — {d['specialty']} ({d['department_name']})" for d in docs]
                        )
                        final_reply = format_localized_message(
                            lang,
                            "found_doctors",
                            count=len(docs),
                            doc_list=doc_list_str,
                        )
                        session.step = ConversationStep.COLLECTING_DOCTOR
                else:
                    final_reply = format_localized_message(lang, "no_doctors")

            elif tool_name == "get_available_slots":
                tool_res = self.tool_router.execute_tool(db, action.tool_call)
                session.tool_trace.append(tool_res)
                session.pending_action = None
                session.pending_action_data = {}
                if tool_res.success and tool_res.data:
                    slots = tool_res.data
                    if slots and not session.draft.doctor_name:
                        session.draft.doctor_name = slots[0].get("doctor_name")
                        session.draft.specialty = slots[0].get("specialty")

                    slot_lines = "\n".join(
                        [f"• Slot ID: {s['slot_id']} | Start: {s['start_time']}" for s in slots[:5]]
                    )
                    final_reply = format_localized_message(
                        lang,
                        "available_slots",
                        doctor_name=session.draft.doctor_name or "the doctor",
                        slot_lines=slot_lines,
                        example_slot=slots[0]["slot_id"],
                    )
                    session.step = ConversationStep.COLLECTING_SLOT
                else:
                    final_reply = format_localized_message(
                        lang,
                        "no_slots",
                        doctor_name=session.draft.doctor_name or "the selected doctor",
                    )

            elif tool_name == "check_lab_report_status":
                is_non_booking_info_turn = True
                tool_res = self.tool_router.execute_tool(db, action.tool_call)
                session.tool_trace.append(tool_res)
                if tool_res.success and isinstance(tool_res.data, dict):
                    if tool_res.data.get("verified"):
                        session.pending_action = None
                        session.pending_action_data = {}
                    else:
                        session.pending_action = "AWAITING_LAB_VERIFICATION_CODE"
                    final_reply = format_lab_verification_reply(lang, tool_res.data)
                else:
                    session.pending_action = "AWAITING_LAB_VERIFICATION_CODE"
                    final_reply = format_lab_verification_reply(
                        lang,
                        {"verified": False, "error_code": "INVALID_OR_EXPIRED_CODE"},
                    )

            elif tool_name == "search_hospital_insurance":
                is_non_booking_info_turn = True
                tool_res = self.tool_router.execute_tool(db, action.tool_call)
                session.tool_trace.append(tool_res)
                if tool_res.success and isinstance(tool_res.data, dict):
                    final_reply = format_insurance_search_reply(lang, tool_res.data)
                else:
                    final_reply = format_insurance_search_reply(
                        lang,
                        {"providers": [], "matched_count": 0},
                    )

        if session.pending_action == "AWAITING_LAB_VERIFICATION_CODE":
            is_non_booking_info_turn = True

        # Update dialogue step based on completeness if not booked, cancelled, emergency priority, or non-booking info turn
        if emergency_kind or is_non_booking_info_turn:
            final_reply = ensure_response_in_session_language(final_reply, session, message)
        elif session.step not in [ConversationStep.BOOKED, ConversationStep.CANCELLED]:
            if session.draft.is_complete():
                session.step = ConversationStep.AWAITING_CONFIRMATION
                session.confirmation_status = ConfirmationStatus.PENDING
                session.confirmed_draft_fingerprint = session.draft.get_fingerprint()
                # Ensure confirmation summary contains the current slot_id and patient_reference
                if (
                    session.draft.slot_id
                    and session.draft.slot_id not in final_reply
                    and (session.draft.slot_start_time or "") not in final_reply
                ):
                    final_reply = format_localized_message(
                        lang,
                        "confirm_summary",
                        patient_reference=session.draft.patient_reference,
                        doctor_name=session.draft.doctor_name or "Specialist",
                        specialty=session.draft.specialty or "OPD",
                        slot_display=format_slot_display(session.draft.slot_id, session.draft.slot_start_time),
                        reason_category=session.draft.reason_category,
                    )
                final_reply = with_urgent_guidance_if_needed(
                    lang,
                    final_reply,
                    message,
                    session.draft.reason_category,
                )
            elif not session.draft.doctor_id:
                session.step = ConversationStep.COLLECTING_DOCTOR
                final_reply = with_urgent_guidance_if_needed(lang, final_reply, message)
            elif not session.draft.slot_id:
                session.step = ConversationStep.COLLECTING_SLOT
                final_reply = with_urgent_guidance_if_needed(lang, final_reply, message)
            else:
                session.step = ConversationStep.COLLECTING_DETAILS
                final_reply = with_urgent_guidance_if_needed(
                    lang, final_reply, message, session.draft.reason_category
                )

        final_reply = ensure_response_in_session_language(final_reply, session, message)

        # Record assistant reply in history
        session.history.append(ChatMessage(role="assistant", content=final_reply))
        return self._build_response(session, final_reply)

    def _build_response(self, session: AgentSessionState, reply: str) -> ChatResponse:
        return ChatResponse(
            session_id=session.session_id,
            reply=reply,
            language=session.language,
            step=session.step,
            draft=session.draft,
            missing_details=session.draft.missing_fields(),
            confirmation_status=session.confirmation_status,
            tool_trace=session.tool_trace,
            booked_appointment=session.booked_appointment,
        )


# Global singleton instance for application use
conversation_manager = ConversationManager()
