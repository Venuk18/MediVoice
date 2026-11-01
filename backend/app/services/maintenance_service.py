import json
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit_event import AuditEvent
from app.models.hospital import Hospital
from app.models.maintenance import (
    MaintenancePriority,
    MaintenanceStatus,
    MaintenanceWorkOrder,
)
from app.schemas.maintenance import (
    MaintenanceSummaryMetrics,
    MaintenanceWorkOrderCreate,
    MaintenanceWorkOrderRead,
    MaintenanceWorkOrderStatusUpdate,
)

VALID_PRIORITIES = {p.value for p in MaintenancePriority}
VALID_STATUSES = {s.value for s in MaintenanceStatus}

# Explicit validated state machine for maintenance work orders
ALLOWED_STATUS_TRANSITIONS: Dict[str, List[str]] = {
    MaintenanceStatus.OPEN.value: [
        MaintenanceStatus.ASSIGNED.value,
        MaintenanceStatus.IN_PROGRESS.value,
        MaintenanceStatus.RESOLVED.value,
    ],
    MaintenanceStatus.ASSIGNED.value: [
        MaintenanceStatus.IN_PROGRESS.value,
        MaintenanceStatus.RESOLVED.value,
        MaintenanceStatus.OPEN.value,
    ],
    MaintenanceStatus.IN_PROGRESS.value: [
        MaintenanceStatus.RESOLVED.value,
        MaintenanceStatus.ASSIGNED.value,
    ],
    MaintenanceStatus.RESOLVED.value: [
        MaintenanceStatus.OPEN.value,
    ],
}


def to_maintenance_read(order: MaintenanceWorkOrder) -> MaintenanceWorkOrderRead:
    allowed_next = ALLOWED_STATUS_TRANSITIONS.get(order.status, [])
    return MaintenanceWorkOrderRead(
        id=order.id,
        hospital_id=order.hospital_id,
        work_order_code=order.work_order_code,
        title=order.title,
        description=order.description,
        category=order.category,
        location=order.location,
        equipment_reference=order.equipment_reference,
        priority=order.priority,
        status=order.status,
        reported_by=order.reported_by,
        assigned_to=order.assigned_to,
        resolution_notes=order.resolution_notes,
        allowed_next_statuses=allowed_next,
        created_at=order.created_at,
        updated_at=order.updated_at,
        resolved_at=order.resolved_at,
    )


def _generate_work_order_code(db: Session) -> str:
    for _ in range(25):
        candidate = f"MWO-2026-{secrets.randbelow(9000) + 1000}"
        existing = db.scalars(
            select(MaintenanceWorkOrder).where(
                MaintenanceWorkOrder.work_order_code == candidate
            )
        ).first()
        if not existing:
            return candidate
    return f"MWO-2026-{int(datetime.now(timezone.utc).timestamp()) % 100000:05d}"


def _resolve_hospital_id(db: Session, requested_hospital_id: Optional[str]) -> str:
    if requested_hospital_id and requested_hospital_id.strip():
        hosp = db.scalars(
            select(Hospital).where(Hospital.id == requested_hospital_id.strip())
        ).first()
        if hosp:
            return hosp.id
    first_hosp = db.scalars(select(Hospital)).first()
    if first_hosp:
        return first_hosp.id
    return settings.DEFAULT_HOSPITAL_ID


def list_work_orders(
    db: Session,
    status_filter: Optional[str] = None,
    priority_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    search_query: Optional[str] = None,
) -> List[MaintenanceWorkOrderRead]:
    stmt = select(MaintenanceWorkOrder)
    if status_filter and status_filter.strip():
        stmt = stmt.where(MaintenanceWorkOrder.status == status_filter.strip().upper())
    if priority_filter and priority_filter.strip():
        stmt = stmt.where(
            MaintenanceWorkOrder.priority == priority_filter.strip().upper()
        )
    if category_filter and category_filter.strip():
        stmt = stmt.where(MaintenanceWorkOrder.category == category_filter.strip())

    stmt = stmt.order_by(MaintenanceWorkOrder.created_at.desc())
    orders = list(db.scalars(stmt).all())

    if search_query and search_query.strip():
        q = search_query.strip().lower()
        orders = [
            o
            for o in orders
            if q in (o.work_order_code or "").lower()
            or q in (o.title or "").lower()
            or q in (o.description or "").lower()
            or q in (o.location or "").lower()
            or q in (o.equipment_reference or "").lower()
            or q in (o.assigned_to or "").lower()
            or q in (o.category or "").lower()
        ]

    return [to_maintenance_read(o) for o in orders]


def get_work_order_by_id(
    db: Session, work_order_id: str
) -> MaintenanceWorkOrder:
    order = db.scalars(
        select(MaintenanceWorkOrder).where(MaintenanceWorkOrder.id == work_order_id)
    ).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Maintenance work order '{work_order_id}' not found.",
        )
    return order


def get_maintenance_summary(db: Session) -> MaintenanceSummaryMetrics:
    orders = list(db.scalars(select(MaintenanceWorkOrder)).all())
    open_c = sum(1 for o in orders if o.status == MaintenanceStatus.OPEN.value)
    assigned_c = sum(1 for o in orders if o.status == MaintenanceStatus.ASSIGNED.value)
    in_prog_c = sum(1 for o in orders if o.status == MaintenanceStatus.IN_PROGRESS.value)
    resolved_c = sum(1 for o in orders if o.status == MaintenanceStatus.RESOLVED.value)
    crit_active = sum(
        1
        for o in orders
        if o.status != MaintenanceStatus.RESOLVED.value
        and o.priority == MaintenancePriority.CRITICAL.value
    )
    high_active = sum(
        1
        for o in orders
        if o.status != MaintenanceStatus.RESOLVED.value
        and o.priority == MaintenancePriority.HIGH.value
    )
    return MaintenanceSummaryMetrics(
        total_work_orders=len(orders),
        open_count=open_c,
        assigned_count=assigned_c,
        in_progress_count=in_prog_c,
        resolved_count=resolved_c,
        critical_active_count=crit_active,
        high_active_count=high_active,
    )


def create_work_order(
    db: Session,
    payload: MaintenanceWorkOrderCreate,
    actor_reference: str = "MAINTENANCE_STAFF",
) -> MaintenanceWorkOrderRead:
    priority_val = (payload.priority or "MEDIUM").strip().upper()
    if priority_val not in VALID_PRIORITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid priority '{payload.priority}'. Allowed: {sorted(VALID_PRIORITIES)}",
        )

    assigned_clean = payload.assigned_to.strip() if payload.assigned_to and payload.assigned_to.strip() else None
    initial_status = (
        MaintenanceStatus.ASSIGNED.value
        if assigned_clean
        else MaintenanceStatus.OPEN.value
    )

    try:
        hosp_id = _resolve_hospital_id(db, payload.hospital_id)
        code = _generate_work_order_code(db)
        order = MaintenanceWorkOrder(
            hospital_id=hosp_id,
            work_order_code=code,
            title=payload.title.strip(),
            description=payload.description.strip(),
            category=(payload.category or "Facility & Safety").strip(),
            location=payload.location.strip(),
            equipment_reference=payload.equipment_reference.strip()
            if payload.equipment_reference and payload.equipment_reference.strip()
            else None,
            priority=priority_val,
            status=initial_status,
            reported_by=(payload.reported_by or actor_reference).strip(),
            assigned_to=assigned_clean,
        )
        db.add(order)
        db.flush()

        audit = AuditEvent(
            actor_reference=actor_reference,
            action="MAINTENANCE_WORK_ORDER_CREATED",
            entity_type="MaintenanceWorkOrder",
            entity_id=order.id,
            details=json.dumps(
                {
                    "work_order_code": order.work_order_code,
                    "title": order.title,
                    "category": order.category,
                    "location": order.location,
                    "priority": order.priority,
                    "status": order.status,
                    "assigned_to": order.assigned_to,
                }
            ),
        )
        db.add(audit)
        db.commit()
        db.refresh(order)
        return to_maintenance_read(order)
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while creating maintenance work order.",
        ) from exc


def update_work_order_status(
    db: Session,
    work_order_id: str,
    payload: MaintenanceWorkOrderStatusUpdate,
    actor_reference: str = "MAINTENANCE_STAFF",
) -> MaintenanceWorkOrderRead:
    target_status = (payload.status or "").strip().upper()
    if target_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid maintenance status '{payload.status}'. Allowed: {sorted(VALID_STATUSES)}",
        )

    order = get_work_order_by_id(db, work_order_id)
    current_status = order.status

    allowed_targets = ALLOWED_STATUS_TRANSITIONS.get(current_status, [])
    if target_status != current_status and target_status not in allowed_targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_STATUS_TRANSITION",
                "message": (
                    f"Cannot transition maintenance work order from '{current_status}' to '{target_status}'. "
                    f"Allowed next statuses: {allowed_targets}."
                ),
                "current_status": current_status,
                "requested_status": target_status,
                "allowed_next_statuses": allowed_targets,
            },
        )

    effective_assignee = (
        payload.assigned_to.strip()
        if payload.assigned_to is not None and payload.assigned_to.strip()
        else order.assigned_to
    )
    if target_status in (
        MaintenanceStatus.ASSIGNED.value,
        MaintenanceStatus.IN_PROGRESS.value,
    ) and not effective_assignee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "ASSIGNEE_REQUIRED",
                "message": f"An assigned engineer or team ('assigned_to') is required when moving to '{target_status}'.",
            },
        )

    effective_notes = (
        payload.resolution_notes.strip()
        if payload.resolution_notes is not None and payload.resolution_notes.strip()
        else order.resolution_notes
    )
    if target_status == MaintenanceStatus.RESOLVED.value and not effective_notes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "RESOLUTION_NOTES_REQUIRED",
                "message": "Resolution notes are required when marking a maintenance work order as RESOLVED.",
            },
        )

    try:
        now_utc = datetime.now(timezone.utc)
        order.status = target_status
        order.assigned_to = effective_assignee
        if effective_notes is not None:
            order.resolution_notes = effective_notes
        if target_status == MaintenanceStatus.RESOLVED.value:
            order.resolved_at = now_utc
        elif target_status == MaintenanceStatus.OPEN.value:
            order.resolved_at = None

        audit = AuditEvent(
            actor_reference=actor_reference,
            action="MAINTENANCE_WORK_ORDER_UPDATED",
            entity_type="MaintenanceWorkOrder",
            entity_id=order.id,
            details=json.dumps(
                {
                    "work_order_code": order.work_order_code,
                    "previous_status": current_status,
                    "new_status": target_status,
                    "assigned_to": order.assigned_to,
                    "resolution_notes": order.resolution_notes,
                }
            ),
        )
        db.add(audit)
        db.commit()
        db.refresh(order)
        return to_maintenance_read(order)
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while updating maintenance work order.",
        ) from exc
