from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

INSURANCE_COVERAGE_DISCLAIMER = (
    "Informational only (Synthetic Demo Data): Listed insurance plan information does not guarantee coverage "
    "or claim approval. Final eligibility, co-pay, waiting periods, exclusions, pre-authorization, and "
    "cashless or reimbursement settlement depend on your specific policy terms, insurer/TPA approval, "
    "and verification at the Aarogya One Hospital Insurance Desk."
)


class InsurancePlanBase(BaseModel):
    plan_name: str = Field(..., max_length=150)
    plan_type: str = Field(default="Individual & Family Floater", max_length=100)
    coverage_summary: str
    covered_services: str
    copay_summary: str = Field(default="Standard policy co-pay applies.")
    exclusions_and_limitations: Optional[str] = None
    preauthorization_required: bool = True
    cashless_available: bool = True
    reimbursement_available: bool = True
    network_notes: Optional[str] = None
    is_active: bool = True


class InsurancePlanRead(InsurancePlanBase):
    id: str
    provider_id: str
    provider_name: Optional[str] = None
    supported_services: str = ""
    supported_services_list: List[str] = Field(default_factory=list)
    coverage_notes: str = ""
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InsuranceProviderBase(BaseModel):
    name: str = Field(..., max_length=150)
    provider_name: str = Field(default="", max_length=150)
    code: str = Field(default="INS-DEMO", max_length=50)
    support_contact: str = Field(..., max_length=150)
    contact_number: str = Field(default="", max_length=150)
    desk_location: Optional[str] = Field(
        default="Ground Floor, Block A — Aarogya One Hospital", max_length=200
    )
    contact_hours: Optional[str] = Field(
        default="08:00 AM - 08:00 PM IST (24/7 Emergency TPA Support)", max_length=150
    )
    is_active: bool = True
    is_synthetic_demo: bool = True


class InsuranceProviderRead(InsuranceProviderBase):
    id: str
    hospital_id: str
    plans: List[InsurancePlanRead] = Field(default_factory=list)
    disclaimer: str = INSURANCE_COVERAGE_DISCLAIMER
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InsuranceDeskContactRead(BaseModel):
    hospital_name: str = "Aarogya One Hospital (Synthetic Demo)"
    department: str = "Aarogya One Hospital — Insurance & TPA Helpdesk"
    desk_name: str = "Aarogya One Hospital — Insurance & TPA Helpdesk"
    phone: str = "1800-100-4200 (Ext. 400)"
    contact_number: str = "1800-100-4200 (Ext. 400)"
    location: str = "Ground Floor, Block A — Aarogya One Hospital"
    desk_location: str = "Ground Floor, Block A — Aarogya One Hospital"
    hours: str = "Monday to Saturday, 08:00 AM to 08:00 PM IST (24/7 Emergency TPA Support)"
    operating_hours: str = "Monday to Saturday, 08:00 AM to 08:00 PM IST (24/7 Emergency TPA Support)"
    is_synthetic_demo: bool = True
    disclaimer: str = INSURANCE_COVERAGE_DISCLAIMER


class InsuranceSearchResponse(BaseModel):
    matched_count: int = 0
    query: Optional[str] = None
    provider_name: Optional[str] = None
    plan_type: Optional[str] = None
    service: Optional[str] = None
    cashless: Optional[bool] = None
    providers: List[InsuranceProviderRead] = Field(default_factory=list)
    matching_plans: List[InsurancePlanRead] = Field(default_factory=list)
    insurance_desk_contact: InsuranceDeskContactRead = Field(default_factory=InsuranceDeskContactRead)
    insurance_desk: InsuranceDeskContactRead = Field(default_factory=InsuranceDeskContactRead)
    is_synthetic_demo: bool = True
    disclaimer: str = INSURANCE_COVERAGE_DISCLAIMER


class InsuranceSupportTicketCreate(BaseModel):
    patient_reference: str = Field(
        default="PAT-2026-4409",
        min_length=2,
        max_length=100,
        description="Synthetic patient reference ID",
    )
    provider_name: Optional[str] = Field(
        default=None, max_length=150, description="Insurance provider name if known"
    )
    plan_name: Optional[str] = Field(
        default=None, max_length=150, description="Insurance plan name if known"
    )
    question: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Specific policy or coverage inquiry requiring human TPA desk review",
    )
    contact_preference: Optional[str] = Field(
        default="In-Hospital Insurance Desk Counter 3",
        max_length=150,
    )


class InsuranceSupportTicketRead(BaseModel):
    ticket_id: str
    patient_reference: str
    provider_name: Optional[str] = None
    plan_name: Optional[str] = None
    question: str
    status: str
    priority: str
    assigned_department: str
    created_at: datetime
    disclaimer: str = INSURANCE_COVERAGE_DISCLAIMER


class InsuranceProviderManageCreate(BaseModel):
    hospital_id: str = Field(default="11111111-1111-1111-1111-111111111111")
    name: str = Field(..., min_length=3, max_length=150)
    code: str = Field(..., min_length=2, max_length=50)
    support_contact: str = Field(default="1800-100-4299 (TPA Desk)", max_length=150)
    desk_location: str = Field(
        default="Ground Floor, Block A — Aarogya One Hospital", max_length=200
    )
    contact_hours: str = Field(
        default="08:00 AM - 08:00 PM IST (24/7 Emergency TPA Support)", max_length=150
    )
    plan_name: str = Field(..., min_length=3, max_length=150)
    plan_type: str = Field(default="Family Floater & Cashless", max_length=100)
    coverage_summary: str = Field(
        default="Covers inpatient hospitalization, day-care procedures, and diagnostic workups subject to policy terms."
    )
    covered_services: str = Field(
        default="Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine, Diagnostics"
    )
    copay_summary: str = Field(default="10% standard co-pay; pre-authorization required.")
    preauthorization_required: bool = True
    cashless_available: bool = True
    reimbursement_available: bool = True


