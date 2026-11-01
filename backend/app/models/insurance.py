import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.core.config import settings


class InsuranceProvider(Base):
    __tablename__ = "insurance_providers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hospital_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        default=lambda: settings.DEFAULT_HOSPITAL_ID,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(150), nullable=False, unique=True, index=True
    )
    code: Mapped[str] = mapped_column(
        String(50), nullable=False, default="INS-DEMO", index=True
    )
    support_contact: Mapped[str] = mapped_column(
        String(150), nullable=False, default="1800-100-4200 (Ext. 400)"
    )
    desk_location: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, default="Ground Floor, Block A — Aarogya One Hospital"
    )
    contact_hours: Mapped[Optional[str]] = mapped_column(
        String(150), nullable=True, default="08:00 AM - 08:00 PM IST (24/7 Emergency TPA Support)"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    is_synthetic_demo: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    plans = relationship(
        "InsurancePlan",
        back_populates="provider",
        cascade="all, delete-orphan",
        order_by="InsurancePlan.plan_name",
    )

    def __init__(self, **kwargs):
        if "provider_name" in kwargs and "name" not in kwargs:
            kwargs["name"] = kwargs.pop("provider_name")
        else:
            kwargs.pop("provider_name", None)
        if "contact_number" in kwargs and "support_contact" not in kwargs:
            kwargs["support_contact"] = kwargs.pop("contact_number")
        else:
            kwargs.pop("contact_number", None)
        super().__init__(**kwargs)

    @property
    def provider_name(self) -> str:
        return self.name

    @property
    def contact_number(self) -> str:
        return self.support_contact


class InsurancePlan(Base):
    __tablename__ = "insurance_plans"
    __table_args__ = (
        UniqueConstraint("provider_id", "plan_name", name="uq_provider_plan_name"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    provider_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("insurance_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_name: Mapped[str] = mapped_column(
        String(150), nullable=False, index=True
    )
    plan_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Individual & Family Floater"
    )
    coverage_summary: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    covered_services: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    copay_summary: Mapped[str] = mapped_column(
        Text, nullable=False, default="Standard policy co-pay applies."
    )
    exclusions_and_limitations: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    preauthorization_required: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    cashless_available: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    reimbursement_available: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    network_notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    provider = relationship("InsuranceProvider", back_populates="plans")

    def __init__(self, **kwargs):
        if "coverage_notes" in kwargs and "coverage_summary" not in kwargs:
            kwargs["coverage_summary"] = kwargs.pop("coverage_notes")
        else:
            kwargs.pop("coverage_notes", None)
        if "supported_services" in kwargs and "covered_services" not in kwargs:
            kwargs["covered_services"] = kwargs.pop("supported_services")
        else:
            kwargs.pop("supported_services", None)
        super().__init__(**kwargs)

    @property
    def coverage_notes(self) -> str:
        return self.coverage_summary

    @property
    def supported_services(self) -> str:
        return self.covered_services
