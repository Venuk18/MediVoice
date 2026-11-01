from sqlalchemy import select
from app.models.audit_event import AuditEvent
from app.models.maintenance import MaintenanceWorkOrder
from app.models.workflow_exception import WorkflowException


def _login_as(client, username: str, password: str = "demo-maint-password") -> str:
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_staff_demo_accounts_and_login_flow(client):
    accounts_resp = client.get("/api/v1/auth/demo-accounts")
    assert accounts_resp.status_code == 200
    accounts = accounts_resp.json()
    roles = {a["role"] for a in accounts}
    assert {"DOCTOR", "LAB_OPERATOR", "MAINTENANCE_STAFF", "ADMIN"}.issubset(roles)

    # Valid login for Doctor
    assert all("demo_password" not in account for account in accounts)
    missing_password = client.post("/api/v1/auth/login", json={"username": "dr.sharma"})
    assert missing_password.status_code == 422
    wrong_password = client.post("/api/v1/auth/login", json={"username": "dr.sharma", "password": "wrong"})
    assert wrong_password.status_code == 401
    doc_login = client.post("/api/v1/auth/login", json={"username": "dr.sharma", "password": "demo-doctor-password"})
    assert doc_login.status_code == 200
    doc_data = doc_login.json()
    assert doc_data["staff"]["role"] == "DOCTOR"
    assert doc_data["staff"]["display_name"] == "Dr. Rajesh Sharma"

    # Verify /auth/me with Bearer token
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {doc_data['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "dr.sharma"

    # Unauthenticated /auth/me returns 401
    unauth_me = client.get("/api/v1/auth/me")
    assert unauth_me.status_code == 401

    # Invalid username returns 401
    bad_login = client.post("/api/v1/auth/login", json={"username": "nonexistent.user", "password": "bad"})
    assert bad_login.status_code == 401


def test_maintenance_work_order_lifecycle_and_validation(client, db_session, seeded_hospital_data):
    maint_token = _login_as(client, "maint.karthik")
    headers = {"Authorization": f"Bearer {maint_token}"}

    # 1. Create an OPEN maintenance work order
    create_resp = client.post(
        "/api/v1/maintenance/work-orders",
        headers=headers,
        json={
            "title": "ICU Isolation Room 3 Negative Pressure Sensor Drift",
            "description": "Differential pressure gauge reading -1.2 Pa below safety threshold.",
            "category": "HVAC & Environmental",
            "location": "Block A • 3rd Floor • ICU Bay 3",
            "equipment_reference": "HVAC-AHU-304",
            "priority": "CRITICAL",
            "reported_by": "ICU Charge Nurse",
        },
    )
    assert create_resp.status_code == 201
    wo = create_resp.json()
    wo_id = wo["id"]
    assert wo["status"] == "OPEN"
    assert wo["priority"] == "CRITICAL"
    assert wo["work_order_code"].startswith("MWO-")
    assert "ASSIGNED" in wo["allowed_next_statuses"]

    # 2. Moving to ASSIGNED without assigned_to must fail with 400
    missing_assignee = client.patch(
        f"/api/v1/maintenance/work-orders/{wo_id}/status",
        headers=headers,
        json={"status": "ASSIGNED"},
    )
    assert missing_assignee.status_code == 400
    assert missing_assignee.json()["detail"]["code"] == "ASSIGNEE_REQUIRED"

    # 3. Valid transition OPEN -> ASSIGNED
    assign_resp = client.patch(
        f"/api/v1/maintenance/work-orders/{wo_id}/status",
        headers=headers,
        json={
            "status": "ASSIGNED",
            "assigned_to": "Karthik Subramanian (Biomedical & HVAC Lead)",
        },
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["status"] == "ASSIGNED"
    assert assign_resp.json()["assigned_to"] == "Karthik Subramanian (Biomedical & HVAC Lead)"

    # 4. Valid transition ASSIGNED -> IN_PROGRESS
    prog_resp = client.patch(
        f"/api/v1/maintenance/work-orders/{wo_id}/status",
        headers=headers,
        json={
            "status": "IN_PROGRESS",
            "resolution_notes": "Inspecting damper actuator linkage and recalibrating sensor.",
        },
    )
    assert prog_resp.status_code == 200
    assert prog_resp.json()["status"] == "IN_PROGRESS"

    # 5. Invalid transition IN_PROGRESS -> OPEN must be rejected with 400
    invalid_trans = client.patch(
        f"/api/v1/maintenance/work-orders/{wo_id}/status",
        headers=headers,
        json={"status": "OPEN"},
    )
    assert invalid_trans.status_code == 400
    assert invalid_trans.json()["detail"]["code"] == "INVALID_STATUS_TRANSITION"

    # 6. Valid transition IN_PROGRESS -> RESOLVED
    resolve_resp = client.patch(
        f"/api/v1/maintenance/work-orders/{wo_id}/status",
        headers=headers,
        json={
            "status": "RESOLVED",
            "resolution_notes": "Replaced differential pressure transducer; verified -2.8 Pa pressure.",
        },
    )
    assert resolve_resp.status_code == 200
    resolved_wo = resolve_resp.json()
    assert resolved_wo["status"] == "RESOLVED"
    assert resolved_wo["resolved_at"] is not None

    # 7. Verify summary metrics and audit events
    summary_resp = client.get("/api/v1/maintenance/summary", headers=headers)
    assert summary_resp.status_code == 200
    assert summary_resp.json()["resolved_count"] >= 1

    audits = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_type == "MaintenanceWorkOrder",
                AuditEvent.entity_id == wo_id,
            )
        ).all()
    )
    assert len(audits) >= 4


def test_role_based_access_control_enforcement_across_dashboards(client, seeded_hospital_data):
    doc_token = _login_as(client, "dr.sharma", "demo-doctor-password")
    lab_token = _login_as(client, "lab.vikram", "demo-lab-password")
    maint_token = _login_as(client, "maint.karthik")

    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    lab_headers = {"Authorization": f"Bearer {lab_token}"}
    maint_headers = {"Authorization": f"Bearer {maint_token}"}

    appt_id = seeded_hospital_data["existing_appt"].id
    lab_id = seeded_hospital_data["lab_pending"].id

    # 1. Unauthenticated access to maintenance endpoints is rejected with 401
    unauth_maint = client.get("/api/v1/maintenance/work-orders")
    assert unauth_maint.status_code == 401

    # Unauthenticated web client access to doctor complete endpoint is rejected with 401
    unauth_doc = client.post(
        f"/api/v1/appointments/{appt_id}/complete",
        headers={"X-MediVoice-Client": "web"},
        json={"notes": "Attempt without auth"},
    )
    assert unauth_doc.status_code == 401

    # 2. Doctor role CANNOT access maintenance work orders or mutate lab order statuses (403 Forbidden)
    doc_to_maint = client.post(
        "/api/v1/maintenance/work-orders",
        headers=doc_headers,
        json={
            "title": "Unauthorized Doctor Maintenance Request",
            "description": "Doctor attempting to use maintenance staff API directly.",
            "category": "Biomedical Equipment",
            "location": "Suite 102",
            "priority": "LOW",
        },
    )
    assert doc_to_maint.status_code == 403
    assert doc_to_maint.json()["detail"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"

    doc_to_lab = client.patch(
        f"/api/v1/lab-orders/{lab_id}/status",
        headers=doc_headers,
        json={"workflow_status": "PROCESSING"},
    )
    assert doc_to_lab.status_code == 403

    # 3. Lab Operator role CANNOT complete doctor appointments or access maintenance work orders (403 Forbidden)
    lab_to_doc = client.post(
        f"/api/v1/appointments/{appt_id}/complete",
        headers=lab_headers,
        json={"notes": "Lab operator trying to complete appointment"},
    )
    assert lab_to_doc.status_code == 403

    lab_to_maint = client.get("/api/v1/maintenance/work-orders", headers=lab_headers)
    assert lab_to_maint.status_code == 403

    # 4. Maintenance Staff role CANNOT complete doctor appointments or mutate lab order statuses (403 Forbidden)
    maint_to_doc = client.post(
        f"/api/v1/appointments/{appt_id}/complete",
        headers=maint_headers,
        json={"notes": "Maintenance staff trying to complete appointment"},
    )
    assert maint_to_doc.status_code == 403

    maint_to_lab = client.patch(
        f"/api/v1/lab-orders/{lab_id}/status",
        headers=maint_headers,
        json={"workflow_status": "COMPLETED"},
    )
    assert maint_to_lab.status_code == 403

    # 5. Authorized roles succeed on their respective domain endpoints
    valid_lab = client.patch(
        f"/api/v1/lab-orders/{lab_id}/status",
        headers=lab_headers,
        json={"workflow_status": "SAMPLE_COLLECTED"},
    )
    assert valid_lab.status_code == 200
    assert valid_lab.json()["lab_status"] == "SAMPLE_COLLECTED"

    valid_doc = client.post(
        f"/api/v1/appointments/{appt_id}/complete",
        headers=doc_headers,
        json={"notes": "Completed by authorized Doctor"},
    )
    assert valid_doc.status_code == 200
    assert valid_doc.json()["appointment_status"] == "COMPLETED"


def test_insurance_human_support_ticket_creation(client, db_session, seeded_hospital_data):
    resp = client.post(
        "/api/v1/insurance/support-tickets",
        json={
            "patient_reference": "PAT-2026-8812",
            "provider_name": "Aarogya Shield Health Insurance",
            "plan_name": "Aarogya Gold Cashless",
            "question": "Does my policy waive the 24-month waiting period for arthroscopic meniscus repair under corporate continuity?",
            "contact_preference": "Insurance Desk Counter 3 / Callback",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ticket_id"]
    assert data["patient_reference"] == "PAT-2026-8812"
    assert data["status"] == "OPEN"
    assert data["assigned_department"] == "Insurance & TPA Helpdesk"
    assert "does not guarantee coverage" in data["disclaimer"]

    # Verify persisted in WorkflowException table
    exc = db_session.scalars(
        select(WorkflowException).where(WorkflowException.id == data["ticket_id"])
    ).first()
    assert exc is not None
    assert exc.exception_type == "INSURANCE_SUPPORT_TICKET"

    # Ticket details are staff-only; patients receive a ticket confirmation at creation.
    list_resp = client.get("/api/v1/insurance/support-tickets?patient_reference=PAT-2026-8812")
    assert list_resp.status_code == 401
    staff_token = _login_as(client, "maint.karthik")
    list_resp = client.get(
        "/api/v1/insurance/support-tickets?patient_reference=PAT-2026-8812",
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert list_resp.status_code == 200
    tickets = list_resp.json()
    assert len(tickets) == 1
    assert tickets[0]["ticket_id"] == data["ticket_id"]


def test_maintenance_add_remove_doctors_and_insurance(client, seeded_hospital_data):
    maint_token = _login_as(client, "maint.karthik")
    maint_headers = {"Authorization": f"Bearer {maint_token}"}

    # 1. Add a new Doctor via Maintenance role
    add_doc_resp = client.post(
        "/api/v1/doctors",
        headers=maint_headers,
        json={
            "display_name": "Dr. Kavita Reddy",
            "specialty": "Cardiology",
            "department_name": "Cardiology",
        },
    )
    assert add_doc_resp.status_code == 201
    created_doc = add_doc_resp.json()
    assert created_doc["display_name"] == "Dr. Kavita Reddy"
    assert created_doc["is_active"] is True

    # Verify 6 open slots were automatically seeded for the new doctor
    slots_resp = client.get(f"/api/v1/doctors/{created_doc['id']}/slots")
    assert slots_resp.status_code == 200
    assert len(slots_resp.json()) == 6

    # 2. Remove the Doctor via Maintenance role
    del_doc_resp = client.delete(
        f"/api/v1/doctors/{created_doc['id']}",
        headers=maint_headers,
    )
    assert del_doc_resp.status_code == 200
    assert del_doc_resp.json()["is_active"] is False

    # 3. Add a new Insurance Provider & Plan via Maintenance role
    add_ins_resp = client.post(
        "/api/v1/insurance/providers",
        headers=maint_headers,
        json={
            "name": "NavaBharat Health Assurance",
            "code": "INS-NAVA",
            "support_contact": "1800-100-4299",
            "plan_name": "NavaBharat Platinum Cashless Care",
            "plan_type": "Family Floater & Cashless",
            "covered_services": "Cardiology, Neurology, Diagnostics",
            "cashless_available": True,
        },
    )
    assert add_ins_resp.status_code == 201
    created_ins = add_ins_resp.json()
    assert created_ins["name"] == "NavaBharat Health Assurance"
    assert len(created_ins["plans"]) == 1

    # 4. Remove the Insurance Provider via Maintenance role
    del_ins_resp = client.delete(
        f"/api/v1/insurance/providers/{created_ins['id']}",
        headers=maint_headers,
    )
    assert del_ins_resp.status_code == 200
    assert del_ins_resp.json()["is_active"] is False

