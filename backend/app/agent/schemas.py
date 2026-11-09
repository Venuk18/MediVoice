from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator


class ConversationStep(str, Enum):
    GREETING = "GREETING"
    COLLECTING_DOCTOR = "COLLECTING_DOCTOR"
    COLLECTING_SLOT = "COLLECTING_SLOT"
    COLLECTING_DETAILS = "COLLECTING_DETAILS"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"
    # Natural conversation states
    IDENTIFYING_DEPARTMENT = "IDENTIFYING_DEPARTMENT"
    PATIENT_IDENTIFICATION = "PATIENT_IDENTIFICATION"
    NEW_PATIENT_REGISTRATION = "NEW_PATIENT_REGISTRATION"
    EXISTING_PATIENT_VERIFICATION = "EXISTING_PATIENT_VERIFICATION"
    REVIEWING_APPOINTMENT = "REVIEWING_APPOINTMENT"
    # Registration & detail collection compatibility states
    COLLECTING_NAME = "COLLECTING_NAME"
    COLLECTING_PHONE = "COLLECTING_PHONE"


class ConfirmationStatus(str, Enum):
    NONE = "NONE"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    STALE = "STALE"


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user', 'assistant', 'system', or 'tool'")
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BookingDraft(BaseModel):
    doctor_id: Optional[str] = None
    doctor_name: Optional[str] = None
    specialty: Optional[str] = None
    slot_id: Optional[str] = None
    slot_start_time: Optional[str] = None
    reason_category: Optional[str] = None
    patient_reference: Optional[str] = None
    # Patient registration/identification details
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    is_new_patient: Optional[bool] = None

    def get_fingerprint(self) -> str:
        """Returns deterministic fingerprint of the core booking parameters."""
        raw = f"{self.patient_reference or ''}|{self.doctor_id or ''}|{self.slot_id or ''}|{self.reason_category or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def is_complete(self) -> bool:
        """Checks if all required booking parameters are present."""
        return bool(
            self.doctor_id
            and self.slot_id
            and self.reason_category
            and self.patient_reference
        )

    def missing_fields(self) -> List[str]:
        missing = []
        if not self.doctor_id:
            missing.append("doctor")
        if not self.slot_id:
            missing.append("slot")
        if not self.reason_category:
            missing.append("reason")
        if not self.patient_reference:
            missing.append("patient_reference")
        return missing


class ToolCallIntent(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResult(BaseModel):
    tool_name: str
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


class AgentAction(BaseModel):
    reply: str
    tool_call: Optional[ToolCallIntent] = None


class AgentSessionState(BaseModel):
    session_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_active_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    language: str = "en"
    language_mode: str = "auto"
    preferred_language: Optional[str] = None
    step: ConversationStep = ConversationStep.GREETING
    draft: BookingDraft = Field(default_factory=BookingDraft)
    confirmation_status: ConfirmationStatus = ConfirmationStatus.NONE
    confirmed_draft_fingerprint: Optional[str] = None
    pending_action: Optional[str] = None
    pending_action_data: Dict[str, Any] = Field(default_factory=dict)
    history: List[ChatMessage] = Field(default_factory=list)
    tool_trace: List[ToolExecutionResult] = Field(default_factory=list)
    booked_appointment: Optional[Dict[str, Any]] = None
    suggested_options: Optional[List[Dict[str, str]]] = None

    # Structured workflow & context tracking
    current_workflow: str = "appointment"
    workflow_stage: Optional[str] = None
    previous_assistant_question: Optional[str] = None
    expected_response_type: Optional[str] = None
    cached_doctor_search: Optional[Dict[str, Any]] = None
    cached_slots: Optional[Dict[str, Any]] = None
    turn_tool_calls: List[ToolExecutionResult] = Field(default_factory=list)
    spoken_reply: Optional[str] = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("step", mode="before")
    @classmethod
    def validate_step(cls, v: Any) -> ConversationStep:
        if isinstance(v, ConversationStep):
            return v
        if isinstance(v, str):
            try:
                return ConversationStep(v)
            except ValueError:
                v_clean = v.strip().upper()
                for member in ConversationStep:
                    if member.name == v_clean or member.value == v_clean:
                        return member
                return ConversationStep.GREETING
        return ConversationStep.GREETING


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    patient_reference: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    language: str = "en"
    language_mode: str = "auto"
    preferred_language: Optional[str] = None
    step: ConversationStep
    draft: BookingDraft
    missing_details: List[str]
    confirmation_status: ConfirmationStatus
    tool_trace: List[ToolExecutionResult] = Field(default_factory=list)
    turn_tool_calls: List[ToolExecutionResult] = Field(default_factory=list)
    spoken_reply: Optional[str] = None
    timings: Optional[Dict[str, float]] = None
    booked_appointment: Optional[Dict[str, Any]] = None
    suggested_options: Optional[List[Dict[str, str]]] = None

    # Compatibility aliases for frontend clients
    assistant_reply: Optional[str] = None
    conversation_step: Optional[str] = None
    requires_confirmation: Optional[bool] = None
    tool_calls: Optional[List[ToolExecutionResult]] = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("step", mode="before")
    @classmethod
    def validate_step(cls, v: Any) -> ConversationStep:
        if isinstance(v, ConversationStep):
            return v
        if isinstance(v, str):
            try:
                return ConversationStep(v)
            except ValueError:
                v_clean = v.strip().upper()
                for member in ConversationStep:
                    if member.name == v_clean or member.value == v_clean:
                        return member
                return ConversationStep.GREETING
        return ConversationStep.GREETING

    @model_validator(mode="after")
    def populate_compatibility_aliases(self) -> "ChatResponse":
        if self.assistant_reply is None:
            self.assistant_reply = self.reply
        if self.conversation_step is None:
            self.conversation_step = self.step.value if hasattr(self.step, "value") else str(self.step)
        if self.requires_confirmation is None:
            self.requires_confirmation = (
                self.confirmation_status == ConfirmationStatus.PENDING
                or self.step == ConversationStep.AWAITING_CONFIRMATION
            )
        if self.tool_calls is None:
            self.tool_calls = self.turn_tool_calls
        return self


class SessionResetResponse(BaseModel):
    status: str
    session_id: str

