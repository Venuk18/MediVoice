import json
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.models.lab_order import LabOrder
from app.models.workflow_exception import WorkflowException
from app.models.audit_event import AuditEvent


def get_workflow_exceptions(
    db: Session,
    status_filter: Optional[str] = None,
    priority: Optional[str] = None,
    department: Optional[str] = None,
) -> List[WorkflowException]:
    query = select(WorkflowException)
    if status_filter:
        query = query.where(WorkflowException.status == status_filter)
    if priority:
        query = query.where(WorkflowException.priority == priority)
    if department:
        query = query.where(WorkflowException.responsible_department == department)
    query = query.order_by(WorkflowException.detected_at.desc())
    return list(db.scalars(query).all())


def get_workflow_exception_by_id(db: Session, exception_id: str) -> Optional[WorkflowException]:
    return db.scalars(
        select(WorkflowException).where(WorkflowException.id == exception_id)
    ).first()


def detect_overdue_lab_orders(db: Session, reference_time: Optional[datetime] = None) -> List[WorkflowException]:
    """
    Deterministic rule-based detection for lab orders exceeding turnaround.
    Checks orders in 'Pending' or 'Processing' where expected_completion_at < current_time.
    Idempotent: prevents duplicate OPEN exceptions for the same affected lab order.
    """
    now_utc = reference_time or datetime.now(timezone.utc)

    # Fetch candidate delayed lab orders
    query = select(LabOrder).where(
        LabOrder.workflow_status.in_(["Pending", "Processing"]),
        LabOrder.expected_completion_at < now_utc,
    )
    overdue_orders = db.scalars(query).all()

    created_exceptions: List[WorkflowException] = []

    for order in overdue_orders:
        # Check if an open or in-progress exception already exists for this order
        existing = db.scalars(
            select(WorkflowException).where(
                WorkflowException.affected_record_type == "LabOrder",
                WorkflowException.affected_record_id == order.id,
                WorkflowException.status.in_(["OPEN", "IN_PROGRESS"]),
            )
        ).first()

        if existing:
            continue  # Avoid duplicate tasks for the same open operational issue

        # Deterministic title and description based on operational data
        dept_name = order.ordering_department.name if order.ordering_department else "Central Diagnostics"
        exp_time_str = order.expected_completion_at.strftime("%Y-%m-%d %H:%M UTC")
        
        new_exception = WorkflowException(
            exception_type="LAB_ORDER_OVERDUE",
            title=f"Turnaround Exceeded: {order.test_category} ({order.patient_reference})",
            description=(
                f"Lab order for '{order.test_category}' (Patient: {order.patient_reference}) "
                f"was expected at {exp_time_str}. Current status remains '{order.workflow_status}' "
                f"under team '{order.assigned_team}'."
            ),
            priority="HIGH",
            responsible_department=dept_name,
            assigned_to=order.assigned_team,
            status="OPEN",
            affected_record_type="LabOrder",
            affected_record_id=order.id,
            detected_at=now_utc,
        )
        db.add(new_exception)
        db.flush()

        audit = AuditEvent(
            actor_reference="WORKFLOW_INTELLIGENCE",
            action="EXCEPTION_DETECTED",
            entity_type="WorkflowException",
            entity_id=new_exception.id,
            details=json.dumps({
                "exception_type": "LAB_ORDER_OVERDUE",
                "affected_record_id": order.id,
                "order_category": order.test_category,
            }),
        )
        db.add(audit)
        created_exceptions.append(new_exception)

    if created_exceptions:
        db.commit()
        for exc in created_exceptions:
            db.refresh(exc)

    return created_exceptions


def assign_exception(
    db: Session,
    exception_id: str,
    assigned_to: str,
    actor_reference: str = "OPERATIONS_COORDINATOR",
) -> WorkflowException:
    exc = get_workflow_exception_by_id(db, exception_id)
    if not exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow exception '{exception_id}' not found.",
        )

    exc.assigned_to = assigned_to
    if exc.status == "OPEN":
        exc.status = "IN_PROGRESS"

    audit = AuditEvent(
        actor_reference=actor_reference,
        action="EXCEPTION_ASSIGNED",
        entity_type="WorkflowException",
        entity_id=exc.id,
        details=json.dumps({"assigned_to": assigned_to, "status": exc.status}),
    )
    db.add(audit)
    db.commit()
    db.refresh(exc)
    return exc


def resolve_exception(
    db: Session,
    exception_id: str,
    resolution_note: str,
    actor_reference: str = "OPERATIONS_COORDINATOR",
) -> WorkflowException:
    """
    Resolves an exception only after recording investigation notes and checking the record.
    """
    exc = get_workflow_exception_by_id(db, exception_id)
    if not exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow exception '{exception_id}' not found.",
        )

    exc.status = "RESOLVED"
    exc.resolution_note = resolution_note
    exc.resolved_at = datetime.now(timezone.utc)

    audit = AuditEvent(
        actor_reference=actor_reference,
        action="EXCEPTION_RESOLVED",
        entity_type="WorkflowException",
        entity_id=exc.id,
        details=json.dumps({"resolution_note": resolution_note}),
    )
    db.add(audit)
    db.commit()
    db.refresh(exc)
    return exc


def get_audit_events(
    db: Session,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = 50,
) -> List[AuditEvent]:
    query = select(AuditEvent)
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditEvent.entity_id == entity_id)
    query = query.order_by(AuditEvent.created_at.desc()).limit(limit)
    return list(db.scalars(query).all())
