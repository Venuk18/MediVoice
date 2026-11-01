from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class DepartmentBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    is_active: bool = True


class DepartmentCreate(DepartmentBase):
    hospital_id: str


class DepartmentRead(DepartmentBase):
    id: str
    hospital_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HospitalBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    address: str
    is_active: bool = True


class HospitalCreate(HospitalBase):
    id: Optional[str] = None


class HospitalRead(HospitalBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HospitalDetailRead(HospitalRead):
    departments: List[DepartmentRead] = []
