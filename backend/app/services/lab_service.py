import json
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Callable
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.models.lab_order import LabOrder, LabStatus, normalize_lab_status
from app.models.audit_event import AuditEvent
from app.schemas.lab_order import (
    LabOrderCreate,
    LabOrderDemoPortalRead,
    LabVerificationResponse,
)

# Thread-safe rate-limiting state for failed verification attempts (shared across sessions/requests)
_VERIFICATION_LOCK = threading.Lock()
_FAILED_VERIFICATION_ATTEMPTS: Dict[str, List[float]] = {}

VALID_SIX_DIGIT_CODE_RE = re.compile(r"^\d{6}$")

ALLOWED_WORKFLOW_STATUSES = {
    "Pending",
    "Processing",
    "Completed",
    "Delayed",
    LabStatus.REGISTERED.value,
    LabStatus.SAMPLE_COLLECTED.value,
    LabStatus.PROCESSING.value,
    LabStatus.COMPLETED.value,
    LabStatus.CANCELLED.value,
}

LAB_STATUS_PATIENT_INFO: Dict[str, Dict[str, str]] = {
    LabStatus.REGISTERED.value: {
        "explanation": "Your lab order has been registered in the Aarogya One Hospital laboratory system.",
        "next_step": "Please proceed to the Ground Floor Sample Collection Counter with your order slip to provide your sample.",
    },
    LabStatus.SAMPLE_COLLECTED.value: {
        "explanation": "Your sample has been collected and logged at the hospital laboratory reception.",
        "next_step": "Your sample is queued for laboratory analysis. Please check back in a few hours for processing updates.",
    },
    LabStatus.PROCESSING.value: {
        "explanation": "Your test sample is currently being processed and analyzed by the hospital diagnostic laboratory team.",
        "next_step": "Please check again later. Once analysis and quality verification are complete, the status will update to COMPLETED.",
    },
    LabStatus.COMPLETED.value: {
        "explanation": "Laboratory processing is complete and the official report is ready for release.",
        "next_step": "You may collect your official report at the Hospital Diagnostics Desk (Ground Floor) with valid photo ID or view it in your authenticated patient portal.",
    },
    LabStatus.CANCELLED.value: {
        "explanation": "This laboratory order has been cancelled and is no longer being processed.",
        "next_step": "Please contact the Aarogya One Hospital Lab Desk or your ordering physician if you need a new lab order.",
    },
}


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def reset_verification_rate_limits() -> None:
    """Clears in-memory failed verification attempt counters (used in test fixtures)."""
    with _VERIFICATION_LOCK:
        _FAILED_VERIFICATION_ATTEMPTS.clear()


def _check_rate_limit_locked(keys: List[str], now_mono: float) -> None:
    window = float(settings.LAB_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS)
    max_attempts = int(settings.LAB_VERIFICATION_RATE_LIMIT_MAX_ATTEMPTS)
    cutoff = now_mono - window

    for key in keys:
        if not key:
            continue
        timestamps = _FAILED_VERIFICATION_ATTEMPTS.get(key, [])
        recent = [ts for ts in timestamps if ts > cutoff]
        _FAILED_VERIFICATION_ATTEMPTS[key] = recent
        if len(recent) >= max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "RATE_LIMITED",
                    "message": (
                        "Too many failed verification attempts. Please wait a few minutes before "
                        "trying again or contact the Aarogya One Hospital Lab Desk."
                    ),
                },
            )


def _record_failed_attempt_locked(keys: List[str], now_mono: float) -> None:
    window = float(settings.LAB_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS)
    cutoff = now_mono - window
    for key in keys:
        if not key:
            continue
        timestamps = [ts for ts in _FAILED_VERIFICATION_ATTEMPTS.get(key, []) if ts > cutoff]
        timestamps.append(now_mono)
        _FAILED_VERIFICATION_ATTEMPTS[key] = timestamps


def is_active_unexpired_code_in_use(
    db: Session,
    code: str,
    reference_time: Optional[datetime] = None,
    exclude_order_id: Optional[str] = None,
) -> bool:
    """Checks whether a 6-digit code is currently assigned to any active, unexpired LabOrder."""
    now_utc = _ensure_utc(reference_time) or datetime.now(timezone.utc)
    query = select(LabOrder).where(
        LabOrder.verification_code == code,
        LabOrder.verification_code_is_active.is_(True),
    )
    if exclude_order_id:
        query = query.where(LabOrder.id != exclude_order_id)

    candidates = db.scalars(query).all()
    for order in candidates:
        exp = _ensure_utc(order.verification_code_expires_at)
        if exp is None or exp > now_utc:
            return True
    return False


def generate_unique_verification_code(
    db: Session,
    max_retries: Optional[int] = None,
    reference_time: Optional[datetime] = None,
    code_generator: Optional[Callable[[], str]] = None,
) -> str:
    """
    Generates a cryptographically secure 6-digit verification code ('000000' through '999999')
    using Python's `secrets` module.
    Enforces uniqueness among active, unexpired codes with bounded collision retries.
    Never logs verification codes or falls back to predictable values.
    """
    retries = max_retries if max_retries is not None else int(settings.LAB_VERIFICATION_MAX_GENERATION_RETRIES)
    if retries < 1:
        retries = 1

    now_utc = _ensure_utc(reference_time) or datetime.now(timezone.utc)

    for _ in range(retries):
        if code_generator is not None:
            candidate = str(code_generator())
        else:
            candidate = f"{secrets.randbelow(1_000_000):06d}"

        if not VALID_SIX_DIGIT_CODE_RE.fullmatch(candidate):
            continue

        if not is_active_unexpired_code_in_use(db, candidate, reference_time=now_utc):
            return candidate

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Unable to generate a unique verification code at this time. Please try again.",
    )


def create_lab_order(
    db: Session,
    payload: Optional[LabOrderCreate] = None,
    *,
    patient_reference: Optional[str] = None,
    ordering_department_id: Optional[str] = None,
    test_name: Optional[str] = None,
    test_category: Optional[str] = None,
    workflow_status: str = "REGISTERED",
    expected_completion_at: Optional[datetime] = None,
    assigned_team: str = "Central Diagnostics Lab",
    delay_reason: Optional[str] = None,
    explicit_verification_code: Optional[str] = None,
    expires_in_hours: Optional[int] = None,
) -> LabOrder:
    """
    Creates a new LabOrder with a unique, active 6-digit verification code and expiration timestamp.
    Accepts either a `LabOrderCreate` payload object or direct keyword arguments.
    """
    if payload is None:
        if not patient_reference:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="patient_reference is required to create a lab order.",
            )
        payload = LabOrderCreate(
            patient_reference=patient_reference,
            ordering_department_id=ordering_department_id,
            test_name=test_name,
            test_category=test_category or test_name,
            workflow_status=workflow_status,
            expected_completion_at=expected_completion_at,
            assigned_team=assigned_team,
            delay_reason=delay_reason,
        )

    try:
        now_utc = datetime.now(timezone.utc)
        exp_hours = (
            expires_in_hours
            if expires_in_hours is not None
            else int(settings.LAB_VERIFICATION_CODE_EXPIRY_HOURS)
        )
        expires_at = now_utc + timedelta(hours=exp_hours)

        with _VERIFICATION_LOCK:
            if explicit_verification_code is not None:
                code_clean = str(explicit_verification_code).strip()
                if not VALID_SIX_DIGIT_CODE_RE.fullmatch(code_clean):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Verification code must be a six-digit string ('000000' through '999999').",
                    )
                if is_active_unexpired_code_in_use(db, code_clean, reference_time=now_utc):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="An active, unexpired lab order already uses this verification code.",
                    )
                code = code_clean
            else:
                code = generate_unique_verification_code(db, reference_time=now_utc)

            expected_comp = payload.expected_completion_at or (now_utc + timedelta(hours=4))
            test_name_val = payload.test_name or payload.test_category or "General Diagnostic Panel"
            test_cat_val = payload.test_category or test_name_val

            order = LabOrder(
                patient_reference=payload.patient_reference.strip(),
                ordering_department_id=payload.ordering_department_id,
                test_category=test_cat_val.strip(),
                test_name=test_name_val.strip(),
                workflow_status=payload.workflow_status,
                expected_completion_at=expected_comp,
                assigned_team=payload.assigned_team.strip(),
                delay_reason=payload.delay_reason,
                verification_code=code,
                verification_code_expires_at=expires_at,
                verification_code_is_active=True,
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            return order
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while creating lab order.",
        ) from exc


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


def get_demo_patient_portal_lab_orders(
    db: Session,
    patient_reference: str,
) -> List[LabOrderDemoPortalRead]:
    """
    Synthetic demo patient portal endpoint helper: returns the verification codes
    associated with a synthetic patient reference so demo testers can retrieve their code.
    """
    pat_clean = (patient_reference or "").strip()
    if not pat_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Patient reference is required.",
        )
    query = (
        select(LabOrder)
        .where(LabOrder.patient_reference == pat_clean)
        .order_by(LabOrder.created_at.desc())
    )
    orders = list(db.scalars(query).all())
    results: List[LabOrderDemoPortalRead] = []
    for o in orders:
        if not o.verification_code:
            continue
        results.append(
            LabOrderDemoPortalRead(
                patient_reference=o.patient_reference,
                test_name=o.display_test_name,
                lab_status=o.lab_status,
                verification_code=o.verification_code,
                verification_code_expires_at=o.verification_code_expires_at,
                verification_code_is_active=o.verification_code_is_active,
                updated_at=o.updated_at,
            )
        )
    return results


def update_lab_order_status(
    db: Session,
    order_id: str,
    workflow_status: str,
    delay_reason: Optional[str] = None,
    actor_reference: str = "LAB_STAFF",
) -> LabOrder:
    if workflow_status not in ALLOWED_WORKFLOW_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid workflow status '{workflow_status}'. Allowed: {sorted(list(ALLOWED_WORKFLOW_STATUSES))}",
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


def verify_lab_order_by_code(
    db: Session,
    verification_code: str,
    client_identifier: str = "default_client",
    session_id: Optional[str] = None,
    reference_time: Optional[datetime] = None,
) -> LabVerificationResponse:
    """
    Validates a six-digit verification code and returns ONLY minimal permitted status information
    (test name, normalized status, patient-friendly explanation, next step, and last updated timestamp).
    - Enforces rate limiting per client and session on failed attempts.
    - Rejects malformed, unknown, expired, or inactive codes with a uniform, safe error response.
    - Never logs verification codes or exposes patient identifiers, internal IDs, or lab results.
    """
    rate_keys = [f"client:{client_identifier or 'unknown'}"]
    if session_id and str(session_id).strip():
        rate_keys.append(f"session:{str(session_id).strip()}")

    now_mono = time.monotonic()
    now_utc = _ensure_utc(reference_time) or datetime.now(timezone.utc)

    with _VERIFICATION_LOCK:
        # 1. Check rate limit before processing
        _check_rate_limit_locked(rate_keys, now_mono)

        # 2. Validate exact 6-digit format (preserving leading zeros)
        if not isinstance(verification_code, str):
            _record_failed_attempt_locked(rate_keys, now_mono)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_CODE_FORMAT",
                    "message": "Invalid verification code format. Please enter a six-digit numeric code (000000-999999).",
                },
            )

        cleaned_code = verification_code.strip()
        if not VALID_SIX_DIGIT_CODE_RE.fullmatch(cleaned_code):
            _record_failed_attempt_locked(rate_keys, now_mono)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_CODE_FORMAT",
                    "message": "Invalid verification code format. Please enter a six-digit numeric code (000000-999999).",
                },
            )

        # 3. Query database safely
        try:
            candidates = list(
                db.scalars(
                    select(LabOrder)
                    .where(LabOrder.verification_code == cleaned_code)
                    .order_by(LabOrder.created_at.desc())
                ).all()
            )
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Laboratory verification service is temporarily unavailable. Please try again shortly.",
                },
            ) from exc

        # 4. Find active, unexpired match
        valid_order: Optional[LabOrder] = None
        for order in candidates:
            if not order.verification_code_is_active:
                continue
            exp_utc = _ensure_utc(order.verification_code_expires_at)
            if exp_utc is not None and exp_utc <= now_utc:
                continue
            valid_order = order
            break

        if valid_order is None:
            _record_failed_attempt_locked(rate_keys, now_mono)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "INVALID_OR_EXPIRED_CODE",
                    "message": (
                        "Unable to verify lab order status. The verification code is invalid, expired, "
                        "or inactive. Please recheck your six-digit code or contact the Aarogya One Hospital Lab Desk."
                    ),
                },
            )

        # 5. Record verification timestamp without exposing sensitive data in audit or logs
        try:
            valid_order.verification_code_used_at = now_utc
            db.commit()
            db.refresh(valid_order)
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Laboratory verification service is temporarily unavailable. Please try again shortly.",
                },
            ) from exc

        canonical = valid_order.lab_status
        info = LAB_STATUS_PATIENT_INFO.get(
            canonical,
            LAB_STATUS_PATIENT_INFO[LabStatus.PROCESSING.value],
        )

        return LabVerificationResponse(
            verified=True,
            test_name=valid_order.display_test_name,
            lab_status=canonical,
            status_explanation=info["explanation"],
            next_step=info["next_step"],
            last_updated_at=valid_order.updated_at or valid_order.created_at or now_utc,
        )


def check_lab_report_status_tool(
    db: Session,
    verification_code: str,
    session_key: Optional[str] = None,
    session_id: Optional[str] = None,
    client_identifier: str = "agent_tool",
) -> Dict[str, Any]:
    """
    Allowlisted AI Agent tool interface for verifying lab report status via a 6-digit code.
    Returns structured verification status (or structured error code on invalid/expired/rate-limited codes)
    and never exposes patient identifiers, internal IDs, or clinical results.
    """
    effective_session = session_key or session_id
    try:
        response = verify_lab_order_by_code(
            db=db,
            verification_code=verification_code,
            client_identifier=client_identifier,
            session_id=effective_session,
        )
        return {
            "verified": response.verified,
            "test_name": response.test_name,
            "lab_status": response.lab_status,
            "status_explanation": response.status_explanation,
            "next_step": response.next_step,
            "last_updated_at": response.last_updated_at.isoformat() if response.last_updated_at else None,
            "disclaimer": response.disclaimer,
        }
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            error_code = detail.get("code", "INVALID_OR_EXPIRED_CODE")
            error_msg = detail.get("message", "Unable to verify lab order status.")
        else:
            error_code = "RATE_LIMITED" if exc.status_code == 429 else (
                "INVALID_CODE_FORMAT" if exc.status_code == 400 else "INVALID_OR_EXPIRED_CODE"
            )
            error_msg = str(detail)
        return {
            "verified": False,
            "error_code": error_code,
            "message": error_msg,
        }
