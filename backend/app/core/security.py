import base64
import hashlib
import hmac
import json
import os
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple
from fastapi import Depends, Header, HTTPException, Request, status
from app.core.config import settings


def is_demo_staff_auth_allowed() -> bool:
    """
    Synthetic demo staff authentication is permitted in non-production environments,
    or in production ONLY when ENABLE_DEMO_STAFF_AUTH=true is explicitly set.
    """
    env = (os.getenv("ENVIRONMENT") or getattr(settings, "ENVIRONMENT", "development")).strip().lower()
    if env in ("prod", "production"):
        return os.getenv("ENABLE_DEMO_STAFF_AUTH", "").strip().lower() in ("true", "1", "yes") or bool(
            getattr(settings, "ENABLE_DEMO_STAFF_AUTH", False)
        )
    return True


class StaffRole(str, Enum):
    DOCTOR = "DOCTOR"
    LAB_OPERATOR = "LAB_OPERATOR"
    MAINTENANCE_STAFF = "MAINTENANCE_STAFF"
    ADMIN = "ADMIN"


# Secret key for signing synthetic demo tokens
_AUTH_SECRET = os.getenv("MEDIVOICE_AUTH_SECRET") or "local-demo-only-change-before-deployment"
if os.getenv("ENVIRONMENT", "development").lower() in {"prod", "production"} and not os.getenv("MEDIVOICE_AUTH_SECRET"):
    raise RuntimeError("MEDIVOICE_AUTH_SECRET must be configured in production.")
_TOKEN_TTL_SECONDS = 86400  # 24 hours


# Approved synthetic demo staff accounts for Aarogya One Hospital
SYNTHETIC_STAFF_ACCOUNTS: Dict[str, Dict[str, Optional[str]]] = {
    "dr.sharma": {
        "staff_id": "STAFF-DOC-001",
        "username": "dr.sharma",
        "password": "demo-doctor-password",
        "display_name": "Dr. Rajesh Sharma",
        "role": StaffRole.DOCTOR.value,
        "department": "Cardiology",
        "doctor_id": "33333333-0001-0000-0000-000000000001",
        "badge_label": "Senior Interventional Cardiologist • Suite 102",
    },
    "dr.nair": {
        "staff_id": "STAFF-DOC-002",
        "username": "dr.nair",
        "password": "demo-doctor-password",
        "display_name": "Dr. Priya Nair",
        "role": StaffRole.DOCTOR.value,
        "department": "Neurology",
        "doctor_id": "33333333-0002-0000-0000-000000000002",
        "badge_label": "Consultant Neurologist • Neuro Center 204",
    },
    "dr.mehta": {
        "staff_id": "STAFF-DOC-005",
        "username": "dr.mehta",
        "password": "demo-doctor-password",
        "display_name": "Dr. Vikram Mehta",
        "role": StaffRole.DOCTOR.value,
        "department": "General Medicine",
        "doctor_id": "33333333-0005-0000-0000-000000000005",
        "badge_label": "Lead Physician, Internal Medicine • Room 108",
    },
    "lab.vikram": {
        "staff_id": "STAFF-LAB-001",
        "username": "lab.vikram",
        "password": "demo-lab-password",
        "display_name": "Vikram Deshmukh",
        "role": StaffRole.LAB_OPERATOR.value,
        "department": "Central Diagnostics & Stat Biochemistry",
        "doctor_id": None,
        "badge_label": "Lead Clinical Laboratory Technologist",
    },
    "maint.karthik": {
        "staff_id": "STAFF-MAINT-001",
        "username": "maint.karthik",
        "password": "demo-maint-password",
        "display_name": "Karthik Subramanian",
        "role": StaffRole.MAINTENANCE_STAFF.value,
        "department": "Hospital Engineering & Biomedical Facilities",
        "doctor_id": None,
        "badge_label": "Chief Biomedical & Facilities Engineer",
    },
    "admin.meera": {
        "staff_id": "STAFF-ADMIN-001",
        "username": "admin.meera",
        "password": "demo-admin-password",
        "display_name": "Meera Krishnan",
        "role": StaffRole.ADMIN.value,
        "department": "Hospital Command & Operations",
        "doctor_id": None,
        "badge_label": "Hospital Operations Superintendent",
    },
}


def create_staff_token(account: Dict[str, Optional[str]]) -> Tuple[str, int]:
    """Generates an HMAC-SHA256 signed token for a synthetic staff profile."""
    expires_at = int(time.time()) + _TOKEN_TTL_SECONDS
    payload = {
        "staff_id": account["staff_id"],
        "username": account["username"],
        "display_name": account["display_name"],
        "role": account["role"],
        "department": account.get("department") or "",
        "doctor_id": account.get("doctor_id"),
        "badge_label": account.get("badge_label") or "",
        "exp": expires_at,
    }
    raw_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
    signature = hmac.new(
        _AUTH_SECRET.encode("utf-8"),
        b64_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{b64_payload}.{signature}", expires_at


def verify_staff_token(token: str) -> Dict[str, Optional[str]]:
    """Verifies an HMAC-SHA256 signed token and returns the decoded staff claims."""
    if not token or "." not in token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_TOKEN",
                "message": "Invalid or malformed authentication token. Please sign in to the staff portal.",
            },
        )
    parts = token.split(".", 1)
    if len(parts) != 2:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Malformed authentication token."},
        )
    b64_payload, provided_sig = parts
    expected_sig = hmac.new(
        _AUTH_SECRET.encode("utf-8"),
        b64_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_SIGNATURE", "message": "Authentication token signature verification failed."},
        )

    padding = "=" * (-len(b64_payload) % 4)
    try:
        decoded_bytes = base64.urlsafe_b64decode(b64_payload + padding)
        claims = json.loads(decoded_bytes.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Unable to decode authentication token."},
        ) from exc

    exp = claims.get("exp", 0)
    if int(time.time()) > int(exp):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_EXPIRED", "message": "Your staff session has expired. Please sign in again."},
        )
    return claims


def authenticate_staff(username: str, password: str) -> Dict[str, Optional[str]]:
    """Authenticates a synthetic staff account using both username and password."""
    if not is_demo_staff_auth_allowed():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "DEMO_AUTH_DISABLED",
                "message": (
                    "Synthetic staff authentication is disabled in production environments. "
                    "Set ENABLE_DEMO_STAFF_AUTH=true to enable demo staff access."
                ),
            },
        )
    clean_user = (username or "").strip().lower()
    account = SYNTHETIC_STAFF_ACCOUNTS.get(clean_user)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_CREDENTIALS",
                "message": f"Unknown staff username '{username}'. Use one of the approved synthetic demo accounts.",
            },
        )
    if not password or not hmac.compare_digest(password, account["password"] or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_CREDENTIALS",
                "message": "Invalid staff password for the selected synthetic demo account.",
            },
        )
    return account


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    clean = authorization.strip()
    if not clean.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_AUTH_HEADER",
                "message": "Authorization header must use Bearer token format.",
            },
        )
    token = clean[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "MISSING_TOKEN",
                "message": "Bearer token is empty.",
            },
        )
    return token


def require_staff_roles(
    allowed_roles: List[StaffRole],
    *,
    strict_unauthenticated: bool = True,
):
    """
    FastAPI dependency factory that enforces role-based access control on backend endpoints.
    - Always allows ADMIN alongside the specified `allowed_roles`.
    - When `strict_unauthenticated=True` (default for `/api/v1/maintenance/*` and `/api/v1/auth/me`)
      or when the client sends `X-MediVoice-Client` / `X-Enforce-RBAC` / `Authorization`, missing
      credentials return 401 Unauthorized.
    - When a valid token is present with a role not in `allowed_roles`, always returns 403 Forbidden.
    """
    allowed_values = {r.value for r in allowed_roles} | {StaffRole.ADMIN.value}

    def dependency(
        request: Request,
        authorization: Optional[str] = Header(default=None),
        x_medivoice_client: Optional[str] = Header(default=None),
        x_enforce_rbac: Optional[str] = Header(default=None),
    ) -> Optional[Dict[str, Optional[str]]]:
        token = _extract_bearer_token(authorization)
        enforce_missing = (
            strict_unauthenticated
            or bool(x_medivoice_client)
            or (x_enforce_rbac and x_enforce_rbac.lower() in ("1", "true", "yes"))
        )

        if not token:
            if enforce_missing:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": (
                            f"Staff authentication is required for this operation. "
                            f"Permitted roles: {', '.join(sorted(r.value for r in allowed_roles))}."
                        ),
                        "required_roles": sorted(r.value for r in allowed_roles),
                    },
                )
            return None

        claims = verify_staff_token(token)
        role = claims.get("role", "")
        if role not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INSUFFICIENT_ROLE_PERMISSIONS",
                    "message": (
                        f"Access denied: Role '{role}' is not authorized to perform this action. "
                        f"Permitted roles: {', '.join(sorted(r.value for r in allowed_roles))}."
                    ),
                    "current_role": role,
                    "required_roles": sorted(r.value for r in allowed_roles),
                },
            )
        return claims

    return dependency
