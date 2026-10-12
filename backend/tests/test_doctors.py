import pytest
from app.services.doctor_service import search_doctors_tool, get_available_slots_tool


def test_list_all_active_doctors(client, seeded_hospital_data):
    response = client.get("/api/v1/doctors")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # Dr. Sharma and Dr. Nair (inactive excluded)
    names = [d["display_name"] for d in data]
    assert "Dr. Rajesh Sharma" in names
    assert "Dr. Priya Nair" in names
    assert "Dr. Inactive Doctor" not in names


def test_filter_doctors_by_specialty(client, seeded_hospital_data):
    response = client.get("/api/v1/doctors?specialty=Cardiology")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["display_name"] == "Dr. Rajesh Sharma"
    assert data[0]["specialty"] == "Cardiology"


def test_filter_doctors_by_department_name(client, seeded_hospital_data):
    response = client.get("/api/v1/doctors?department_name=Neurology")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["display_name"] == "Dr. Priya Nair"


def test_get_doctor_by_id_success(client, seeded_hospital_data):
    doc_id = seeded_hospital_data["doc_sharma"].id
    response = client.get(f"/api/v1/doctors/{doc_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == doc_id
    assert data["display_name"] == "Dr. Rajesh Sharma"
    assert data["department_name"] == "Cardiology"


def test_get_doctor_by_id_not_found(client, seeded_hospital_data):
    response = client.get("/api/v1/doctors/non-existent-id")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_available_slots_retrieval(client, seeded_hospital_data):
    doc_id = seeded_hospital_data["doc_sharma"].id
    response = client.get(f"/api/v1/doctors/{doc_id}/slots")
    assert response.status_code == 200
    data = response.json()
    # Should only return AVAILABLE slots (slot1 and slot2, plus slot_past is AVAILABLE in DB, but booked slot is excluded)
    statuses = [s["status"] for s in data]
    assert all(s == "AVAILABLE" for s in statuses)
    slot_ids = [s["id"] for s in data]
    assert seeded_hospital_data["slot_booked"].id not in slot_ids


def test_ai_tool_search_doctors(db_session, seeded_hospital_data):
    results = search_doctors_tool(db_session, specialty_or_department="Cardiology")
    assert len(results) == 1
    assert results[0]["display_name"] == "Dr. Rajesh Sharma"
    assert results[0]["specialty"] == "Cardiology"


def test_ai_tool_get_available_slots(db_session, seeded_hospital_data):
    doc_id = seeded_hospital_data["doc_sharma"].id
    results = get_available_slots_tool(db_session, doctor_id=doc_id)
    assert len(results) >= 2
    for item in results:
        assert item["doctor_id"] == doc_id
        assert item["status"] == "AVAILABLE"
