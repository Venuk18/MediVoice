from typing import List, Optional
from pydantic import BaseModel, Field


class StaffLoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=100, description="Synthetic staff username (e.g., dr.sharma, lab.vikram, maint.karthik)")
    password: str = Field(..., min_length=1, max_length=100, description="Synthetic demo password")


class StaffProfileRead(BaseModel):
    staff_id: str
    username: str
    display_name: str
    role: str
    department: str
    doctor_id: Optional[str] = None
    badge_label: str = ""


class StaffLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int
    staff: StaffProfileRead


class DemoStaffAccountRead(BaseModel):
    staff_id: str
    username: str
    display_name: str
    role: str
    department: str
    doctor_id: Optional[str] = None
    badge_label: str
    workspace_route: str
