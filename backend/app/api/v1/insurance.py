from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.security import StaffRole, require_staff_roles
from app.db.session import get_db
from app.schemas.insurance import (
    InsuranceDeskContactRead,
    InsuranceProviderManageCreate,
    InsuranceProviderRead,
    InsuranceSearchResponse,
    InsuranceSupportTicketCreate,
    InsuranceSupportTicketRead,
)
from app.services import insurance_service

router = APIRouter(prefix="/insurance", tags=["Hospital Insurance (Synthetic Demo)"])


@router.get(
    "/providers",
    response_model=List[InsuranceProviderRead],
    summary="List active synthetic insurance providers and plans",
)
def list_insurance_providers(db: Session = Depends(get_db)):
    """Retrieve all active synthetic insurance providers and their active plans."""
    return insurance_service.list_active_insurance_providers(db)


@router.post(
    "/providers",
    response_model=InsuranceProviderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new synthetic insurance provider and plan",
)
def create_insurance_provider(
    payload: InsuranceProviderManageCreate,
    db: Session = Depends(get_db),
    staff: Optional[Dict[str, Optional[str]]] = Depends(
        require_staff_roles([StaffRole.MAINTENANCE_STAFF, StaffRole.ADMIN])
    ),
):
    """Creates a new active synthetic insurance provider and initial plan."""
    actor = f"{staff.get('username')}:{staff.get('role')}" if staff else "MAINTENANCE_ADMIN"
    return insurance_service.create_insurance_provider_with_plan(
        db=db, payload=payload, actor_reference=actor
    )


@router.delete(
    "/providers/{provider_id}",
    summary="Remove (deactivate) an insurance provider from active hospital list",
)
def remove_insurance_provider(
    provider_id: str,
    db: Session = Depends(get_db),
    staff: Optional[Dict[str, Optional[str]]] = Depends(
        require_staff_roles([StaffRole.MAINTENANCE_STAFF, StaffRole.ADMIN])
    ),
):
    """Deactivates a synthetic insurance provider and its plans."""
    actor = f"{staff.get('username')}:{staff.get('role')}" if staff else "MAINTENANCE_ADMIN"
    return insurance_service.deactivate_insurance_provider(
        db=db, provider_id=provider_id, actor_reference=actor
    )



@router.get(
    "/providers/{provider_id}/plans",
    response_model=InsuranceProviderRead,
    summary="Retrieve active plans for a synthetic insurance provider",
)
def get_provider_plans(provider_id: str, db: Session = Depends(get_db)):
    """Retrieve a specific active insurance provider and all its active plans."""
    return insurance_service.get_provider_with_active_plans(db, provider_id=provider_id)


@router.get(
    "/search",
    response_model=InsuranceSearchResponse,
    summary="Search synthetic insurance providers and plans by provider, plan type, service, or cashless",
)
def search_insurance_providers_and_plans(
    provider_name: Optional[str] = Query(None, description="Filter by insurance provider name"),
    plan_type: Optional[str] = Query(None, description="Filter by plan type (e.g., Senior Citizen, Family Floater)"),
    service: Optional[str] = Query(None, description="Filter by covered service (e.g., OPD, Cardiology)"),
    cashless: Optional[bool] = Query(None, description="Filter by cashless availability (true/false)"),
    q: Optional[str] = Query(None, description="General search query"),
    db: Session = Depends(get_db),
):
    """
    Search active synthetic insurance providers and plans.
    Always returns the mandatory non-guarantee coverage disclaimer and hospital insurance desk contact details.
    """
    return insurance_service.search_insurance(
        db=db,
        provider_name=provider_name,
        plan_type=plan_type,
        service=service,
        cashless=cashless,
        query=q,
    )


@router.get(
    "/contact",
    response_model=InsuranceDeskContactRead,
    summary="Get hospital insurance desk contact information and coverage disclaimer",
)
def get_insurance_contact():
    """Return approved synthetic contact details for the Aarogya One Hospital Insurance & TPA Helpdesk."""
    return insurance_service.get_insurance_desk_contact()


@router.post(
    "/support-tickets",
    response_model=InsuranceSupportTicketRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a human-support ticket for policy-specific or unanswered insurance inquiries",
)
def create_support_ticket_endpoint(
    payload: InsuranceSupportTicketCreate,
    db: Session = Depends(get_db),
):
    """
    Creates a persisted human-support ticket routed to the Aarogya One Hospital Insurance & TPA Helpdesk
    via the WorkflowException workflow and logs an AuditEvent.
    """
    return insurance_service.create_insurance_support_ticket(db=db, payload=payload)


@router.get(
    "/support-tickets",
    response_model=List[InsuranceSupportTicketRead],
    summary="List human-support insurance escalation tickets",
)
def list_support_tickets_endpoint(
    patient_reference: Optional[str] = Query(None, description="Optional filter by synthetic patient reference"),
    db: Session = Depends(get_db),
    staff: Optional[Dict[str, Optional[str]]] = Depends(
        require_staff_roles(
            [StaffRole.DOCTOR, StaffRole.LAB_OPERATOR, StaffRole.MAINTENANCE_STAFF],
        )
    ),
):
    """Retrieve persisted human-support tickets for authenticated staff only."""
    return insurance_service.list_insurance_support_tickets(
        db=db,
        patient_reference=patient_reference,
    )


