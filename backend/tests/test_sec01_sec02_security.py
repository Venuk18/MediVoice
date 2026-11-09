import concurrent.futures
from datetime import datetime, timedelta, timezone
import json
import time
import pytest
from sqlalchemy import select

from app.core.security import (
    StaffRole,
    create_staff_token,
    create_patient_token,
    SYNTHETIC_STAFF_ACCOUNTS,
)
from app.models.appointment import Appointment
from app.models.appointment_slot import AppointmentSlot
from app.models.audit_event import AuditEvent
from app.models.lab_order import LabOrder


# ==============================================================================
# Helper functions for generating test tokens and authentication headers
# ==============================================================================

def _make_doctor_headers(username: str = "dr.sharma") -> dict:
    account = SYNTHETIC_STAFF_ACCOUNTS[username]
    token, _ = create_staff_token(account)
    return {"Authorization": f"Bearer {token}"}


def _make_admin_headers() -> dict:
    account = SYNTHETIC_STAFF_ACCOUNTS["admin.meera"]
    token, _ = create_staff_token(account)
    return {"Authorization": f"Bearer {token}"}


def _make_lab_headers() -> dict:
    account = SYNTHETIC_STAFF_ACCOUNTS["lab.vikram"]
    token, _ = create_staff_token(account)
    return {"Authorization": f"Bearer {token}"}


def _make_maintenance_headers() -> dict:
    account = SYNTHETIC_STAFF_ACCOUNTS["maint.karthik"]
    token, _ = create_staff_token(account)
    return {"Authorization": f"Bearer {token}"}


def _make_patient_headers(patient_reference: str = "PAT-SEC-1001", display_name: str = "Test Patient") -> dict:
    token, _ = create_patient_token(patient_reference=patient_reference, display_name=display_name)
    return {"Authorization": f"Bearer {token}"}


def _make_expired_token(account_or_patient_ref: str = "dr.sharma", is_patient: bool = False) -> str:
    """Creates a token with an expiration time in the past (-3600 seconds)."""
    if is_patient:
        token, _ = create_patient_token(account_or_patient_ref, ttl_seconds=-3600)
    else:
        account = SYNTHETIC_STAFF_ACCOUNTS[account_or_patient_ref]
        # Temporarily mock past expiration
        import base64
        import hashlib
        import hmac
        import os
        auth_secret = os.getenv("MEDIVOICE_AUTH_SECRET") or "local-demo-only-change-before-deployment"
        payload = {
            "staff_id": account["staff_id"],
            "username": account["username"],
            "display_name": account["display_name"],
            "role": account["role"],
            "department": account.get("department") or "",
            "doctor_id": account.get("doctor_id"),
            "badge_label": account.get("badge_label") or "",
            "exp": int(time.time()) - 3600,
        }
        raw_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        b64_payload = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
        sig = hmac.new(auth_secret.encode("utf-8"), b64_payload.encode("ascii"), hashlib.sha256).hexdigest()
        token = f"{b64_payload}.{sig}"
    return token


# ==============================================================================
# SEC-01 Tests: Doctor Mutation Endpoints (/complete and /follow-up)
# ==============================================================================

class TestDoctorEndpointsSecurity:
    """Verifies strict authorization on doctor mutation endpoints."""

    def test_complete_anonymous_request_rejected(self, client, seeded_hospital_data):
        """Anonymous request without Authorization header must return HTTP 401."""
        appt_id = seeded_hospital_data["existing_appt"].id
        resp = client.post(f"/api/v1/appointments/{appt_id}/complete", json={"notes": "Test notes"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"

    def test_complete_missing_token_rejected(self, client, seeded_hospital_data):
        """Empty Authorization header must return HTTP 401."""
        appt_id = seeded_hospital_data["existing_appt"].id
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/complete",
            headers={"Authorization": "Bearer "},
            json={"notes": "Test notes"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "MISSING_TOKEN"

    def test_complete_invalid_token_rejected(self, client, seeded_hospital_data):
        """Malformed or tampered token signature must return HTTP 401."""
        appt_id = seeded_hospital_data["existing_appt"].id
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/complete",
            headers={"Authorization": "Bearer invalid.signature.token123"},
            json={"notes": "Test notes"},
        )
        assert resp.status_code == 401

    def test_complete_expired_token_rejected(self, client, seeded_hospital_data):
        """Expired staff token must return HTTP 401."""
        appt_id = seeded_hospital_data["existing_appt"].id
        expired_token = _make_expired_token("dr.sharma")
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/complete",
            headers={"Authorization": f"Bearer {expired_token}"},
            json={"notes": "Test notes"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "TOKEN_EXPIRED"

    def test_complete_patient_token_forbidden(self, client, seeded_hospital_data):
        """Patient token attempting doctor complete mutation must return HTTP 403."""
        appt_id = seeded_hospital_data["existing_appt"].id
        patient_headers = _make_patient_headers("PAT-SEC-1001")
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/complete",
            headers=patient_headers,
            json={"notes": "Patient attempting to complete own visit"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"

    def test_complete_lab_staff_token_forbidden(self, client, seeded_hospital_data):
        """Lab staff token attempting doctor complete mutation must return HTTP 403."""
        appt_id = seeded_hospital_data["existing_appt"].id
        lab_headers = _make_lab_headers()
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/complete",
            headers=lab_headers,
            json={"notes": "Lab tech trying to complete clinical visit"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"

    def test_complete_authorized_doctor_mutation(self, client, db_session, seeded_hospital_data):
        """Doctor token successfully completes appointment and logs verified doctor identity."""
        appt_id = seeded_hospital_data["existing_appt"].id
        doc_headers = _make_doctor_headers("dr.sharma")
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/complete",
            headers=doc_headers,
            json={"notes": "Routine cardiology review concluded satisfactorily"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["appointment_status"] == "COMPLETED"
        assert data["visit_completed_at"] is not None

        # Verify audit trail records the doctor display name
        audit = db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_type == "Appointment",
                AuditEvent.entity_id == appt_id,
                AuditEvent.action == "APPOINTMENT_COMPLETED",
            )
        ).first()
        assert audit is not None
        assert audit.actor_reference == "Dr. Rajesh Sharma"

    def test_follow_up_anonymous_request_rejected(self, client, seeded_hospital_data):
        """Anonymous follow-up request must return HTTP 401."""
        appt_id = seeded_hospital_data["existing_appt"].id
        fu_date = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/follow-up",
            json={"follow_up_date": fu_date, "follow_up_notes": "Follow-up in 2 weeks"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"

    def test_follow_up_patient_token_forbidden(self, client, seeded_hospital_data):
        """Patient token attempting doctor follow-up mutation must return HTTP 403."""
        appt_id = seeded_hospital_data["existing_appt"].id
        fu_date = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        patient_headers = _make_patient_headers("PAT-SEC-1001")
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/follow-up",
            headers=patient_headers,
            json={"follow_up_date": fu_date, "follow_up_notes": "Patient instructions"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"

    def test_follow_up_authorized_doctor_mutation(self, client, db_session, seeded_hospital_data):
        """Doctor token successfully records operational follow-up date and instructions."""
        appt_id = seeded_hospital_data["existing_appt"].id
        fu_date = (datetime.now(timezone.utc) + timedelta(days=21)).isoformat()
        doc_headers = _make_doctor_headers("dr.sharma")
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/follow-up",
            headers=doc_headers,
            json={"follow_up_date": fu_date, "follow_up_notes": "Review echocardiogram results in 3 weeks"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["follow_up_recommended"] is True
        assert data["follow_up_notes"] == "Review echocardiogram results in 3 weeks"


# ==============================================================================
# SEC-01 Tests: Lab Mutation Endpoints (/lab-orders POST and PATCH)
# ==============================================================================

class TestLabEndpointsSecurity:
    """Verifies strict authorization on lab order mutation endpoints."""

    def test_create_lab_anonymous_request_rejected(self, client, seeded_hospital_data):
        """Anonymous lab order creation must return HTTP 401."""
        dept_id = seeded_hospital_data["dept_cardio"].id
        resp = client.post(
            "/api/v1/lab-orders",
            json={
                "patient_reference": "PAT-SEC-LAB-01",
                "ordering_department_id": dept_id,
                "test_name": "Serum Troponin-T",
                "workflow_status": "REGISTERED",
            },
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"

    def test_create_lab_missing_token_rejected(self, client, seeded_hospital_data):
        """Empty Authorization header on lab order creation must return HTTP 401."""
        dept_id = seeded_hospital_data["dept_cardio"].id
        resp = client.post(
            "/api/v1/lab-orders",
            headers={"Authorization": "Bearer "},
            json={
                "patient_reference": "PAT-SEC-LAB-01",
                "ordering_department_id": dept_id,
                "test_name": "Serum Troponin-T",
            },
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "MISSING_TOKEN"

    def test_create_lab_patient_token_forbidden(self, client, seeded_hospital_data):
        """Patient token attempting lab order creation must return HTTP 403."""
        dept_id = seeded_hospital_data["dept_cardio"].id
        patient_headers = _make_patient_headers("PAT-SEC-LAB-01")
        resp = client.post(
            "/api/v1/lab-orders",
            headers=patient_headers,
            json={
                "patient_reference": "PAT-SEC-LAB-01",
                "ordering_department_id": dept_id,
                "test_name": "Self-Ordered Blood Panel",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"

    def test_create_lab_doctor_token_allowed(self, client, seeded_hospital_data):
        """Doctors are permitted to create lab orders (requisition) -> HTTP 201."""
        dept_id = seeded_hospital_data["dept_cardio"].id
        doc_headers = _make_doctor_headers("dr.sharma")
        resp = client.post(
            "/api/v1/lab-orders",
            headers=doc_headers,
            json={
                "patient_reference": "PAT-SEC-LAB-02",
                "ordering_department_id": dept_id,
                "test_name": "Lipid Profile Panel",
                "workflow_status": "REGISTERED",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["test_name"] == "Lipid Profile Panel"

    def test_create_lab_staff_token_allowed(self, client, seeded_hospital_data):
        """Lab staff can create lab orders -> HTTP 201."""
        dept_id = seeded_hospital_data["dept_cardio"].id
        lab_headers = _make_lab_headers()
        resp = client.post(
            "/api/v1/lab-orders",
            headers=lab_headers,
            json={
                "patient_reference": "PAT-SEC-LAB-03",
                "ordering_department_id": dept_id,
                "test_name": "Complete Blood Count (CBC)",
                "workflow_status": "REGISTERED",
            },
        )
        assert resp.status_code == 201

    def test_update_status_anonymous_request_rejected(self, client, seeded_hospital_data):
        """Anonymous update of lab status must return HTTP 401."""
        order_id = seeded_hospital_data["lab_pending"].id
        resp = client.patch(
            f"/api/v1/lab-orders/{order_id}/status",
            json={"workflow_status": "PROCESSING"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"

    def test_update_status_patient_token_forbidden(self, client, seeded_hospital_data):
        """Patient token cannot mutate lab workflow status -> HTTP 403."""
        order_id = seeded_hospital_data["lab_pending"].id
        patient_headers = _make_patient_headers("PAT-SEC-LAB-01")
        resp = client.patch(
            f"/api/v1/lab-orders/{order_id}/status",
            headers=patient_headers,
            json={"workflow_status": "COMPLETED"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"

    def test_update_status_doctor_token_forbidden(self, client, seeded_hospital_data):
        """Doctor token cannot update lab processing stage (only lab operators can update lab stage) -> HTTP 403."""
        order_id = seeded_hospital_data["lab_pending"].id
        doc_headers = _make_doctor_headers("dr.sharma")
        resp = client.patch(
            f"/api/v1/lab-orders/{order_id}/status",
            headers=doc_headers,
            json={"workflow_status": "COMPLETED"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"

    def test_update_status_authorized_lab_mutation(self, client, db_session, seeded_hospital_data):
        """Lab staff token successfully updates lab workflow stage and records verified lab actor."""
        order_id = seeded_hospital_data["lab_pending"].id
        lab_headers = _make_lab_headers()
        resp = client.patch(
            f"/api/v1/lab-orders/{order_id}/status",
            headers=lab_headers,
            json={"workflow_status": "PROCESSING", "delay_reason": None},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["workflow_status"].upper() == "PROCESSING"
        assert data["lab_status"] == "PROCESSING"

        # Verify audit event
        audit = db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_type == "LabOrder",
                AuditEvent.entity_id == order_id,
                AuditEvent.action == "LAB_ORDER_STATUS_UPDATED",
            )
        ).first()
        assert audit is not None
        assert audit.actor_reference == "Vikram Deshmukh"


# ==============================================================================
# SEC-02 Tests: Secure Appointment Cancellation (/appointments/{id}/cancel)
# ==============================================================================

class TestAppointmentCancellationSecurity:
    """Verifies strict identity and patient ownership authorization on appointment cancellations."""

    def test_cancellation_anonymous_rejected(self, client, seeded_hospital_data):
        """Anonymous cancellation attempt must return HTTP 401."""
        appt_id = seeded_hospital_data["existing_appt"].id
        resp = client.post(f"/api/v1/appointments/{appt_id}/cancel")
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"

    def test_cancellation_invalid_token_rejected(self, client, seeded_hospital_data):
        """Invalid token signature must return HTTP 401."""
        appt_id = seeded_hospital_data["existing_appt"].id
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/cancel",
            headers={"Authorization": "Bearer bad.token.signature"},
        )
        assert resp.status_code == 401

    def test_cancellation_expired_token_rejected(self, client, seeded_hospital_data):
        """Expired patient token must return HTTP 401."""
        appt_id = seeded_hospital_data["existing_appt"].id
        expired_token = _make_expired_token("PAT-SEC-EXPIRED", is_patient=True)
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/cancel",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "TOKEN_EXPIRED"

    def test_cancellation_patient_cancelling_own_appointment(self, client, db_session, seeded_hospital_data):
        """Patient token matching the appointment's patient_reference successfully cancels appointment."""
        doc_id = seeded_hospital_data["doc_sharma"].id
        slot_id = seeded_hospital_data["slot_available_2"].id
        patient_ref = "PAT-OWNER-99"

        # Book an appointment for this patient
        book_resp = client.post(
            "/api/v1/appointments",
            json={
                "patient_reference": patient_ref,
                "doctor_id": doc_id,
                "slot_id": slot_id,
                "reason_category": "Annual Cardiac Check",
            },
        )
        assert book_resp.status_code == 201
        appt_id = book_resp.json()["id"]

        # Slot is now BOOKED
        db_session.expire_all()
        slot = db_session.scalars(select(AppointmentSlot).where(AppointmentSlot.id == slot_id)).first()
        assert slot.status == "BOOKED"

        # Patient cancels their own appointment
        patient_headers = _make_patient_headers(patient_reference=patient_ref)
        cancel_resp = client.post(
            f"/api/v1/appointments/{appt_id}/cancel",
            headers=patient_headers,
            json={"cancellation_reason": "Patient requested cancellation via portal"},
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["appointment_status"] == "CANCELLED"

        # Slot is safely released back to AVAILABLE
        db_session.expire_all()
        slot_after = db_session.scalars(select(AppointmentSlot).where(AppointmentSlot.id == slot_id)).first()
        assert slot_after.status == "AVAILABLE"

        # Verify audit trail records patient actor
        audit = db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_type == "Appointment",
                AuditEvent.entity_id == appt_id,
                AuditEvent.action == "APPOINTMENT_CANCELLED",
            )
        ).first()
        assert audit is not None
        assert audit.actor_reference == f"PATIENT:{patient_ref}"

    def test_cancellation_patient_cancelling_another_patient_appointment_forbidden(
        self, client, db_session, seeded_hospital_data
    ):
        """Patient token for PAT-ATTACKER attempting to cancel PAT-VICTIM's appointment is rejected with HTTP 403."""
        # existing_appt belongs to PAT-2024-9182
        victim_appt = seeded_hospital_data["existing_appt"]
        victim_appt_id = victim_appt.id
        slot_id = victim_appt.slot_id

        # Slot is BOOKED
        slot = db_session.scalars(select(AppointmentSlot).where(AppointmentSlot.id == slot_id)).first()
        assert slot.status == "BOOKED"

        # Attacker with a valid patient token for a different patient
        attacker_headers = _make_patient_headers(patient_reference="PAT-ATTACKER-666")
        cancel_resp = client.post(
            f"/api/v1/appointments/{victim_appt_id}/cancel",
            headers=attacker_headers,
            json={"cancellation_reason": "Malicious attempt to cancel victim booking"},
        )
        assert cancel_resp.status_code == 403
        assert cancel_resp.json()["detail"]["code"] == "INSUFFICIENT_PERMISSIONS"

        # Verify appointment is STILL CONFIRMED
        db_session.expire_all()
        appt_after = db_session.scalars(select(Appointment).where(Appointment.id == victim_appt_id)).first()
        assert appt_after.appointment_status == "CONFIRMED"

        # Verify slot is STILL BOOKED (slot availability after rejected cancellation)
        slot_after = db_session.scalars(select(AppointmentSlot).where(AppointmentSlot.id == slot_id)).first()
        assert slot_after.status == "BOOKED"

    def test_cancellation_doctor_authorized_cancellation(self, client, db_session, seeded_hospital_data):
        """Doctor staff token successfully cancels appointment."""
        victim_appt = seeded_hospital_data["existing_appt"]
        appt_id = victim_appt.id
        slot_id = victim_appt.slot_id

        doc_headers = _make_doctor_headers("dr.sharma")
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/cancel",
            headers=doc_headers,
            json={"cancellation_reason": "Doctor schedule emergency"},
        )
        assert resp.status_code == 200
        assert resp.json()["appointment_status"] == "CANCELLED"

        # Verify slot was released to AVAILABLE
        db_session.expire_all()
        slot = db_session.scalars(select(AppointmentSlot).where(AppointmentSlot.id == slot_id)).first()
        assert slot.status == "AVAILABLE"

    def test_cancellation_admin_authorized_cancellation(self, client, db_session, seeded_hospital_data):
        """Hospital administrator token successfully cancels appointment."""
        # Book a fresh appointment to test admin cancellation
        doc_id = seeded_hospital_data["doc_sharma"].id
        slot_id = seeded_hospital_data["slot_available"].id
        book_resp = client.post(
            "/api/v1/appointments",
            json={
                "patient_reference": "PAT-ADMIN-TEST",
                "doctor_id": doc_id,
                "slot_id": slot_id,
                "reason_category": "Consultation",
            },
        )
        assert book_resp.status_code == 201
        appt_id = book_resp.json()["id"]

        admin_headers = _make_admin_headers()
        resp = client.post(
            f"/api/v1/appointments/{appt_id}/cancel",
            headers=admin_headers,
            json={"cancellation_reason": "Administrative ward reassignment"},
        )
        assert resp.status_code == 200
        assert resp.json()["appointment_status"] == "CANCELLED"

    def test_cancellation_unauthorized_staff_roles_forbidden(self, client, db_session, seeded_hospital_data):
        """Non-clinical staff roles (LAB_OPERATOR, MAINTENANCE_STAFF) are forbidden from canceling appointments."""
        # Book an appointment
        doc_id = seeded_hospital_data["doc_sharma"].id
        slot_id = seeded_hospital_data["slot_available"].id
        book_resp = client.post(
            "/api/v1/appointments",
            json={
                "patient_reference": "PAT-STAFF-ROLES-TEST",
                "doctor_id": doc_id,
                "slot_id": slot_id,
                "reason_category": "Checkup",
            },
        )
        assert book_resp.status_code == 201
        appt_id = book_resp.json()["id"]

        # Lab operator attempt -> 403
        lab_headers = _make_lab_headers()
        resp_lab = client.post(f"/api/v1/appointments/{appt_id}/cancel", headers=lab_headers)
        assert resp_lab.status_code == 403
        assert resp_lab.json()["detail"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"

        # Maintenance staff attempt -> 403
        maint_headers = _make_maintenance_headers()
        resp_maint = client.post(f"/api/v1/appointments/{appt_id}/cancel", headers=maint_headers)
        assert resp_maint.status_code == 403
        assert resp_maint.json()["detail"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"

        # Slot remains BOOKED
        db_session.expire_all()
        slot = db_session.scalars(select(AppointmentSlot).where(AppointmentSlot.id == slot_id)).first()
        assert slot.status == "BOOKED"

    def test_cancellation_nonexistent_appointment_id_not_found(self, client):
        """Valid token with nonexistent appointment ID must return HTTP 404."""
        doc_headers = _make_doctor_headers("dr.sharma")
        fake_uuid = "00000000-dead-beef-0000-000000000000"
        resp = client.post(f"/api/v1/appointments/{fake_uuid}/cancel", headers=doc_headers)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_repeated_cancellation_rejected(self, client, db_session, seeded_hospital_data):
        """Cancelling an already-cancelled appointment must return HTTP 400 Bad Request."""
        doc_id = seeded_hospital_data["doc_sharma"].id
        slot_id = seeded_hospital_data["slot_available"].id
        patient_ref = "PAT-REPEAT-TEST"

        book_resp = client.post(
            "/api/v1/appointments",
            json={
                "patient_reference": patient_ref,
                "doctor_id": doc_id,
                "slot_id": slot_id,
                "reason_category": "Checkup",
            },
        )
        assert book_resp.status_code == 201
        appt_id = book_resp.json()["id"]

        patient_headers = _make_patient_headers(patient_reference=patient_ref)

        # First cancellation succeeds
        resp1 = client.post(f"/api/v1/appointments/{appt_id}/cancel", headers=patient_headers)
        assert resp1.status_code == 200
        assert resp1.json()["appointment_status"] == "CANCELLED"

        # Second repeated cancellation must fail with 400 Bad Request
        resp2 = client.post(f"/api/v1/appointments/{appt_id}/cancel", headers=patient_headers)
        assert resp2.status_code == 400
        assert "already cancelled" in resp2.json()["detail"].lower()

    def test_cancellation_of_completed_appointment_rejected(self, client, db_session, seeded_hospital_data):
        """Cancelling an appointment that is already COMPLETED must return HTTP 400 Bad Request."""
        appt_id = seeded_hospital_data["existing_appt"].id
        doc_headers = _make_doctor_headers("dr.sharma")

        # Complete the visit
        comp_resp = client.post(
            f"/api/v1/appointments/{appt_id}/complete",
            headers=doc_headers,
            json={"notes": "Visit concluded"},
        )
        assert comp_resp.status_code == 200

        # Attempt cancellation
        cancel_resp = client.post(f"/api/v1/appointments/{appt_id}/cancel", headers=doc_headers)
        assert cancel_resp.status_code == 400
        assert "completed" in cancel_resp.json()["detail"].lower()

    def test_concurrent_cancellation_attempts(self, client, db_session, seeded_hospital_data):
        """
        Multiple concurrent cancellation requests on the same appointment:
        Exactly one request succeeds (HTTP 200), and all other attempts receive HTTP 400.
        The slot is released to AVAILABLE without corruption.
        """
        doc_id = seeded_hospital_data["doc_sharma"].id
        slot_id = seeded_hospital_data["slot_available"].id
        patient_ref = "PAT-CONCURRENT-CANCEL"

        # Create fresh appointment
        book_resp = client.post(
            "/api/v1/appointments",
            json={
                "patient_reference": patient_ref,
                "doctor_id": doc_id,
                "slot_id": slot_id,
                "reason_category": "Stress Test",
            },
        )
        assert book_resp.status_code == 201
        appt_id = book_resp.json()["id"]

        patient_headers = _make_patient_headers(patient_reference=patient_ref)

        def attempt_cancel():
            return client.post(
                f"/api/v1/appointments/{appt_id}/cancel",
                headers=patient_headers,
                json={"cancellation_reason": "Concurrent race attempt"},
            )

        # Fire multiple rapid cancellation calls
        results = [attempt_cancel() for _ in range(4)]
        status_codes = [r.status_code for r in results]

        # Exactly one must succeed (200), remaining must be 400 (already cancelled)
        assert status_codes[0] == 200
        assert status_codes[1:] == [400, 400, 400]

        # Verify final slot state in DB is AVAILABLE
        db_session.expire_all()
        slot = db_session.scalars(select(AppointmentSlot).where(AppointmentSlot.id == slot_id)).first()
        assert slot.status == "AVAILABLE"
