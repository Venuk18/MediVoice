from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

ALLOWED_LAB_STATUS_PATTERN = (
    "^(Pending|Processing|Completed|Delayed|"
    "REGISTERED|SAMPLE_COLLECTED|PROCESSING|COMPLETED|CANCELLED)$"
)


class LabOrderBase(BaseModel):
    patient_reference: str = Field(..., max_length=100)
    ordering_department_id: Optional[str] = None
    test_category: Optional[str] = Field(default=None, max_length=150)
    test_name: Optional[str] = Field(default=None, max_length=150)
    workflow_status: str = Field(
        default="REGISTERED",
        pattern=ALLOWED_LAB_STATUS_PATTERN,
        description=(
            "Allowed workflow statuses: Pending, Processing, Completed, Delayed, "
            "REGISTERED, SAMPLE_COLLECTED, PROCESSING, COMPLETED, CANCELLED"
        ),
    )
    expected_completion_at: Optional[datetime] = None
    assigned_team: str = Field(default="Central Diagnostics Lab", max_length=100)
    delay_reason: Optional[str] = None

    @model_validator(mode="after")
    def populate_test_name_and_category(self):
        if not self.test_name and self.test_category:
            self.test_name = self.test_category
        elif not self.test_category and self.test_name:
            self.test_category = self.test_name
        elif not self.test_name and not self.test_category:
            self.test_name = "General Diagnostic Panel"
            self.test_category = "General Diagnostic Panel"
        return self


class LabOrderCreate(LabOrderBase):
    pass


class LabOrderStatusUpdate(BaseModel):
    workflow_status: str = Field(
        ...,
        pattern=ALLOWED_LAB_STATUS_PATTERN,
    )
    delay_reason: Optional[str] = None


class LabOrderRead(LabOrderBase):
    """
    Public / operational lab-order metadata read model.
    Intentionally excludes `verification_code` so codes are never exposed in public listing endpoints.
    """
    id: str
    lab_status: str
    expected_completion_at: datetime
    created_at: datetime
    updated_at: datetime
    department_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LabOrderDemoPortalRead(BaseModel):
    """
    Synthetic patient demo portal response that surfaces the 6-digit verification code
    only for the intended synthetic patient in the demo environment.
    """
    is_synthetic_demo: bool = True
    demo_notice: str = (
        "SYNTHETIC DEMO PORTAL ONLY: This verification code is provided to simulate the "
        "code a patient receives on their lab receipt at Aarogya One Hospital."
    )
    patient_reference: str
    test_name: str
    lab_status: str
    verification_code: str
    verification_code_expires_at: Optional[datetime] = None
    verification_code_is_active: bool = True
    updated_at: datetime


class LabVerificationRequest(BaseModel):
    verification_code: str = Field(
        ...,
        description="Six-digit lab verification code ('000000' through '999999')",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional conversation session identifier for rate limiting",
    )


class LabVerificationResponse(BaseModel):
    """
    Minimal, privacy-safe lab status verification response.
    Excludes patient name, patient_reference, DOB, phone number, internal order ID, and clinical results.
    """
    verified: bool = True
    test_name: str
    lab_status: str
    status_explanation: str
    next_step: str
    last_updated_at: datetime
    disclaimer: str = (
        "Status verification only: This status check provides operational lab order progress only "
        "and does not include clinical test results or medical interpretations. Note: A six-digit code "
        "is a demo status lookup mechanism and is not sufficient standalone authentication for sensitive medical records."
    )
