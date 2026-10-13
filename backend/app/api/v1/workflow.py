from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.workflow import (
    WorkflowExceptionRead,
    WorkflowExceptionAssign,
    WorkflowExceptionResolve,
    AuditEventRead,
)
from app.services import workflow_service

router = APIRouter(prefix="/workflow", tags=["Workflow Intelligence"])


@router.get("/exceptions", response_model=List[WorkflowExceptionRead], summary="List workflow exceptions")
def list_exceptions(
    status: Optional[str] = Query(None, description="Status filter (OPEN, IN_PROGRESS, RESOLVED, DISMISSED)"),
    priority: Optional[str] = Query(None, description="Priority filter (LOW, MEDIUM, HIGH, CRITICAL)"),
    department: Optional[str] = Query(None, description="Responsible department filter"),
    db: Session = Depends(get_db),
):
    """Retrieve operational workflow exceptions."""
    return workflow_service.get_workflow_exceptions(
        db=db,
        status_filter=status,
        priority=priority,
        department=department,
    )


@router.post("/exceptions/detect", response_model=List[WorkflowExceptionRead], summary="Trigger overdue lab detection")
def run_overdue_detection(db: Session = Depends(get_db)):
    """
    Run deterministic rule-based evaluation of pending/processing lab orders
    whose expected completion has passed. Idempotent against open duplicates.
    """
    created = workflow_service.detect_overdue_lab_orders(db=db)
    return created


@router.post("/exceptions/{exception_id}/assign", response_model=WorkflowExceptionRead, summary="Assign exception")
def assign_exception_endpoint(
    exception_id: str,
    payload: WorkflowExceptionAssign,
    db: Session = Depends(get_db),
):
    """Assign exception to team or coordinator; transitions OPEN -> IN_PROGRESS."""
    return workflow_service.assign_exception(
        db=db,
        exception_id=exception_id,
        assigned_to=payload.assigned_to,
        actor_reference="OPERATIONS_COORDINATOR",
    )


@router.post("/exceptions/{exception_id}/resolve", response_model=WorkflowExceptionRead, summary="Resolve exception")
def resolve_exception_endpoint(
    exception_id: str,
    payload: WorkflowExceptionResolve,
    db: Session = Depends(get_db),
):
    """Resolves exception with mandatory investigation finding note."""
    return workflow_service.resolve_exception(
        db=db,
        exception_id=exception_id,
        resolution_note=payload.resolution_note,
        actor_reference="OPERATIONS_COORDINATOR",
    )


@router.get("/audit-events", response_model=List[AuditEventRead], summary="List audit events")
def list_audit_events(
    entity_type: Optional[str] = Query(None, description="Filter by entity type (Appointment, LabOrder, WorkflowException)"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Audit trail of all critical operations."""
    return workflow_service.get_audit_events(
        db=db,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )
