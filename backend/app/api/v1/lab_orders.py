from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.security import StaffRole, require_staff_roles
from app.db.session import get_db
from app.schemas.lab_order import (
    LabOrderCreate,
    LabOrderDemoPortalRead,
    LabOrderRead,
    LabOrderStatusUpdate,
    LabVerificationRequest,
    LabVerificationResponse,
)
from app.services import lab_service

router = APIRouter(prefix="/lab-orders", tags=["Lab Orders"])

_require_lab_operator_role = require_staff_roles(
    [StaffRole.LAB_OPERATOR],
    strict_unauthenticated=True,
)
_require_lab_or_doctor_role = require_staff_roles(
    [StaffRole.LAB_OPERATOR, StaffRole.DOCTOR],
    strict_unauthenticated=True,
)


_require_any_staff_role = require_staff_roles(
    [StaffRole.DOCTOR, StaffRole.LAB_OPERATOR, StaffRole.MAINTENANCE_STAFF, StaffRole.ADMIN],
)


def _to_lab_order_read(order) -> LabOrderRead:
    return LabOrderRead(
        id=order.id,
        patient_reference=order.patient_reference,
        ordering_department_id=order.ordering_department_id,
        test_category=order.test_category,
        test_name=order.display_test_name,
        workflow_status=order.workflow_status,
        lab_status=order.lab_status,
        expected_completion_at=order.expected_completion_at,
        assigned_team=order.assigned_team,
        delay_reason=order.delay_reason,
        created_at=order.created_at,
        updated_at=order.updated_at,
        department_name=order.ordering_department.name if order.ordering_department else None,
    )


@router.get("", response_model=List[LabOrderRead], summary="List lab orders (staff queue without verification codes)")
def list_lab_orders(
    status: Optional[str] = Query(None, description="Workflow status filter"),
    department_id: Optional[str] = Query(None, description="Ordering department ID"),
    db: Session = Depends(get_db),
    _claims=Depends(_require_any_staff_role),
):
    """Retrieve lab orders metadata for authorized hospital staff (no clinical results and no verification codes)."""
    orders = lab_service.get_lab_orders(
        db=db,
        workflow_status=status,
        ordering_department_id=department_id,
    )
    return [_to_lab_order_read(o) for o in orders]


@router.post(
    "",
    response_model=LabOrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create synthetic lab order (excludes verification code in public response)",
)
def create_lab_order_endpoint(
    payload: LabOrderCreate,
    db: Session = Depends(get_db),
    _claims=Depends(_require_lab_or_doctor_role),
):
    """
    Creates a synthetic lab order and generates a unique six-digit verification code.
    Protected by LAB_OPERATOR / DOCTOR role authorization.
    The verification code is excluded from public lab-order responses. Patients use the private
    code provided on their receipt to check the current processing stage.
    """
    order = lab_service.create_lab_order(db=db, payload=payload)
    return _to_lab_order_read(order)


@router.post(
    "/verify-status",
    response_model=LabVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify six-digit lab code and retrieve patient-safe order status",
)
def verify_lab_order_status(
    payload: LabVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Submits a six-digit verification code and retrieves only permitted lab order status metadata
    (test name, current status, patient-friendly explanation, next step, and last-updated time).
    Enforces per-client and per-session rate limiting on failed verification attempts.
    """
    client_host = request.client.host if request.client else "unknown_client"
    return lab_service.verify_lab_order_by_code(
        db=db,
        verification_code=payload.verification_code,
        client_identifier=client_host,
        session_id=payload.session_id,
    )


@router.get(
    "/demo/patient-portal/{patient_reference}",
    response_model=List[LabOrderDemoPortalRead],
    summary="Staff-only demo utility: retrieve verification codes for a synthetic patient",
)
def get_demo_patient_portal_orders(
    patient_reference: str,
    db: Session = Depends(get_db),
    _claims=Depends(_require_any_staff_role),
):
    """
    Staff-only synthetic utility that allows an authorized staff member to view the six-digit
    verification code issued to a synthetic patient reference (e.g., PAT-2024-9182).
    """
    return lab_service.get_demo_patient_portal_lab_orders(
        db=db,
        patient_reference=patient_reference,
    )


@router.get("/{order_id}", response_model=LabOrderRead, summary="Get lab order by ID")
def get_lab_order(order_id: str, db: Session = Depends(get_db)):
    """Retrieve a single lab order metadata record (excludes verification code)."""
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
    claims=Depends(_require_lab_operator_role),
):
    """
    Update lab order workflow stage.
    Protected by LAB_OPERATOR role authorization.
    """
    actor = claims.get("display_name") or claims.get("username") or "LAB_COORDINATOR"
    order = lab_service.update_lab_order_status(
        db=db,
        order_id=order_id,
        workflow_status=payload.workflow_status,
        delay_reason=payload.delay_reason,
        actor_reference=actor,
    )
    return _to_lab_order_read(order)

