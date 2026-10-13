from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class WorkflowExceptionBase(BaseModel):
    exception_type: str = Field(..., max_length=100)
    title: str = Field(..., max_length=255)
    description: str
    priority: str = Field(..., pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    responsible_department: str = Field(..., max_length=100)
    assigned_to: Optional[str] = None
    status: str = Field(default="OPEN", pattern="^(OPEN|IN_PROGRESS|RESOLVED|DISMISSED)$")
    affected_record_type: str = Field(..., max_length=50)
    affected_record_id: str = Field(..., max_length=100)


class WorkflowExceptionCreate(WorkflowExceptionBase):
    pass


class WorkflowExceptionAssign(BaseModel):
    assigned_to: str = Field(..., min_length=2, max_length=100)


class WorkflowExceptionResolve(BaseModel):
    resolution_note: str = Field(..., min_length=5, description="Investigation finding and resolution note")


class WorkflowExceptionRead(WorkflowExceptionBase):
    id: str
    detected_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AuditEventRead(BaseModel):
    id: str
    actor_reference: str
    action: str
    entity_type: str
    entity_id: str
    details: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
