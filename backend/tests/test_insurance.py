import pytest


def test_list_active_insurance_providers_excludes_inactive(client, seeded_hospital_data):
    """GET /api/v1/insurance/providers returns only active providers and active plans."""
    resp = client.get("/api/v1/insurance/providers")
    assert resp.status_code == 200
    providers = resp.json()
    assert len(providers) == 2

    names = [p["name"] for p in providers]
    assert "Aarogya Shield Health Insurance" in names
    assert "Bharat Care Assurance" in names
    assert "Legacy Metro Assurance (Inactive)" not in names

    for prov in providers:
        assert prov["is_active"] is True
        assert "does not guarantee coverage" in prov["disclaimer"]
        for plan in prov["plans"]:
            assert plan["is_active"] is True
            assert plan["coverage_summary"]
            assert plan["copay_summary"]


def test_get_provider_plans_and_inactive_provider_404(client, seeded_hospital_data):
    """GET /api/v1/insurance/providers/{id}/plans returns active plans or 404 for inactive/unknown provider."""
    resp = client.get("/api/v1/insurance/providers/ins-prov-aarogya-shield/plans")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Aarogya Shield Health Insurance"
    assert len(data["plans"]) == 2
    plan_names = {p["plan_name"] for p in data["plans"]}
    assert "Aarogya Gold Cashless" in plan_names
    assert "Aarogya Senior Care" in plan_names
    assert "does not guarantee coverage" in data["disclaimer"]

    # Inactive provider must return 404
    r_inactive = client.get("/api/v1/insurance/providers/ins-prov-inactive/plans")
    assert r_inactive.status_code == 404

    # Unknown provider must return 404
    r_unknown = client.get("/api/v1/insurance/providers/non-existent-provider/plans")
    assert r_unknown.status_code == 404


def test_search_insurance_by_provider_plan_type_service_and_cashless(client, seeded_hospital_data):
    """GET /api/v1/insurance/search filters accurately by provider_name, plan_type, service, and cashless."""
    # 1. Search by provider_name
    r_prov = client.get("/api/v1/insurance/search", params={"provider_name": "Aarogya Shield"})
    assert r_prov.status_code == 200
    d_prov = r_prov.json()
    assert d_prov["matched_count"] == 1
    assert d_prov["providers"][0]["name"] == "Aarogya Shield Health Insurance"
    assert len(d_prov["providers"][0]["plans"]) == 2

    # 2. Search by plan_type
    r_type = client.get("/api/v1/insurance/search", params={"plan_type": "Senior Citizen"})
    assert r_type.status_code == 200
    d_type = r_type.json()
    assert d_type["matched_count"] == 1
    assert d_type["providers"][0]["plans"][0]["plan_name"] == "Aarogya Senior Care"

    # 3. Search by covered service (OPD)
    r_srv = client.get("/api/v1/insurance/search", params={"service": "OPD"})
    assert r_srv.status_code == 200
    d_srv = r_srv.json()
    assert d_srv["matched_count"] >= 1
    all_plans = [pl for pr in d_srv["providers"] for pl in pr["plans"]]
    assert any("OPD" in pl["coverage_summary"] for pl in all_plans)

    # 4. Search by cashless=true vs cashless=false
    r_cashless = client.get("/api/v1/insurance/search", params={"cashless": "true"})
    assert r_cashless.status_code == 200
    d_cashless = r_cashless.json()
    assert d_cashless["matched_count"] == 1
    assert all(pl["cashless_available"] is True for pl in d_cashless["providers"][0]["plans"])

    r_reimb_only = client.get("/api/v1/insurance/search", params={"cashless": "false"})
    assert r_reimb_only.status_code == 200
    d_reimb_only = r_reimb_only.json()
    assert d_reimb_only["matched_count"] == 1
    assert d_reimb_only["providers"][0]["name"] == "Bharat Care Assurance"
    assert d_reimb_only["providers"][0]["plans"][0]["cashless_available"] is False
    assert d_reimb_only["providers"][0]["plans"][0]["reimbursement_available"] is True

    # 5. Search for unsupported / inactive provider returns 0 matches + desk contact + disclaimer
    r_unsupported = client.get("/api/v1/insurance/search", params={"provider_name": "Legacy Metro"})
    assert r_unsupported.status_code == 200
    d_unsupported = r_unsupported.json()
    assert d_unsupported["matched_count"] == 0
    assert d_unsupported["providers"] == []
    assert "1800-100-4200" in d_unsupported["insurance_desk_contact"]["phone"]
    assert "does not guarantee coverage" in d_unsupported["disclaimer"]


def test_insurance_desk_contact_endpoint(client, seeded_hospital_data):
    """GET /api/v1/insurance/contact returns Hospital Insurance Desk contact and disclaimer."""
    resp = client.get("/api/v1/insurance/contact")
    assert resp.status_code == 200
    data = resp.json()
    assert data["department"] == "Aarogya One Hospital — Insurance & TPA Helpdesk"
    assert "1800-100-4200" in data["phone"]
    assert "does not guarantee coverage" in data["disclaimer"]
