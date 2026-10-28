import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class MaintenanceStatus(str, Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class MaintenancePriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MaintenanceCategory(str, Enum):
    BIOMEDICAL_EQUIPMENT = "Biomedical Equipment"
    HVAC_ENVIRONMENTAL = "HVAC & Environmental"
    ELECTRICAL_POWER = "Electrical & Power"
    SANITATION_PLUMBING = "Sanitation & Plumbing"
    IT_TELEMETRY = "IT & Telemetry"
    FACILITY_SAFETY = "Facility & Safety"


class MaintenanceWorkOrder(Base):
    __tablename__ = "maintenance_work_orders"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hospital_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_order_code: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(80),
        default=MaintenanceCategory.FACILITY_SAFETY.value,
        nullable=False,
        index=True,
    )
    location: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True
    )
    equipment_reference: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        default=MaintenancePriority.MEDIUM.value,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=MaintenanceStatus.OPEN.value,
        nullable=False,
        index=True,
    )
    reported_by: Mapped[str] = mapped_column(
        String(120), default="Hospital Operations Desk", nullable=False
    )
    assigned_to: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True, index=True
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
