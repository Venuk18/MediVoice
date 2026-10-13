from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from app.models.workflow_exception import WorkflowException
from app.models.audit_event import AuditEvent
from app.services.workflow_service import detect_overdue_lab_orders


def test_deterministic_overdue_lab_detection(client, db_session, seeded_hospital_data):
    # Trigger detection
    response = client.post("/api/v1/workflow/exceptions/detect")
    assert response.status_code == 200
    created = response.json()
    assert len(created) == 1
    assert created[0]["exception_type"] == "LAB_ORDER_OVERDUE"
    assert created[0]["priority"] == "HIGH"
    assert created[0]["affected_record_id"] == seeded_hospital_data["lab_overdue"].id

    # Running detection a second time must NOT create duplicate exceptions for the same open issue
    res2 = client.post("/api/v1/workflow/exceptions/detect")
    assert res2.status_code == 200
    assert len(res2.json()) == 0  # No duplicate tasks created


def test_workflow_exception_assignment(client, db_session, seeded_hospital_data):
    # Detect first
    client.post("/api/v1/workflow/exceptions/detect")

    exc = db_session.scalars(select(WorkflowException)).first()
    assert exc is not None
    assert exc.status == "OPEN"

    # Assign exception
    assign_payload = {"assigned_to": "Senior Biochemist Dr. Raman"}
    res_assign = client.post(f"/api/v1/workflow/exceptions/{exc.id}/assign", json=assign_payload)
    assert res_assign.status_code == 200
    data = res_assign.json()
    assert data["assigned_to"] == "Senior Biochemist Dr. Raman"
    assert data["status"] == "IN_PROGRESS"


def test_workflow_exception_resolution(client, db_session, seeded_hospital_data):
    # Detect first
    client.post("/api/v1/workflow/exceptions/detect")
    exc = db_session.scalars(select(WorkflowException)).first()

    resolve_payload = {
        "resolution_note": "Reagent batch QC recalibrated successfully; troponin test released to stat queue."
    }
    res_resolve = client.post(f"/api/v1/workflow/exceptions/{exc.id}/resolve", json=resolve_payload)
    assert res_resolve.status_code == 200
    data = res_resolve.json()
    assert data["status"] == "RESOLVED"
    assert data["resolved_at"] is not None
    assert "recalibrated successfully" in data["resolution_note"]

    # Verify audit event for resolution
    audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "WorkflowException",
            AuditEvent.entity_id == exc.id,
            AuditEvent.action == "EXCEPTION_RESOLVED",
        )
    ).first()
    assert audit is not None


def test_audit_events_endpoint(client, seeded_hospital_data):
    # Query audit events
    response = client.get("/api/v1/workflow/audit-events")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
