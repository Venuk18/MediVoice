from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class AppointmentSlotBase(BaseModel):
    doctor_id: str
    start_time: datetime
    end_time: datetime
    status: str = Field(default="AVAILABLE", pattern="^(AVAILABLE|RESERVED|BOOKED|CANCELLED)$")


class AppointmentSlotCreate(AppointmentSlotBase):
    pass


class AppointmentSlotRead(AppointmentSlotBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DoctorBase(BaseModel):
    hospital_id: str
    department_id: str
    display_name: str = Field(..., max_length=150)
    specialty: str = Field(..., max_length=100)
    is_active: bool = True


class DoctorCreate(DoctorBase):
    pass


class DoctorManageCreate(BaseModel):
    hospital_id: str = Field(default="11111111-1111-1111-1111-111111111111")
    department_id: Optional[str] = None
    department_name: Optional[str] = Field(default="General Medicine")
    display_name: str = Field(..., min_length=3, max_length=150)
    specialty: str = Field(..., min_length=2, max_length=100)


class DoctorSlotCreateRequest(BaseModel):
    start_time: datetime
    end_time: datetime


class DoctorRead(DoctorBase):
    id: str
    created_at: datetime
    department_name: Optional[str] = None
    hospital_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DoctorDetailRead(DoctorRead):
    slots: List[AppointmentSlotRead] = []

