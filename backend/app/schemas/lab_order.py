from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class LabOrderBase(BaseModel):
    patient_reference: str = Field(..., max_length=100)
    ordering_department_id: Optional[str] = None
    test_category: str = Field(..., max_length=100)
    workflow_status: str = Field(
        default="Pending",
        pattern="^(Pending|Processing|Completed|Delayed)$",
        description="Allowed workflow statuses: Pending, Processing, Completed, Delayed"
    )
    expected_completion_at: datetime
    assigned_team: str = Field(..., max_length=100)
    delay_reason: Optional[str] = None


class LabOrderCreate(LabOrderBase):
    pass


class LabOrderStatusUpdate(BaseModel):
    workflow_status: str = Field(
        ...,
        pattern="^(Pending|Processing|Completed|Delayed)$"
    )
    delay_reason: Optional[str] = None


class LabOrderRead(LabOrderBase):
    id: str
    created_at: datetime
    updated_at: datetime
    department_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
