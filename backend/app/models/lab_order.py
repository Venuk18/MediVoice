import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class LabOrder(Base):
    __tablename__ = "lab_orders"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    patient_reference: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    ordering_department_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    test_category: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    # Allowed statuses: Pending, Processing, Completed, Delayed
    workflow_status: Mapped[str] = mapped_column(
        String(30), default="Pending", nullable=False, index=True
    )
    expected_completion_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    assigned_team: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    delay_reason: Mapped[str] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    ordering_department = relationship("Department", back_populates="lab_orders")
