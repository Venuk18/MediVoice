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


class DoctorRead(DoctorBase):
    id: str
    created_at: datetime
    department_name: Optional[str] = None
    hospital_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DoctorDetailRead(DoctorRead):
    slots: List[AppointmentSlotRead] = []
