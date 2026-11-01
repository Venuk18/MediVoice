import html
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, List
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

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
    ReasoningAdapterError,
    extract_explicit_doctor_name,
    deduplicate_doctors,
    is_ambiguous_account_or_booking_inquiry,
    BaseReasoningAdapter,
    MockReasoningAdapter,
    GeminiReasoningAdapter,
    build_localized_prompt_for_current_state,
    create_reasoning_adapter,
    detect_emergency_priority_kind,
    detect_language,
    ensure_response_in_session_language,
    has_expected_language_script,
    format_insurance_search_reply,
    format_lab_verification_reply,
    format_localized_message,
    format_slot_display,
    get_specialist_plural,
    format_human_slot_time,
    sanitize_patient_facing_text,
    is_cancellation,
    is_explicit_cancellation,
    is_first_time_patient_reply,
    is_existing_patient_reply,
    is_gratitude_or_closing,
    is_contextual_affirmative,
    extract_patient_name_candidate,
    extract_phone_number_candidate,
    get_offered_doctors_from_session,
    get_offered_slots_from_session,
    is_affirmative,
    is_flexible_slot_request,
    is_insurance_inquiry,
    is_lab_report_inquiry,
    resolve_ordinal_doctor_selection,
    with_urgent_guidance_if_needed,
)
from app.agent.tool_router import RestrictedToolRouter
from app.services.doctor_service import search_doctors_tool


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
        self._voice_selected_languages: Dict[str, str] = {}

    def get_or_create_session(
        self, session_id: Optional[str] = None, initial_patient_ref: Optional[str] = None
    ) -> AgentSessionState:
        """Retrieves an existing session or creates a fresh, isolated conversation session."""
        if not session_id:
            session_id = str(uuid.uuid4())

        if session_id not in self._sessions:
            self._voice_selected_languages.pop(session_id, None)
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
        self._voice_selected_languages.pop(session_id, None)
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def resolve_voice_language_base(self, session_id: str, selected_language: Optional[str], current_language: str) -> str:
        """Apply a changed UI language selection once; otherwise preserve conversation language."""
        selected = (selected_language or "").split("-")[0].lower()
        if selected not in ("en", "te", "hi", "ta", "kn"):
            return current_language
        previous_selected = self._voice_selected_languages.get(session_id)
        self._voice_selected_languages[session_id] = selected
        return selected if previous_selected != selected else current_language

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
                for d in deduplicate_doctors(tr.data):
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
        t_start = time.perf_counter()
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

        normalized_confirmation_ack = re.sub(r"[.!?,;]+", "", message.strip().lower())
        ambiguous_confirmation_acks = {"ok", "okay", "sure", "alright", "సరే", "అలాగే", "சரி", "ಸರಿ", "ठीक है"}
        if session.confirmation_status == ConfirmationStatus.PENDING and normalized_confirmation_ack in ambiguous_confirmation_acks:
            clarification_by_language = {
                "en": "Would you like me to book this appointment? Please say yes to confirm, or tell me what you would like to change.",
                "te": "ఈ అపాయింట్‌మెంట్‌ను బుక్ చేయమంటారా? నిర్ధారించడానికి ‘అవును’ అని చెప్పండి, లేదా మార్చాల్సిన వివరాన్ని చెప్పండి.",
                "hi": "क्या मैं यह अपॉइंटमेंट बुक करूँ? पुष्टि के लिए ‘हाँ’ कहें, या बताएं कि क्या बदलना है।",
                "ta": "இந்த அப்பாயிண்ட்மென்ட்டை பதிவு செய்யவா? உறுதிப்படுத்த ‘ஆம்’ என்று சொல்லுங்கள் அல்லது மாற்ற வேண்டியதைச் சொல்லுங்கள்.",
                "kn": "ಈ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲೇ? ಖಚಿತಪಡಿಸಲು ‘ಹೌದು’ ಎಂದು ಹೇಳಿ ಅಥವಾ ಬದಲಿಸಬೇಕಾದುದನ್ನು ತಿಳಿಸಿ.",
            }
            reply = clarification_by_language.get(lang, clarification_by_language["en"])
            session.history.append(ChatMessage(role="assistant", content=reply))
            return self._build_response(session, sanitize_patient_facing_text(reply, lang))

        if lang == "te" and session.history and re.search(r"\b(?:cab|taxi)\b|క్యాబ్|టాక్సీ", message, re.IGNORECASE):
            reply = "క్యాబ్ గురించి కొంచెం వివరంగా చెబుతారా? మీరు రవాణా గురించి అడుగుతున్నారా, లేక అపాయింట్‌మెంట్ బుకింగ్‌ను కొనసాగించాలా?"
            session.history.append(ChatMessage(role="assistant", content=reply))
            return self._build_response(session, reply)

        # Snapshot initial state before reasoning
        initial_fingerprint = session.draft.get_fingerprint()
        initial_confirmation_status = session.confirmation_status
        initial_confirmed_fingerprint = session.confirmed_draft_fingerprint

        turn_tool_calls: List[ToolExecutionResult] = []

        # Check for explicit cancellation intent first (Rule 1: Isolated 'no' is NEVER cancellation)
        hard_cancel = is_explicit_cancellation(message) and not is_first_time_patient_reply(message)
        if hard_cancel:
            session.confirmation_status = ConfirmationStatus.REJECTED
            session.step = ConversationStep.CANCELLED
            session.workflow_stage = "cancelled"
            session.pending_action = None
            session.pending_action_data = {}
            reply = format_localized_message(lang, "cancelled")
            session.history.append(ChatMessage(role="assistant", content=reply))
            return self._build_response(session, reply, turn_tool_calls=turn_tool_calls)

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

        # Doctor preference safeguard: When patient explicitly names a doctor
        is_collecting_patient_info = session.pending_action in (
            "COLLECTING_NEW_PATIENT_NAME",
            "COLLECTING_EXISTING_PATIENT_NAME",
            "COLLECTING_NEW_PATIENT_PHONE",
            "COLLECTING_EXISTING_PATIENT_PHONE",
            "COLLECTING_EXISTING_PATIENT_REF",
            "AWAITING_PATIENT_STATUS",
            "AWAITING_LAB_VERIFICATION_CODE",
        )

        if not emergency_kind and not is_collecting_patient_info:
            explicit_doc_name = extract_explicit_doctor_name(message)
            if explicit_doc_name:
                matched_docs = deduplicate_doctors(search_doctors_tool(db, specialty_or_department=explicit_doc_name))
                if not matched_docs:
                    # Explicit doctor is NOT available at Aarogya One Hospital. Never silently substitute!
                    session.draft.doctor_id = None
                    session.draft.doctor_name = None
                    session.draft.slot_id = None
                    session.draft.slot_start_time = None
                    session.pending_action = None
                    session.pending_action_data = {}
                    session.step = ConversationStep.COLLECTING_DOCTOR
                    reply = format_localized_message(
                        lang,
                        "doctor_not_found_ask_alternative",
                        doctor_name=explicit_doc_name,
                    )
                    session.history.append(ChatMessage(role="assistant", content=reply))
                    return self._build_response(session, reply)
                elif len(matched_docs) > 1 and len({d.get("display_name", "") for d in matched_docs}) > 1:
                    # Ambiguous doctor request matching multiple distinct physicians
                    reply = format_localized_message(
                        lang,
                        "doctor_ambiguous_clarify",
                        doctor_name=explicit_doc_name,
                    )
                    session.history.append(ChatMessage(role="assistant", content=reply))
                    return self._build_response(session, reply)

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
                if booking_attempted_in_turn:
                    return ToolExecutionResult(
                        tool_name="book_appointment",
                        success=False,
                        error="Booking was already attempted in this conversation turn.",
                    )
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
                            slot_display=format_slot_display(session.draft.slot_id, session.draft.slot_start_time, lang=lang),
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
                    if session.draft.doctor_id:
                        refresh_intent = ToolCallIntent(
                            tool_name="get_available_slots",
                            arguments={"doctor_id": session.draft.doctor_id},
                        )
                        fresh_slots_res = self.tool_router.execute_tool(db, refresh_intent)
                        session.tool_trace.append(fresh_slots_res)

                return tool_res

            # Non-booking tools (search_doctors, get_available_slots, or rejected unauthorized tools)
            for prev in turn_tool_calls:
                if prev.tool_name == t_name and getattr(prev, "_call_args", None) == intent.arguments:
                    logger.info("Prevented duplicate execution of tool '%s' with identical arguments in same turn", t_name)
                    session.tool_trace.append(prev)
                    return prev

            tool_res = self.tool_router.execute_tool(db, intent)
            tool_res._call_args = dict(intent.arguments)
            session.tool_trace.append(tool_res)
            turn_tool_calls.append(tool_res)

            if t_name == "search_doctors" and tool_res.success and tool_res.data:
                session.cached_doctor_search = {
                    "query": str(intent.arguments.get("specialty_or_department", "")),
                    "data": tool_res.data,
                }
            elif t_name == "get_available_slots" and tool_res.success and tool_res.data:
                session.cached_slots = {
                    "doctor_id": str(intent.arguments.get("doctor_id", "")),
                    "time_range": intent.arguments.get("time_range"),
                    "data": tool_res.data,
                }

            if t_name == "search_doctors" and tool_res.success and tool_res.data:
                docs = deduplicate_doctors(tool_res.data)
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

            elif t_name == "register_patient" and tool_res.success and tool_res.data:
                p_data = tool_res.data
                session.draft.patient_reference = p_data.get("patient_reference")
                session.draft.patient_name = p_data.get("full_name")
                session.draft.patient_phone = p_data.get("phone_number")
                session.pending_action = None
                session.pending_action_data = {}

            elif t_name == "verify_patient" and tool_res.success and tool_res.data:
                p_data = tool_res.data
                if p_data.get("verified"):
                    session.draft.patient_reference = p_data.get("patient_reference")
                    if p_data.get("full_name"):
                        session.draft.patient_name = p_data.get("full_name")
                    session.pending_action = None
                    session.pending_action_data = {}

            return tool_res

        # Plan action via reasoning adapter
        # Pass tool_executor when using GeminiReasoningAdapter so multi-round tool calls execute within the turn
        use_multi_round_callback = isinstance(self.adapter, GeminiReasoningAdapter)
        try:
            action: AgentAction = self.adapter.plan_and_respond(
                session_state=session,
                user_message=message,
                available_tools=list(self.tool_router.ALLOWED_TOOLS),
                tool_executor=execute_tool_from_adapter if use_multi_round_callback else None,
            )
        except ReasoningAdapterError as exc:
            logger.warning("ReasoningAdapterError caught during turn: %s (code=%s)", exc.safe_message, exc.code)
            action = AgentAction(
                reply=format_localized_message(session.language, "provider_error", reason=exc.safe_message),
                tool_call=None,
            )

        if isinstance(self.adapter, GeminiReasoningAdapter) and getattr(self.adapter, 'last_model_used', None):
            logger.info('MediVoice turn processed with Gemini model: %s', self.adapter.last_model_used)

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
            not getattr(self.adapter, "last_error", None)
            and use_multi_round_callback
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
            not getattr(self.adapter, "last_error", None)
            and use_multi_round_callback
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
                slot_lines = "\n".join([f"• {format_human_slot_time(s.get('start_time'), lang=lang)}" for s in slots[:5]])
                is_explicit_doc = self.adapter._detect_doctor_query(message) is not None
                msg_key = "selected_doctor_slots" if is_explicit_doc else "recommended_doctor_slots"
                final_reply = format_localized_message(
                    lang,
                    msg_key,
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
                            appointment_start_time=format_human_slot_time(d_res.get("appointment_start_time"), lang=lang),
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
                            slot_display=format_slot_display(session.draft.slot_id, session.draft.slot_start_time, lang=lang),
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
                            appointment_start_time=format_human_slot_time(tool_res.data.get("appointment_start_time"), lang=lang),
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
                        # Automatically refresh available slots for this doctor so patient is immediately presented with new options
                        if session.draft.doctor_id:
                            refresh_intent = ToolCallIntent(
                                tool_name="get_available_slots",
                                arguments={"doctor_id": session.draft.doctor_id},
                            )
                            fresh_slots_res = self.tool_router.execute_tool(db, refresh_intent)
                            session.tool_trace.append(fresh_slots_res)
                            if fresh_slots_res.success and fresh_slots_res.data:
                                slot_lines = "\n".join(
                                    [f"• {format_human_slot_time(s['start_time'], lang=lang)}" for s in fresh_slots_res.data]
                                )
                                final_reply += "\n\n" + format_localized_message(
                                    lang,
                                    "available_slots",
                                    doctor_name=session.draft.doctor_name or "the doctor",
                                    slot_lines=slot_lines,
                                )

            elif tool_name == "search_doctors":
                tool_res = self.tool_router.execute_tool(db, action.tool_call)
                session.tool_trace.append(tool_res)
                turn_tool_calls.append(tool_res)
                if tool_res.success and tool_res.data:
                    docs = tool_res.data
                    session.cached_doctor_search = {"query": str(action.tool_call.arguments.get("specialty_or_department", "")), "data": docs}
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
                                [f"• {format_human_slot_time(s.get('start_time'), lang=lang)}" for s in slots[:5]]
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
                        is_flexible_doc = bool(
                            re.search(
                                r"\b(?:anyone(?:\s+is)?(?:\s+okay|\s+fine)?|any(?:\s+doctor|\s+one|\s+specialist)?(?:\s+is)?(?:\s+okay|\s+fine)?|whichever|either(?:\s+is)?(?:\s+okay|\s+fine)?|no\s+preference)\b",
                                message.lower(),
                            )
                        )
                        if is_flexible_doc and docs:
                            chosen = docs[0]
                            session.draft.doctor_id = chosen["doctor_id"]
                            session.draft.doctor_name = chosen["display_name"]
                            session.draft.specialty = chosen["specialty"]
                            session.pending_action = None
                            session.pending_action_data = {}

                            # Chain to get_available_slots for this doctor
                            slot_intent = ToolCallIntent(
                                tool_name="get_available_slots",
                                arguments={"doctor_id": chosen["doctor_id"]},
                            )
                            slot_res = self.tool_router.execute_tool(db, slot_intent)
                            session.tool_trace.append(slot_res)
                            turn_tool_calls.append(slot_res)

                            if slot_res.success and slot_res.data:
                                slots = slot_res.data
                                s0 = slots[0]
                                session.pending_action = "CONFIRM_SUGGESTED_SLOT"
                                session.pending_action_data = {
                                    "slot_id": s0["slot_id"],
                                    "slot_start_time": s0.get("start_time"),
                                }
                                formatted_time = format_human_slot_time(s0.get("start_time"), lang=lang)
                                final_reply = format_localized_message(
                                    lang, "suggest_earliest_slot", slot_time=formatted_time, slot_id=s0["slot_id"]
                                )
                                session.step = ConversationStep.COLLECTING_SLOT
                            else:
                                final_reply = format_localized_message(
                                    lang, "no_slots", doctor_name=chosen["display_name"]
                                )
                                session.step = ConversationStep.COLLECTING_SLOT
                        elif len(docs) == 1:
                            chosen = docs[0]
                            session.draft.specialty = chosen.get("specialty")
                            session.pending_action = "SHOW_SLOTS_FOR_DOCTOR"
                            session.pending_action_data = {
                                "doctor_id": chosen.get("doctor_id"),
                                "doctor_name": chosen.get("display_name"),
                                "specialty": chosen.get("specialty"),
                            }
                            final_reply = format_localized_message(
                                lang,
                                "doctor_found_consult_or_more",
                                doctor_name=chosen["display_name"],
                                specialty=chosen["specialty"],
                            )
                        elif docs:
                            session.pending_action = "SHOW_SLOTS_FOR_DOCTOR"
                            session.pending_action_data = {
                                "doctor_id": docs[0].get("doctor_id"),
                                "doctor_name": docs[0].get("display_name"),
                                "specialty": docs[0].get("specialty"),
                            }
                            doc_list_str = "\n".join(
                                [f"• {d['display_name']} — {d['specialty']} ({d['department_name']})" for d in docs]
                            )
                            spec_plural = get_specialist_plural(lang, docs[0].get("specialty", "Specialist"))
                            final_reply = format_localized_message(
                                lang,
                                "found_specialists_recommend",
                                count=len(docs),
                                specialist_plural=spec_plural,
                                doc_list=doc_list_str,
                                recommend_name=docs[0]["display_name"],
                            )
                        session.step = ConversationStep.COLLECTING_DOCTOR
                else:
                    doc_query = self.adapter._detect_doctor_query(message)
                    if doc_query:
                        session.draft.doctor_id = None
                        session.draft.doctor_name = None
                        session.draft.slot_id = None
                        session.draft.slot_start_time = None
                        session.pending_action = None
                        session.pending_action_data = {}
                        session.step = ConversationStep.COLLECTING_DOCTOR
                        final_reply = format_localized_message(
                            lang,
                            "doctor_not_found_ask_alternative",
                            doctor_name=doc_query,
                        )
                    else:
                        final_reply = format_localized_message(lang, "no_doctors")

            elif tool_name == "get_available_slots":
                tool_res = self.tool_router.execute_tool(db, action.tool_call)
                session.tool_trace.append(tool_res)
                turn_tool_calls.append(tool_res)
                session.pending_action = None
                session.pending_action_data = {}
                if tool_res.success and tool_res.data:
                    slots = tool_res.data
                    session.cached_slots = {"doctor_id": str(action.tool_call.arguments.get("doctor_id", "")), "time_range": action.tool_call.arguments.get("time_range"), "data": slots}
                    if slots and not session.draft.doctor_name:
                        session.draft.doctor_name = slots[0].get("doctor_name")
                        session.draft.specialty = slots[0].get("specialty")

                    is_flexible = (
                        is_flexible_slot_request(message)
                        or bool(re.search(r"\b(anyone\s+(?:is\s+)?fine|any\s+(?:doctor|one|specialist)?\s+(?:is\s+)?fine|either\s+is\s+fine|no\s+preference)\b", message.lower()))
                    )
                    if is_flexible and slots:
                        s0 = slots[0]
                        session.pending_action = "CONFIRM_SUGGESTED_SLOT"
                        session.pending_action_data = {
                            "slot_id": s0["slot_id"],
                            "slot_start_time": s0.get("start_time"),
                        }
                        formatted_time = format_human_slot_time(s0.get("start_time"), lang=lang)
                        final_reply = format_localized_message(
                            lang, "suggest_earliest_slot", slot_time=formatted_time, slot_id=s0["slot_id"]
                        )
                    else:
                        slot_lines = "\n".join(
                            [f"• {format_human_slot_time(s['start_time'], lang=lang)}" for s in slots[:5]]
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

            elif tool_name == "register_patient":
                tool_res = self.tool_router.execute_tool(db, action.tool_call)
                session.tool_trace.append(tool_res)
                turn_tool_calls.append(tool_res)
                if tool_res.success and tool_res.data:
                    p_data = tool_res.data
                    session.draft.patient_reference = p_data.get("patient_reference")
                    session.draft.patient_name = p_data.get("full_name")
                    session.draft.patient_phone = p_data.get("phone_number")
                    session.pending_action = None
                    session.pending_action_data = {}
                    if not session.draft.reason_category:
                        session.draft.reason_category = f"{session.draft.specialty or 'General'} Consultation"
                    final_reply = f"Thank you, {session.draft.patient_name}! Your patient registration is complete. Your reference ID is {session.draft.patient_reference}."

            elif tool_name == "verify_patient":
                tool_res = self.tool_router.execute_tool(db, action.tool_call)
                session.tool_trace.append(tool_res)
                turn_tool_calls.append(tool_res)
                if tool_res.success and tool_res.data and tool_res.data.get("verified"):
                    p_data = tool_res.data
                    session.draft.patient_reference = p_data.get("patient_reference")
                    if p_data.get("full_name"):
                        session.draft.patient_name = p_data.get("full_name")
                    session.pending_action = None
                    session.pending_action_data = {}
                    if not session.draft.reason_category:
                        session.draft.reason_category = f"{session.draft.specialty or 'General'} Consultation"
                    final_reply = format_localized_message(
                        lang,
                        "patient_verified_success",
                        patient_reference=session.draft.patient_reference,
                        patient_name=session.draft.patient_name or "Patient",
                    )
                else:
                    session.pending_action = "AWAITING_PATIENT_STATUS"
                    final_reply = format_localized_message(lang, "patient_not_found_options")

            elif tool_name == "check_lab_report_status":
                is_non_booking_info_turn = True
                tool_res = self.tool_router.execute_tool(db, action.tool_call)
                session.tool_trace.append(tool_res)
                turn_tool_calls.append(tool_res)
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
                turn_tool_calls.append(tool_res)
                if tool_res.success and isinstance(tool_res.data, dict):
                    final_reply = format_insurance_search_reply(lang, tool_res.data, user_message=message)
                else:
                    final_reply = format_insurance_search_reply(
                        lang,
                        {"providers": [], "matched_count": 0},
                        user_message=message,
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
                pat_disp = (
                    f"{session.draft.patient_name} ({session.draft.patient_reference})"
                    if session.draft.patient_name and session.draft.patient_name != session.draft.patient_reference
                    else session.draft.patient_reference
                )
                summary_prompt = format_localized_message(
                    lang,
                    "confirm_summary",
                    patient_reference=pat_disp,
                    doctor_name=session.draft.doctor_name or "Specialist",
                    specialty=session.draft.specialty or "OPD",
                            slot_display=format_slot_display(session.draft.slot_id, session.draft.slot_start_time, lang=lang),
                    reason_category=session.draft.reason_category,
                )
                # Ensure single localized confirmation summary is returned
                confirm_markers = [
                    "confirm your appointment",
                    "reply yes to confirm",
                    "yes to confirm",
                    "మీ అపాయింట్‌మెంట్ వివరాలను",
                    "అపాయింట్",
                    "నిర్ధారించండి",
                    "ధృవీకరించడానికి",
                    "ఖరారు చేయడానికి",
                    "விவரங்களை உறுதிப்படுத்தவும்",
                    "முன்பதிவு விவரங்களை",
                    "உறுதிப்படுத்த",
                    "ವಿವರಗಳನ್ನು ದೃಢೀಕರಿಸಿ",
                    "ಅಪಾಯಿಂಟ್",
                    "ದೃಢೀಕರಿಸಲು",
                    "ಖಚಿತಪಡಿಸಲು",
                    "विवरण की पुष्टि करें",
                    "अपॉइंटमेंट के विवरण",
                    "पुष्टि करने के लिए",
                    "कन्फर्म करने के लिए",
                ]
                is_already_confirm = any(cm.lower() in (final_reply or "").lower() for cm in confirm_markers)

                # If active session language is Indic (te, hi, ta, kn) and final_reply is in English or has duplicate, replace with single localized summary
                if lang in ("te", "hi", "ta", "kn"):
                    if not has_expected_language_script(final_reply or "", lang) or not is_already_confirm:
                        final_reply = summary_prompt
                    elif "Please verify and confirm" in (final_reply or "") or "confirm your appointment" in (final_reply or "").lower():
                        final_reply = summary_prompt
                else:
                    if not final_reply:
                        final_reply = summary_prompt
                    elif not is_already_confirm and summary_prompt not in final_reply:
                        final_reply = f"{final_reply}\n\n{summary_prompt}"

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
        final_reply = sanitize_patient_facing_text(final_reply, lang)

        # Guard against empty/undefined responses
        if not final_reply or not str(final_reply).strip():
            logger.warning(
                "Empty assistant reply generated for session %s (step=%s, msg='%s'). Falling back safely.",
                session.session_id,
                session.step,
                message,
            )
            final_reply = build_localized_prompt_for_current_state(session)
        if not final_reply or not str(final_reply).strip():
            # Greet once at beginning; do not repeat greeting on every turn when session is underway
            if any(m.role == "user" for m in session.history):
                final_reply = build_localized_prompt_for_current_state(session)
                if not final_reply or not str(final_reply).strip():
                    final_reply = format_localized_message(session.language, "how_to_book")
            else:
                final_reply = format_localized_message(session.language, "greeting")

        # Record assistant reply in history
        session.history.append(ChatMessage(role="assistant", content=final_reply))
        turn_timings = dict(getattr(self.adapter, "last_turn_timings", {}) or {})
        turn_timings["agent_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
        if "gemini_calls_count" not in turn_timings:
            turn_timings["gemini_calls_count"] = 0
        return self._build_response(session, final_reply, turn_tool_calls=turn_tool_calls, timings=turn_timings)

    def _compute_suggested_options(self, session: AgentSessionState) -> Optional[List[Dict[str, str]]]:
        if session.step == ConversationStep.BOOKED or session.step == ConversationStep.CANCELLED:
            return None
        if (
            session.step == ConversationStep.AWAITING_CONFIRMATION
            or session.confirmation_status == ConfirmationStatus.PENDING
        ):
            return [
                {"label": "Confirm & Book", "value": "YES"},
                {"label": "Cancel / Change", "value": "No, cancel"},
            ]
        if session.pending_action == "CLARIFY_ACCOUNT_VS_BOOKING":
            lang = session.language or "en"
            if lang == "te":
                return [
                    {"label": "అపాయింట్‌మెంట్ బుక్ చేయండి", "value": "డాక్టర్ అపాయింట్‌మెంట్ బుక్ చేయండి"},
                    {"label": "కొత్త ఖాతా నమోదు", "value": "కొత్త పేషెంట్ ఖాతా నమోదు"},
                ]
            elif lang == "ta":
                return [
                    {"label": "அப்பாயிண்ட்மென்ட் பதிவு", "value": "மருத்துவர் அப்பாயிண்ட்மென்ட் பதிவு செய்ய விரும்புகிறேன்"},
                    {"label": "புதிய கணக்கு பதிவு", "value": "புதிய நோயாளி கணக்கு பதிவு செய்ய விரும்புகிறேன்"},
                ]
            elif lang == "kn":
                return [
                    {"label": "ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕ್ ಮಾಡಿ", "value": "ವೈದ್ಯರ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕ್ ಮಾಡಿ"},
                    {"label": "ಹೊಸ ಖಾತೆ ನೋಂದಣಿ", "value": "ಹೊಸ ರೋಗಿಯ ಖಾತೆ ನೋಂದಾಯಿಸಿ"},
                ]
            elif lang == "hi":
                return [
                    {"label": "अपॉइंटमेंट बुक करें", "value": "डॉक्टर का अपॉइंटमेंट बुक करें"},
                    {"label": "नया खाता पंजीकृत करें", "value": "नया मरीज खाता पंजीकृत करें"},
                ]
            return [
                {"label": "Book Doctor Appointment", "value": "I want to book a doctor appointment"},
                {"label": "Register New Account", "value": "I want to register a new patient account"},
            ]
        if session.pending_action == "AWAITING_PATIENT_STATUS":
            return [
                {"label": "No, this is my first time", "value": "No, this is my first time"},
                {"label": "Yes, I visited before", "value": "Yes, I have visited before"},
            ]
        if session.pending_action == "COLLECTING_EXISTING_PATIENT_REF":
            return [
                {"label": "I don't remember", "value": "I don't remember"},
            ]
        if session.pending_action in ("CONFIRM_SUGGESTED_SLOT", "SELECT_EARLIEST_SLOT"):
            return [
                {"label": "Yes, reserve this slot", "value": "Okay"},
                {"label": "Show other times", "value": "Show other times"},
            ]
        if session.pending_action == "SHOW_SLOTS_FOR_DOCTOR":
            doc_name = session.pending_action_data.get("doctor_name") or "doctor"
            return [
                {"label": f"{doc_name} is fine", "value": f"{doc_name} is fine"},
                {"label": "See other doctors", "value": "Show other available doctors"},
            ]
        if session.step == ConversationStep.COLLECTING_SLOT and not session.draft.slot_id:
            return [
                {"label": "Morning", "value": "morning"},
                {"label": "Afternoon", "value": "afternoon"},
                {"label": "Anything is fine", "value": "Anything is fine"},
            ]
        if not session.draft.doctor_id and not session.draft.specialty:
            return [
                {"label": "I have a fever", "value": "I have a fever"},
                {"label": "Cardiologist", "value": "I need a cardiologist"},
                {"label": "Check lab report", "value": "Check lab report"},
            ]
        return None

    def _build_response(
        self,
        session: AgentSessionState,
        reply: str,
        turn_tool_calls: Optional[List[ToolExecutionResult]] = None,
        timings: Optional[Dict[str, float]] = None,
    ) -> ChatResponse:
        options = self._compute_suggested_options(session)
        actual_turn_tools = turn_tool_calls if turn_tool_calls is not None else []
        session.turn_tool_calls = actual_turn_tools
        session.previous_assistant_question = reply

        # Auto-infer workflow and stage if not explicitly set
        if session.step == ConversationStep.CANCELLED:
            session.workflow_stage = "cancelled"
        elif session.step == ConversationStep.BOOKED:
            session.workflow_stage = "completed"
        elif session.step == ConversationStep.AWAITING_CONFIRMATION:
            session.workflow_stage = "confirmation"
            session.expected_response_type = "CONFIRM_BOOKING"
        elif session.pending_action == "CLARIFY_ACCOUNT_VS_BOOKING":
            step_intent = "clarify_intent"
        elif session.pending_action == "AWAITING_PATIENT_STATUS":
            session.workflow_stage = "patient_identification"
            session.expected_response_type = "VISITED_BEFORE"
        elif session.pending_action in ("COLLECTING_NEW_PATIENT_NAME", "COLLECTING_NEW_PATIENT_PHONE", "COLLECTING_EXISTING_PATIENT_PHONE", "COLLECTING_EXISTING_PATIENT_REF"):
            session.workflow_stage = "patient_identification"
        elif session.pending_action == "CONFIRM_SUGGESTED_SLOT":
            session.workflow_stage = "slot_selection"
            session.expected_response_type = "CONFIRM_SLOT"
        elif session.pending_action == "AWAITING_LAB_VERIFICATION_CODE":
            session.current_workflow = "lab_report"
            session.expected_response_type = "LAB_VERIFICATION_CODE"

        clean_reply = html.unescape(reply) if isinstance(reply, str) else reply
        return ChatResponse(
            session_id=session.session_id,
            reply=clean_reply,
            language=session.language,
            step=session.step,
            draft=session.draft,
            missing_details=session.draft.missing_fields(),
            confirmation_status=session.confirmation_status,
            tool_trace=session.tool_trace,
            turn_tool_calls=actual_turn_tools,
            tool_calls=actual_turn_tools,
            timings=timings,
            booked_appointment=session.booked_appointment,
            suggested_options=options,
        )


# Global singleton instance for application use
conversation_manager = ConversationManager()
