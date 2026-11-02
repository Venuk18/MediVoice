from typing import List
from fastapi import APIRouter, Depends, status

from app.core.security import (
    SYNTHETIC_STAFF_ACCOUNTS,
    is_demo_staff_auth_allowed,
    StaffRole,
    authenticate_staff,
    create_staff_token,
    require_staff_roles,
)
from app.schemas.auth import (
    DemoStaffAccountRead,
    StaffLoginRequest,
    StaffLoginResponse,
    StaffProfileRead,
)

router = APIRouter(prefix="/auth", tags=["Staff Authentication & RBAC"])


def _workspace_for_role(role: str) -> str:
    if role == StaffRole.DOCTOR.value:
        return "doctor"
    if role == StaffRole.LAB_OPERATOR.value:
        return "lab"
    if role == StaffRole.MAINTENANCE_STAFF.value:
        return "maintenance"
    return "doctor"


@router.get(
    "/demo-accounts",
    response_model=List[DemoStaffAccountRead],
    summary="List synthetic staff account names and roles for local workspace testing",
)
def list_demo_staff_accounts():
    """Returns synthetic staff profiles without credentials."""
    if not is_demo_staff_auth_allowed():
        return []
    results: List[DemoStaffAccountRead] = []
    for acc in SYNTHETIC_STAFF_ACCOUNTS.values():
        role_val = acc["role"] or StaffRole.DOCTOR.value
        results.append(
            DemoStaffAccountRead(
                staff_id=acc["staff_id"] or "",
                username=acc["username"] or "",
                display_name=acc["display_name"] or "",
                role=role_val,
                department=acc.get("department") or "",
                doctor_id=acc.get("doctor_id"),
                badge_label=acc.get("badge_label") or "",
                workspace_route=_workspace_for_role(role_val),
            )
        )
    return results


@router.post(
    "/login",
    response_model=StaffLoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Sign in to a synthetic hospital staff account and receive a signed RBAC token",
)
def staff_login(payload: StaffLoginRequest):
    """Authenticates a staff user and returns an HMAC-signed Bearer token with role claims."""
    account = authenticate_staff(payload.username, payload.password)
    token, exp = create_staff_token(account)
    return StaffLoginResponse(
        access_token=token,
        token_type="bearer",
        expires_at=exp,
        staff=StaffProfileRead(
            staff_id=account["staff_id"] or "",
            username=account["username"] or "",
            display_name=account["display_name"] or "",
            role=account["role"] or "",
            department=account.get("department") or "",
            doctor_id=account.get("doctor_id"),
            badge_label=account.get("badge_label") or "",
        ),
    )


@router.get(
    "/me",
    response_model=StaffProfileRead,
    summary="Verify current staff Bearer token and return authenticated staff profile",
)
def get_current_staff_profile(
    claims=Depends(
        require_staff_roles(
            [StaffRole.DOCTOR, StaffRole.LAB_OPERATOR, StaffRole.MAINTENANCE_STAFF, StaffRole.ADMIN],
            strict_unauthenticated=True,
        )
    ),
):
    """Returns the currently authenticated staff profile or raises 401 Unauthorized."""
    return StaffProfileRead(
        staff_id=claims.get("staff_id") or "",
        username=claims.get("username") or "",
        display_name=claims.get("display_name") or "",
        role=claims.get("role") or "",
        department=claims.get("department") or "",
        doctor_id=claims.get("doctor_id"),
        badge_label=claims.get("badge_label") or "",
    )
