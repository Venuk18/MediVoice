from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.lab_order import LabOrder, LabStatus
from app.models.audit_event import AuditEvent
from app.services.lab_service import (
    create_lab_order,
    generate_unique_verification_code,
    reset_verification_rate_limits,
)


def _lab_headers(client):
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "lab.vikram", "password": "demo-lab-password"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_list_lab_orders(client, seeded_hospital_data):
    assert client.get("/api/v1/lab-orders").status_code == 401
    response = client.get("/api/v1/lab-orders", headers=_lab_headers(client))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # Staff listing must never expose verification_code.
    for item in data:
        assert "verification_code" not in item


def test_filter_lab_orders_by_status(client, seeded_hospital_data):
    assert client.get("/api/v1/lab-orders?status=Processing").status_code == 401
    response = client.get("/api/v1/lab-orders?status=Processing", headers=_lab_headers(client))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["workflow_status"] == "Processing"
    assert data[0]["test_category"] == "Cardiac Enzymes"
    assert "verification_code" not in data[0]


def test_update_lab_order_status(client, db_session, seeded_hospital_data):
    order_id = seeded_hospital_data["lab_pending"].id

    payload = {
        "workflow_status": "Processing",
        "delay_reason": None,
    }
    response = client.patch(f"/api/v1/lab-orders/{order_id}/status", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["workflow_status"] == "Processing"
    assert data["lab_status"] == "PROCESSING"
    assert "verification_code" not in data

    # Verify audit event
    audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "LabOrder",
            AuditEvent.entity_id == order_id,
            AuditEvent.action == "LAB_ORDER_STATUS_UPDATED",
        )
    ).first()
    assert audit is not None


def test_reject_invalid_lab_status(client, seeded_hospital_data):
    order_id = seeded_hospital_data["lab_pending"].id

    payload = {
        "workflow_status": "ArbitraryNonExistentStatus",
    }
    response = client.patch(f"/api/v1/lab-orders/{order_id}/status", json=payload)
    assert response.status_code in [400, 422]


def test_verification_code_format_and_leading_zeros_preserved(db_session, seeded_hospital_data):
    """Verification codes must be 6-digit strings ('000000'-'999999') preserving leading zeros."""
    with patch("app.services.lab_service.secrets.randbelow", return_value=42):
        code = generate_unique_verification_code(db_session)
        assert isinstance(code, str)
        assert len(code) == 6
        assert code == "000042"

    # Seeded lab_overdue has code '048271' with a leading zero
    overdue_order = seeded_hospital_data["lab_overdue"]
    assert overdue_order.verification_code == "048271"
    assert len(overdue_order.verification_code) == 6


def test_verification_code_uniqueness_and_collision_retry(db_session, seeded_hospital_data):
    """Generator retries safely when a generated 6-digit code collides with an active unexpired code."""
    # '048271' is already active on lab_overdue; generator should skip 48271 and pick 123456
    with patch("app.services.lab_service.secrets.randbelow", side_effect=[48271, 123456]):
        code = generate_unique_verification_code(db_session)
        assert code == "123456"

    # If all bounded retries collide with an active code, raise controlled HTTP 503 error
    with patch("app.services.lab_service.secrets.randbelow", return_value=48271):
        with pytest.raises(HTTPException) as exc_info:
            generate_unique_verification_code(db_session, max_retries=3)
        assert exc_info.value.status_code == 503


def test_create_lab_order_and_demo_patient_portal_access(client, seeded_hospital_data):
    """Creating a lab order assigns a unique 6-digit code retrievable only by authorized staff or the patient with the code."""
    dept_id = seeded_hospital_data["dept_cardio"].id
    create_resp = client.post(
        "/api/v1/lab-orders",
        json={
            "patient_reference": "PAT-DEMO-7001",
            "ordering_department_id": dept_id,
            "test_name": "High-Sensitivity CRP (hs-CRP)",
            "workflow_status": "REGISTERED",
            "assigned_team": "Clinical Biochemistry",
        },
    )
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["test_name"] == "High-Sensitivity CRP (hs-CRP)"
    assert created_data["lab_status"] == "REGISTERED"
    # Public creation/listing response must not expose verification_code
    assert "verification_code" not in created_data

    # Single order public endpoint must also not expose verification_code
    single_resp = client.get(f"/api/v1/lab-orders/{created_data['id']}")
    assert single_resp.status_code == 200
    assert "verification_code" not in single_resp.json()

    # The demo portal is staff-only because it returns verification codes.
    portal_resp = client.get("/api/v1/lab-orders/demo/patient-portal/PAT-DEMO-7001")
    assert portal_resp.status_code == 401
    portal_resp = client.get(
        "/api/v1/lab-orders/demo/patient-portal/PAT-DEMO-7001",
        headers=_lab_headers(client),
    )
    assert portal_resp.status_code == 200
    portal_orders = portal_resp.json()
    assert len(portal_orders) == 1
    code = portal_orders[0]["verification_code"]
    assert isinstance(code, str)
    assert len(code) == 6
    assert code.isdigit()


def test_verify_lab_order_valid_codes_across_all_statuses(client, db_session, seeded_hospital_data):
    """Valid 6-digit verification codes return accurate patient-facing status explanations across all 5 statuses."""
    dept_id = seeded_hospital_data["dept_gen"].id
    status_expectations = [
        (LabStatus.REGISTERED.value, "registered"),
        (LabStatus.SAMPLE_COLLECTED.value, "sample has been collected"),
        (LabStatus.PROCESSING.value, "currently being processed"),
        (LabStatus.COMPLETED.value, "processing is complete"),
        (LabStatus.CANCELLED.value, "cancelled"),
    ]

    for idx, (status_val, expected_phrase) in enumerate(status_expectations):
        order = create_lab_order(
            db_session,
            patient_reference=f"PAT-STATUS-{idx}",
            ordering_department_id=dept_id,
            test_name=f"Synthetic Panel {status_val}",
            workflow_status=status_val,
        )
        resp = client.post(
            "/api/v1/lab-orders/verify-status",
            json={"verification_code": order.verification_code},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["verified"] is True
        assert body["test_name"] == f"Synthetic Panel {status_val}"
        assert body["lab_status"] == status_val
        assert expected_phrase in body["status_explanation"].lower()
        assert body["next_step"]
        assert body["last_updated_at"] is not None
        assert "Status verification only" in body["disclaimer"]


def test_verify_lab_order_privacy_protection(client, seeded_hospital_data):
    """Verification endpoint never leaks patient_reference, internal order IDs, or other orders."""
    resp = client.post(
        "/api/v1/lab-orders/verify-status",
        json={"verification_code": "048271"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verified"] is True
    assert data["test_name"] == "Cardiac Troponin I & Lipid Profile"
    assert data["lab_status"] == "PROCESSING"

    # Privacy checks: no patient_reference, no internal id, no clinical test values
    raw_json_str = str(data)
    assert "PAT-1001" not in raw_json_str
    assert "lab-overdue-1" not in raw_json_str
    assert "patient_reference" not in data
    assert "id" not in data
    assert "order_id" not in data


def test_verify_lab_order_rejects_malformed_unknown_expired_and_inactive_codes(
    client, db_session, seeded_hospital_data
):
    """Malformed, unknown, expired, and inactive verification codes are rejected with safe responses."""
    # 1. Malformed codes (fewer than 6 digits, more than 6 digits, non-digits)
    for bad_code in ["12345", "1234567", "12A456", "ABCDEF", ""]:
        reset_verification_rate_limits()
        r_bad = client.post(
            "/api/v1/lab-orders/verify-status",
            json={"verification_code": bad_code},
        )
        assert r_bad.status_code == 400
        detail = r_bad.json()["detail"]
        assert detail["code"] == "INVALID_CODE_FORMAT"

    # 2. Unknown 6-digit code
    reset_verification_rate_limits()
    r_unknown = client.post(
        "/api/v1/lab-orders/verify-status",
        json={"verification_code": "999999"},
    )
    assert r_unknown.status_code == 404
    assert r_unknown.json()["detail"]["code"] == "INVALID_OR_EXPIRED_CODE"

    # 3. Expired verification code
    reset_verification_rate_limits()
    pending_order = seeded_hospital_data["lab_pending"]
    pending_order.verification_code_expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.commit()

    r_expired = client.post(
        "/api/v1/lab-orders/verify-status",
        json={"verification_code": "839201"},
    )
    assert r_expired.status_code == 404
    assert r_expired.json()["detail"]["code"] == "INVALID_OR_EXPIRED_CODE"

    # 4. Inactive verification code
    reset_verification_rate_limits()
    overdue_order = seeded_hospital_data["lab_overdue"]
    overdue_order.verification_code_is_active = False
    db_session.commit()

    r_inactive = client.post(
        "/api/v1/lab-orders/verify-status",
        json={"verification_code": "048271"},
    )
    assert r_inactive.status_code == 404
    assert r_inactive.json()["detail"]["code"] == "INVALID_OR_EXPIRED_CODE"


def test_verify_lab_order_rate_limiting_on_repeated_failed_attempts(client, seeded_hospital_data):
    """Repeated failed verification attempts trigger HTTP 429 rate limiting."""
    reset_verification_rate_limits()

    # Make 5 failed attempts (default max_attempts = 5)
    for _ in range(5):
        r = client.post(
            "/api/v1/lab-orders/verify-status",
            json={"verification_code": "999999", "session_id": "rate-limit-test-session"},
        )
        assert r.status_code == 404

    # 6th attempt within window must be blocked with HTTP 429 Too Many Requests
    r_blocked = client.post(
        "/api/v1/lab-orders/verify-status",
        json={"verification_code": "048271", "session_id": "rate-limit-test-session"},
    )
    assert r_blocked.status_code == 429
    assert r_blocked.json()["detail"]["code"] == "RATE_LIMITED"
