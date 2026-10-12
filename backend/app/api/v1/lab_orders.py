from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.lab_order import LabOrderRead, LabOrderStatusUpdate
from app.services import lab_service

router = APIRouter(prefix="/lab-orders", tags=["Lab Orders"])


def _to_lab_order_read(order) -> LabOrderRead:
    return LabOrderRead(
        id=order.id,
        patient_reference=order.patient_reference,
        ordering_department_id=order.ordering_department_id,
        test_category=order.test_category,
        workflow_status=order.workflow_status,
        expected_completion_at=order.expected_completion_at,
        assigned_team=order.assigned_team,
        delay_reason=order.delay_reason,
        created_at=order.created_at,
        updated_at=order.updated_at,
        department_name=order.ordering_department.name if order.ordering_department else None,
    )


@router.get("", response_model=List[LabOrderRead], summary="List lab orders")
def list_lab_orders(
    status: Optional[str] = Query(None, description="Workflow status (Pending, Processing, Completed, Delayed)"),
    department_id: Optional[str] = Query(None, description="Ordering department ID"),
    db: Session = Depends(get_db),
):
    """Retrieve lab orders metadata (no clinical results)."""
    orders = lab_service.get_lab_orders(
        db=db,
        workflow_status=status,
        ordering_department_id=department_id,
    )
    return [_to_lab_order_read(o) for o in orders]


@router.get("/{order_id}", response_model=LabOrderRead, summary="Get lab order by ID")
def get_lab_order(order_id: str, db: Session = Depends(get_db)):
    """Retrieve a single lab order."""
    order = lab_service.get_lab_order_by_id(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lab order '{order_id}' not found.",
        )
    return _to_lab_order_read(order)


@router.patch("/{order_id}/status", response_model=LabOrderRead, summary="Update lab order workflow status")
def update_status(
    order_id: str,
    payload: LabOrderStatusUpdate,
    db: Session = Depends(get_db),
):
    """Update lab order workflow stage (Pending, Processing, Completed, Delayed)."""
    order = lab_service.update_lab_order_status(
        db=db,
        order_id=order_id,
        workflow_status=payload.workflow_status,
        delay_reason=payload.delay_reason,
        actor_reference="LAB_COORDINATOR",
    )
    return _to_lab_order_read(order)
