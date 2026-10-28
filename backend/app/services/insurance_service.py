from datetime import datetime, timezone
import json
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.models.audit_event import AuditEvent
from app.models.insurance import InsuranceProvider, InsurancePlan
from app.models.workflow_exception import WorkflowException
from app.schemas.insurance import (
    INSURANCE_COVERAGE_DISCLAIMER,
    InsuranceDeskContactRead,
    InsurancePlanRead,
    InsuranceProviderRead,
    InsuranceSearchResponse,
    InsuranceSupportTicketCreate,
    InsuranceSupportTicketRead,
)


def _split_services(raw: str) -> List[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _to_plan_read(plan: InsurancePlan, provider_name: Optional[str] = None) -> InsurancePlanRead:
    resolved_provider_name = provider_name or (plan.provider.name if plan.provider else None)
    return InsurancePlanRead(
        id=plan.id,
        provider_id=plan.provider_id,
        provider_name=resolved_provider_name,
        plan_name=plan.plan_name,
        plan_type=plan.plan_type,
        coverage_summary=plan.coverage_summary,
        covered_services=plan.covered_services,
        supported_services=plan.covered_services,
        supported_services_list=_split_services(plan.covered_services),
        coverage_notes=plan.coverage_summary,
        copay_summary=plan.copay_summary,
        exclusions_and_limitations=plan.exclusions_and_limitations,
        preauthorization_required=plan.preauthorization_required,
        cashless_available=plan.cashless_available,
        reimbursement_available=plan.reimbursement_available,
        network_notes=plan.network_notes,
        is_active=plan.is_active,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def _to_provider_read(provider: InsuranceProvider, active_plans_only: bool = True) -> InsuranceProviderRead:
    plans = [
        _to_plan_read(p, provider_name=provider.name)
        for p in (provider.plans or [])
        if (not active_plans_only or p.is_active)
    ]
    return InsuranceProviderRead(
        id=provider.id,
        hospital_id=provider.hospital_id,
        name=provider.name,
        provider_name=provider.name,
        code=provider.code,
        support_contact=provider.support_contact,
        contact_number=provider.support_contact,
        desk_location=provider.desk_location,
        contact_hours=provider.contact_hours,
        is_active=provider.is_active,
        is_synthetic_demo=provider.is_synthetic_demo,
        plans=plans,
        disclaimer=INSURANCE_COVERAGE_DISCLAIMER,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


def get_insurance_desk_contact() -> InsuranceDeskContactRead:
    return InsuranceDeskContactRead()


def list_active_insurance_providers(db: Session) -> List[InsuranceProviderRead]:
    """Returns all active synthetic insurance providers and their active plans."""
    try:
        stmt = (
            select(InsuranceProvider)
            .options(joinedload(InsuranceProvider.plans))
            .where(InsuranceProvider.is_active.is_(True))
            .order_by(InsuranceProvider.name)
        )
        providers = list(db.scalars(stmt).unique().all())
        return [_to_provider_read(p, active_plans_only=True) for p in providers]
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while retrieving insurance providers.",
        ) from exc


def get_provider_with_active_plans(db: Session, provider_id: str) -> InsuranceProviderRead:
    """Returns a single active insurance provider and its active plans, or raises 404."""
    clean_id = (provider_id or "").strip()
    if not clean_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider ID is required.",
        )
    try:
        provider = db.scalars(
            select(InsuranceProvider)
            .options(joinedload(InsuranceProvider.plans))
            .where(
                InsuranceProvider.id == clean_id,
                InsuranceProvider.is_active.is_(True),
            )
        ).unique().first()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while retrieving provider plans.",
        ) from exc

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active insurance provider '{clean_id}' not found.",
        )

    return _to_provider_read(provider, active_plans_only=True)


def get_provider_plans(db: Session, provider_id: str) -> List[InsurancePlanRead]:
    """Returns active plans list for a specific active insurance provider."""
    prov = get_provider_with_active_plans(db, provider_id=provider_id)
    return prov.plans


def search_insurance(
    db: Session,
    provider_name: Optional[str] = None,
    plan_type: Optional[str] = None,
    service: Optional[str] = None,
    cashless: Optional[bool] = None,
    query: Optional[str] = None,
) -> InsuranceSearchResponse:
    """
    Searches active synthetic insurance providers and active plans by provider_name,
    plan_type, covered service, cashless availability, or general query string.
    Always excludes inactive providers and inactive plans.
    """
    active_providers = list_active_insurance_providers(db)

    prov_filter = (provider_name or "").strip().lower()
    type_filter = (plan_type or "").strip().lower()
    srv_filter = (service or "").strip().lower()
    q_filter = (query or "").strip().lower()

    matched_providers: List[InsuranceProviderRead] = []
    matched_plans: List[InsurancePlanRead] = []

    for prov in active_providers:
        if prov_filter and prov_filter not in prov.name.lower() and prov_filter not in prov.code.lower():
            continue

        prov_matching_plans: List[InsurancePlanRead] = []
        for pl in prov.plans:
            if type_filter and type_filter not in pl.plan_type.lower() and type_filter not in pl.plan_name.lower():
                continue

            if srv_filter:
                srv_blob = f"{pl.covered_services} {pl.coverage_summary} {pl.plan_name}".lower()
                if srv_filter not in srv_blob:
                    continue

            if cashless is not None and pl.cashless_available != cashless:
                continue

            if q_filter:
                full_blob = (
                    f"{prov.name} {prov.code} {pl.plan_name} {pl.plan_type} "
                    f"{pl.coverage_summary} {pl.covered_services}"
                ).lower()
                if q_filter not in full_blob:
                    continue

            prov_matching_plans.append(pl)
            matched_plans.append(pl)

        if prov_matching_plans:
            matched_providers.append(prov.model_copy(update={"plans": prov_matching_plans}))

    desk = get_insurance_desk_contact()
    return InsuranceSearchResponse(
        matched_count=len(matched_providers),
        query=query,
        provider_name=provider_name,
        plan_type=plan_type,
        service=service,
        cashless=cashless,
        providers=matched_providers,
        matching_plans=matched_plans,
        insurance_desk_contact=desk,
        insurance_desk=desk,
        is_synthetic_demo=True,
        disclaimer=INSURANCE_COVERAGE_DISCLAIMER,
    )


def search_hospital_insurance_tool(
    db: Session,
    provider_name: Optional[str] = None,
    plan_type: Optional[str] = None,
    service: Optional[str] = None,
    cashless: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Allowlisted AI Agent tool interface for searching Aarogya One Hospital's synthetic
    insurance providers, plans, supported services, co-pay, pre-authorization, and desk contact info.
    """
    res = search_insurance(
        db=db,
        provider_name=provider_name,
        plan_type=plan_type,
        service=service,
        cashless=cashless,
    )
    return {
        "matched_count": res.matched_count,
        "provider_name": res.provider_name,
        "plan_type": res.plan_type,
        "service": res.service,
        "cashless": res.cashless,
        "providers": [
            {
                "id": p.id,
                "name": p.name,
                "provider_name": p.name,
                "code": p.code,
                "support_contact": p.support_contact,
                "desk_location": p.desk_location,
                "contact_hours": p.contact_hours,
                "is_active": p.is_active,
                "plans": [
                    {
                        "id": pl.id,
                        "plan_name": pl.plan_name,
                        "plan_type": pl.plan_type,
                        "coverage_summary": pl.coverage_summary,
                        "covered_services": pl.covered_services,
                        "copay_summary": pl.copay_summary,
                        "preauthorization_required": pl.preauthorization_required,
                        "cashless_available": pl.cashless_available,
                        "reimbursement_available": pl.reimbursement_available,
                        "network_notes": pl.network_notes,
                    }
                    for pl in p.plans
                ],
            }
            for p in res.providers
        ],
        "insurance_desk_contact": {
            "department": res.insurance_desk_contact.department,
            "phone": res.insurance_desk_contact.phone,
            "location": res.insurance_desk_contact.location,
            "hours": res.insurance_desk_contact.hours,
        },
        "is_synthetic_demo": True,
        "disclaimer": res.disclaimer,
    }


def create_insurance_support_ticket(
    db: Session,
    payload: InsuranceSupportTicketCreate,
) -> InsuranceSupportTicketRead:
    """
    Creates a real persisted human-support ticket via the WorkflowException & AuditEvent
    workflow when a patient's policy-specific question cannot be answered from synthetic
    plan documents.
    """
    pat_ref = (payload.patient_reference or "PAT-2026-4409").strip()
    prov = payload.provider_name.strip() if payload.provider_name else None
    plan = payload.plan_name.strip() if payload.plan_name else None
    question = payload.question.strip()

    context_label = f"{prov} ({plan})" if prov and plan else (prov or plan or "Unlisted / Policy Verification")
    title = f"Insurance Desk Escalation: {context_label} ({pat_ref})"
    description = (
        f"Patient Reference: {pat_ref}\n"
        f"Provider / Plan: {context_label}\n"
        f"Preferred Follow-Up: {payload.contact_preference or 'Hospital Insurance Desk'}\n"
        f"Patient Question: {question}"
    )

    try:
        now_utc = datetime.now(timezone.utc)
        exc = WorkflowException(
            exception_type="INSURANCE_SUPPORT_TICKET",
            title=title[:255],
            description=description,
            priority="MEDIUM",
            responsible_department="Insurance & TPA Helpdesk",
            assigned_to="TPA Verification Coordinator",
            status="OPEN",
            affected_record_type="InsuranceInquiry",
            affected_record_id=pat_ref,
            detected_at=now_utc,
        )
        db.add(exc)
        db.flush()

        audit = AuditEvent(
            actor_reference=pat_ref,
            action="INSURANCE_SUPPORT_TICKET_CREATED",
            entity_type="WorkflowException",
            entity_id=exc.id,
            details=json.dumps(
                {
                    "patient_reference": pat_ref,
                    "provider_name": prov,
                    "plan_name": plan,
                    "question": question,
                }
            ),
        )
        db.add(audit)
        db.commit()
        db.refresh(exc)

        return InsuranceSupportTicketRead(
            ticket_id=exc.id,
            patient_reference=pat_ref,
            provider_name=prov,
            plan_name=plan,
            question=question,
            status=exc.status,
            priority=exc.priority,
            assigned_department=exc.responsible_department,
            created_at=exc.detected_at or now_utc,
            disclaimer=INSURANCE_COVERAGE_DISCLAIMER,
        )
    except SQLAlchemyError as exc_err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while creating insurance support ticket.",
        ) from exc_err


def list_insurance_support_tickets(
    db: Session,
    patient_reference: Optional[str] = None,
) -> List[InsuranceSupportTicketRead]:
    stmt = select(WorkflowException).where(
        WorkflowException.exception_type == "INSURANCE_SUPPORT_TICKET"
    )
    if patient_reference and patient_reference.strip():
        stmt = stmt.where(
            WorkflowException.affected_record_id == patient_reference.strip()
        )
    stmt = stmt.order_by(WorkflowException.detected_at.desc())
    rows = list(db.scalars(stmt).all())
    results: List[InsuranceSupportTicketRead] = []
    for r in rows:
        results.append(
            InsuranceSupportTicketRead(
                ticket_id=r.id,
                patient_reference=r.affected_record_id,
                provider_name=None,
                plan_name=None,
                question=r.description,
                status=r.status,
                priority=r.priority,
                assigned_department=r.responsible_department,
                created_at=r.detected_at,
                disclaimer=INSURANCE_COVERAGE_DISCLAIMER,
            )
        )
    return results


def create_insurance_provider_with_plan(
    db: Session,
    payload: Any,
    actor_reference: str = "MAINTENANCE_ADMIN",
) -> InsuranceProviderRead:
    """Create a new synthetic insurance provider and initial plan."""
    import uuid
    from app.models.hospital import Hospital

    hosp = db.scalars(select(Hospital)).first()
    hospital_id = hosp.id if hosp else payload.hospital_id

    prov_id = str(uuid.uuid4())
    provider = InsuranceProvider(
        id=prov_id,
        hospital_id=hospital_id,
        name=payload.name.strip(),
        code=payload.code.strip().upper(),
        support_contact=payload.support_contact.strip(),
        desk_location=payload.desk_location.strip(),
        contact_hours=payload.contact_hours.strip(),
        is_active=True,
        is_synthetic_demo=True,
    )
    db.add(provider)
    db.flush()

    plan = InsurancePlan(
        id=str(uuid.uuid4()),
        provider_id=provider.id,
        plan_name=payload.plan_name.strip(),
        plan_type=payload.plan_type.strip(),
        coverage_summary=payload.coverage_summary.strip(),
        covered_services=payload.covered_services.strip(),
        copay_summary=payload.copay_summary.strip(),
        preauthorization_required=payload.preauthorization_required,
        cashless_available=payload.cashless_available,
        reimbursement_available=payload.reimbursement_available,
        is_active=True,
    )
    db.add(plan)
    db.add(
        AuditEvent(
            actor_reference=actor_reference,
            action="INSURANCE_PROVIDER_CREATED",
            entity_type="InsuranceProvider",
            entity_id=provider.id,
            details=f"Added synthetic insurance provider {provider.name} ({provider.code}) with plan {plan.plan_name}.",
        )
    )
    db.commit()
    return get_provider_with_active_plans(db, provider.id)


def deactivate_insurance_provider(
    db: Session,
    provider_id: str,
    actor_reference: str = "MAINTENANCE_ADMIN",
) -> Dict[str, Any]:
    """Deactivate an insurance provider and its associated plans."""
    provider = db.scalars(
        select(InsuranceProvider)
        .options(joinedload(InsuranceProvider.plans))
        .where(InsuranceProvider.id == provider_id)
    ).unique().first()
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Insurance provider '{provider_id}' not found.",
        )
    provider.is_active = False
    for pl in provider.plans or []:
        pl.is_active = False
    db.add(
        AuditEvent(
            actor_reference=actor_reference,
            action="INSURANCE_PROVIDER_REMOVED",
            entity_type="InsuranceProvider",
            entity_id=provider.id,
            details=f"Deactivated insurance provider {provider.name} ({provider.code}).",
        )
    )
    db.commit()
    return {"id": provider.id, "name": provider.name, "is_active": False}


