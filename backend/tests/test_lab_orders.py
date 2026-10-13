import pytest
from sqlalchemy import select
from app.models.lab_order import LabOrder
from app.models.audit_event import AuditEvent


def test_list_lab_orders(client, seeded_hospital_data):
    response = client.get("/api/v1/lab-orders")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_filter_lab_orders_by_status(client, seeded_hospital_data):
    response = client.get("/api/v1/lab-orders?status=Processing")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["workflow_status"] == "Processing"
    assert data[0]["test_category"] == "Cardiac Enzymes"


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
