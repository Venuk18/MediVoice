from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.security import StaffRole, require_staff_roles
from app.db.session import get_db
from app.schemas.maintenance import (
    MaintenanceSummaryMetrics,
    MaintenanceWorkOrderCreate,
    MaintenanceWorkOrderRead,
    MaintenanceWorkOrderStatusUpdate,
)
from app.services import maintenance_service

router = APIRouter(prefix="/maintenance", tags=["Hospital Facilities & Maintenance"])

_require_maintenance_role = require_staff_roles(
    [StaffRole.MAINTENANCE_STAFF],
    strict_unauthenticated=True,
)


@router.get(
    "/summary",
    response_model=MaintenanceSummaryMetrics,
    summary="Retrieve hospital facilities and maintenance summary metrics",
)
def get_maintenance_summary_endpoint(
    db: Session = Depends(get_db),
    _claims=Depends(_require_maintenance_role),
):
    """Returns counts of open, assigned, in-progress, resolved, and critical maintenance work orders."""
    return maintenance_service.get_maintenance_summary(db)


@router.get(
    "/work-orders",
    response_model=List[MaintenanceWorkOrderRead],
    summary="List and filter hospital maintenance work orders",
)
def list_work_orders_endpoint(
    status: Optional[str] = Query(None, description="Filter by status (OPEN, ASSIGNED, IN_PROGRESS, RESOLVED)"),
    priority: Optional[str] = Query(None, description="Filter by priority (LOW, MEDIUM, HIGH, CRITICAL)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    q: Optional[str] = Query(None, description="Search work order code, title, location, equipment, or assignee"),
    db: Session = Depends(get_db),
    _claims=Depends(_require_maintenance_role),
):
    """Retrieve hospital maintenance work orders with optional filters (protected for MAINTENANCE_STAFF / ADMIN)."""
    return maintenance_service.list_work_orders(
        db=db,
        status_filter=status,
        priority_filter=priority,
        category_filter=category,
        search_query=q,
    )


@router.get(
    "/work-orders/{work_order_id}",
    response_model=MaintenanceWorkOrderRead,
    summary="Get maintenance work order by ID",
)
def get_work_order_endpoint(
    work_order_id: str,
    db: Session = Depends(get_db),
    _claims=Depends(_require_maintenance_role),
):
    """Retrieve a single maintenance work order by ID."""
    order = maintenance_service.get_work_order_by_id(db, work_order_id)
    return maintenance_service.to_maintenance_read(order)


@router.post(
    "/work-orders",
    response_model=MaintenanceWorkOrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new hospital maintenance work order",
)
def create_work_order_endpoint(
    payload: MaintenanceWorkOrderCreate,
    db: Session = Depends(get_db),
    claims=Depends(_require_maintenance_role),
):
    """Creates a persisted maintenance work order and logs an audit event."""
    actor = claims.get("display_name") or claims.get("username") or "MAINTENANCE_STAFF"
    return maintenance_service.create_work_order(
        db=db,
        payload=payload,
        actor_reference=actor,
    )


@router.patch(
    "/work-orders/{work_order_id}/status",
    response_model=MaintenanceWorkOrderRead,
    summary="Update maintenance work order status, staff assignment, and resolution notes",
)
def update_work_order_status_endpoint(
    work_order_id: str,
    payload: MaintenanceWorkOrderStatusUpdate,
    db: Session = Depends(get_db),
    claims=Depends(_require_maintenance_role),
):
    """Validates and executes a maintenance work order lifecycle transition (OPEN -> ASSIGNED -> IN_PROGRESS -> RESOLVED)."""
    actor = claims.get("display_name") or claims.get("username") or "MAINTENANCE_STAFF"
    return maintenance_service.update_work_order_status(
        db=db,
        work_order_id=work_order_id,
        payload=payload,
        actor_reference=actor,
    )
