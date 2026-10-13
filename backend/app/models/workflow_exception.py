import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class WorkflowException(Base):
    __tablename__ = "workflow_exceptions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Types: LAB_ORDER_OVERDUE, UNASSIGNED_CRITICAL_ORDER, SLOT_CONFLICT, etc.
    exception_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Priorities: LOW, MEDIUM, HIGH, CRITICAL
    priority: Mapped[str] = mapped_column(
        String(20), default="MEDIUM", nullable=False, index=True
    )
    responsible_department: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    assigned_to: Mapped[str] = mapped_column(
        String(100), nullable=True, index=True
    )
    # Statuses: OPEN, IN_PROGRESS, RESOLVED, DISMISSED
    status: Mapped[str] = mapped_column(
        String(30), default="OPEN", nullable=False, index=True
    )
    affected_record_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    affected_record_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_note: Mapped[str] = mapped_column(
        Text, nullable=True
    )
