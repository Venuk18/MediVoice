import json
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from app.models.lab_order import LabOrder
from app.models.audit_event import AuditEvent


def get_lab_orders(
    db: Session,
    workflow_status: Optional[str] = None,
    ordering_department_id: Optional[str] = None,
) -> List[LabOrder]:
    query = select(LabOrder).options(joinedload(LabOrder.ordering_department))
    if workflow_status:
        query = query.where(LabOrder.workflow_status == workflow_status)
    if ordering_department_id:
        query = query.where(LabOrder.ordering_department_id == ordering_department_id)
    query = query.order_by(LabOrder.created_at.desc())
    return list(db.scalars(query).all())


def get_lab_order_by_id(db: Session, order_id: str) -> Optional[LabOrder]:
    query = (
        select(LabOrder)
        .options(joinedload(LabOrder.ordering_department))
        .where(LabOrder.id == order_id)
    )
    return db.scalars(query).first()


def update_lab_order_status(
    db: Session,
    order_id: str,
    workflow_status: str,
    delay_reason: Optional[str] = None,
    actor_reference: str = "LAB_STAFF",
) -> LabOrder:
    allowed_statuses = {"Pending", "Processing", "Completed", "Delayed"}
    if workflow_status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid workflow status '{workflow_status}'. Allowed: {sorted(list(allowed_statuses))}",
        )

    order = get_lab_order_by_id(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lab order '{order_id}' not found.",
        )

    prev_status = order.workflow_status
    order.workflow_status = workflow_status
    if delay_reason is not None:
        order.delay_reason = delay_reason

    audit_details = json.dumps({
        "previous_status": prev_status,
        "new_status": workflow_status,
        "delay_reason": delay_reason,
    })
    audit = AuditEvent(
        actor_reference=actor_reference,
        action="LAB_ORDER_STATUS_UPDATED",
        entity_type="LabOrder",
        entity_id=order.id,
        details=audit_details,
    )
    db.add(audit)
    db.commit()
    db.refresh(order)
    return order
