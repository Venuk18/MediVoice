from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MaintenanceWorkOrderCreate(BaseModel):
    hospital_id: Optional[str] = Field(
        default=None, description="Hospital ID (defaults to Aarogya One Hospital)"
    )
    title: str = Field(..., min_length=4, max_length=255, description="Brief work order title")
    description: str = Field(..., min_length=6, max_length=2000, description="Detailed problem description")
    category: str = Field(
        default="Biomedical Equipment",
        max_length=80,
        description="Category (Biomedical Equipment, HVAC & Environmental, Electrical & Power, Sanitation & Plumbing, IT & Telemetry, Facility & Safety)",
    )
    location: str = Field(
        ..., min_length=2, max_length=200, description="Hospital location / floor / wing / suite"
    )
    equipment_reference: Optional[str] = Field(
        default=None, max_length=120, description="Asset tag or equipment reference (e.g., BIO-VENT-204)"
    )
    priority: str = Field(
        default="MEDIUM",
        description="Priority level (LOW, MEDIUM, HIGH, CRITICAL)",
    )
    reported_by: Optional[str] = Field(
        default="Hospital Operations Desk",
        max_length=120,
        description="Staff member or department reporting the issue",
    )
    assigned_to: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Optional initial engineer or maintenance team assignment",
    )


class MaintenanceWorkOrderStatusUpdate(BaseModel):
    status: str = Field(
        ...,
        description="Target lifecycle status (OPEN, ASSIGNED, IN_PROGRESS, RESOLVED)",
    )
    assigned_to: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Engineer or maintenance unit assigned to the work order",
    )
    resolution_notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Operational notes or mandatory resolution summary when marking RESOLVED",
    )


class MaintenanceWorkOrderRead(BaseModel):
    id: str
    hospital_id: str
    work_order_code: str
    title: str
    description: str
    category: str
    location: str
    equipment_reference: Optional[str] = None
    priority: str
    status: str
    reported_by: str
    assigned_to: Optional[str] = None
    resolution_notes: Optional[str] = None
    allowed_next_statuses: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MaintenanceSummaryMetrics(BaseModel):
    total_work_orders: int
    open_count: int
    assigned_count: int
    in_progress_count: int
    resolved_count: int
    critical_active_count: int
    high_active_count: int
