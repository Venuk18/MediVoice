from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.insurance import (
    InsuranceDeskContactRead,
    InsuranceProviderRead,
    InsuranceSearchResponse,
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
