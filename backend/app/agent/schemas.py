from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ConversationStep(str, Enum):
    GREETING = "GREETING"
    COLLECTING_DOCTOR = "COLLECTING_DOCTOR"
    COLLECTING_SLOT = "COLLECTING_SLOT"
    COLLECTING_DETAILS = "COLLECTING_DETAILS"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"


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
    step: ConversationStep = ConversationStep.GREETING
    draft: BookingDraft = Field(default_factory=BookingDraft)
    confirmation_status: ConfirmationStatus = ConfirmationStatus.NONE
    confirmed_draft_fingerprint: Optional[str] = None
    pending_action: Optional[str] = None
    pending_action_data: Dict[str, Any] = Field(default_factory=dict)
    history: List[ChatMessage] = Field(default_factory=list)
    tool_trace: List[ToolExecutionResult] = Field(default_factory=list)
    booked_appointment: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="ignore")


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    patient_reference: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    language: str = "en"
    step: ConversationStep
    draft: BookingDraft
    missing_details: List[str]
    confirmation_status: ConfirmationStatus
    tool_trace: List[ToolExecutionResult] = Field(default_factory=list)
    booked_appointment: Optional[Dict[str, Any]] = None


class SessionResetResponse(BaseModel):
    status: str
    session_id: str

