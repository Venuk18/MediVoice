import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    patient_reference: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    doctor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Unique constraint guarantees at the DB level that a slot cannot be booked by multiple appointments
    slot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("appointment_slots.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True
    )
    # Statuses: CONFIRMED, COMPLETED, CANCELLED, NO_SHOW
    appointment_status: Mapped[str] = mapped_column(
        String(30), default="CONFIRMED", nullable=False, index=True
    )
    reason_category: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    visit_completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    follow_up_recommended: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    follow_up_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    follow_up_notes: Mapped[str] = mapped_column(
        Text, nullable=True
    )

    # Relationships
    doctor = relationship("Doctor", back_populates="appointments")
    slot = relationship("AppointmentSlot", back_populates="appointment")
