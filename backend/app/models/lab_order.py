import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Any
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class LabStatus(str, Enum):
    REGISTERED = "REGISTERED"
    SAMPLE_COLLECTED = "SAMPLE_COLLECTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


LEGACY_TO_CANONICAL_LAB_STATUS = {
    "pending": LabStatus.REGISTERED.value,
    "registered": LabStatus.REGISTERED.value,
    "sample_collected": LabStatus.SAMPLE_COLLECTED.value,
    "sample collected": LabStatus.SAMPLE_COLLECTED.value,
    "processing": LabStatus.PROCESSING.value,
    "delayed": LabStatus.PROCESSING.value,
    "completed": LabStatus.COMPLETED.value,
    "cancelled": LabStatus.CANCELLED.value,
    "canceled": LabStatus.CANCELLED.value,
}


def normalize_lab_status(raw_status: Optional[str]) -> str:
    if not raw_status:
        return LabStatus.REGISTERED.value
    key = str(raw_status).strip().lower()
    return LEGACY_TO_CANONICAL_LAB_STATUS.get(key, str(raw_status).strip().upper())


class LabOrder(Base):
    __tablename__ = "lab_orders"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    patient_reference: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    ordering_department_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    test_category: Mapped[str] = mapped_column(
        String(150), nullable=False, index=True
    )
    test_name: Mapped[Optional[str]] = mapped_column(
        String(150), nullable=True, index=True
    )
    # Allowed statuses: Pending, Processing, Completed, Delayed, REGISTERED, SAMPLE_COLLECTED, PROCESSING, COMPLETED, CANCELLED
    workflow_status: Mapped[str] = mapped_column(
        String(30), default="Pending", nullable=False, index=True
    )
    expected_completion_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + timedelta(hours=4),
        nullable=False,
        index=True,
    )
    assigned_team: Mapped[str] = mapped_column(
        String(100), default="Central Diagnostics Lab", nullable=False, index=True
    )
    delay_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    # Six-digit verification code fields (always stored as 6-character string to preserve leading zeros)
    verification_code: Mapped[Optional[str]] = mapped_column(
        String(6), nullable=True, index=True
    )
    verification_code_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    verification_code_is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    verification_code_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    ordering_department = relationship("Department", back_populates="lab_orders")

    def __init__(self, **kwargs: Any):
        # Synchronize test_name and test_category for backwards & forwards compatibility
        if "test_name" in kwargs and "test_category" not in kwargs and kwargs["test_name"]:
            kwargs["test_category"] = kwargs["test_name"]
        elif "test_category" in kwargs and "test_name" not in kwargs and kwargs["test_category"]:
            kwargs["test_name"] = kwargs["test_category"]

        # Support lab_status or status alias in constructor
        if "lab_status" in kwargs:
            val = kwargs.pop("lab_status")
            if "workflow_status" not in kwargs and val:
                kwargs["workflow_status"] = val.value if isinstance(val, Enum) else str(val)
        if "status" in kwargs:
            val = kwargs.pop("status")
            if "workflow_status" not in kwargs and val:
                kwargs["workflow_status"] = val.value if isinstance(val, Enum) else str(val)

        if "workflow_status" in kwargs and isinstance(kwargs["workflow_status"], Enum):
            kwargs["workflow_status"] = kwargs["workflow_status"].value

        super().__init__(**kwargs)

    @property
    def display_test_name(self) -> str:
        return self.test_name or self.test_category

    @property
    def lab_status(self) -> str:
        return normalize_lab_status(self.workflow_status)

