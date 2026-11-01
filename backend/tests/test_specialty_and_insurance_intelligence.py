"""
Regression test suite for MediVoice AI Specialty Recognition and Insurance Query Intelligence.

Covers:
1. "I want to meet a cardiologist" directly identifies Cardiology.
2. "Cardioligist" (typo) is normalized to Cardiology.
3. "I need a cardiology consultation" does not trigger a generic specialty question.
4. "I want to see a neurologist" identifies Neurology.
5. Specialty persists across conversational turns.
6. Symptoms remain optional when a specialty or doctor intent is explicit.
7. Doctor search occurs only when appropriate (after patient confirms consultation offer).
8. "Is Max Insurance accepted?" searches only the requested provider.
9. A matching provider returns only its matching plans.
10. An unknown provider does not return the entire catalogue.
11. A general request for all providers returns the complete catalogue.
12. Plan-specific questions return relevant plan information only.
13. Treatment coverage questions explain policy eligibility and TPA pre-authorization without guaranteeing claim approval.
14. No invented insurance-provider matches or coverage terms.
15. English and Indic languages (Telugu and Hindi) are thoroughly tested.
"""

import pytest
from app.models.doctor import Doctor
from app.models.insurance import InsuranceProvider, InsurancePlan


def test_scenario_1_want_to_meet_cardiologist_identifies_cardiology(client, seeded_hospital_data):
    """1. 'I want to meet a cardiologist' directly identifies Cardiology and offers consultation."""
    session_id = "test-spec-1-meet-cardiologist"
    resp = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "I want to meet a cardiologist"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["draft"]["specialty"] == "Cardiology"
    # Should offer consultation without needing symptoms
    assert "Cardiology" in data["reply"]
    assert "find an available cardiologist" in data["reply"].lower() or "check" in data["reply"].lower()
    assert "Which specialty or physician do you need consultation for?" not in data["reply"]


def test_scenario_2_cardioligist_typo_normalized_to_cardiology(client, seeded_hospital_data):
    """2. 'Cardioligist' typo is normalized to Cardiology."""
    session_id = "test-spec-2-typo-cardioligist"
    resp = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "Cardioligist."
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["draft"]["specialty"] == "Cardiology"
    assert "Cardiology" in data["reply"]
    assert "Could you let me know what symptoms you are experiencing" not in data["reply"]


def test_scenario_3_cardiology_consultation_no_generic_specialty_question(client, seeded_hospital_data):
    """3. 'I need a cardiology consultation' does not trigger a specialty question."""
    session_id = "test-spec-3-consultation"
    resp = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "I need a cardiology consultation"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["draft"]["specialty"] == "Cardiology"
    assert "Which specialty or physician do you need consultation for?" not in data["reply"]
    assert "Cardiology" in data["reply"]


def test_scenario_4_want_to_see_neurologist_identifies_neurology(client, seeded_hospital_data):
    """4. 'I want to see a neurologist' identifies Neurology."""
    session_id = "test-spec-4-neurologist"
    resp = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "I want to see a neurologist"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["draft"]["specialty"] == "Neurology"
    assert "Neurology" in data["reply"]
    assert "neurologist" in data["reply"].lower()


def test_scenario_5_specialty_persists_across_turns(client, seeded_hospital_data):
    """5. Specialty persists across multiple conversation turns."""
    session_id = "test-spec-5-persist"
    r1 = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "I need an orthopedist"
    })
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["draft"]["specialty"] == "Orthopedics"

    # Next turn: patient says yes to find doctor
    r2 = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "Yes please"
    })
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["draft"]["specialty"] == "Orthopedics"


def test_scenario_6_symptoms_optional_when_specialty_explicit(client, seeded_hospital_data):
    """6. Symptoms remain optional when a specialty or physician is explicitly provided."""
    session_id = "test-spec-6-symptoms-optional"
    resp = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "I am thinking to meet dermatologist."
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["draft"]["specialty"] == "Dermatology"
    # Does not demand symptoms before proceeding
    assert "Could you let me know what symptoms you are experiencing" not in data["reply"]
    assert "Dermatology" in data["reply"]


def test_scenario_7_doctor_search_occurs_after_confirmation(client, seeded_hospital_data):
    """7. Doctor search occurs only when appropriate (e.g. after patient confirms consultation offer)."""
    session_id = "test-spec-7-search-after-confirm"
    # Turn 1: Patient expresses intent
    r1 = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "I am thinking of meeting a cardiologist."
    })
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["draft"]["specialty"] == "Cardiology"
    # Should not have called search_doctors yet in turn 1
    assert "Would you like me to find an available cardiologist?" in d1["reply"]

    # Turn 2: Patient confirms
    r2 = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "Yes."
    })
    assert r2.status_code == 200
    d2 = r2.json()
    # Now doctor search has run and doctor recommendation is presented
    assert "Dr. Rajesh Sharma" in d2["reply"]
    assert "Cardiology" in d2["reply"] or "cardiologist" in d2["reply"].lower()


def test_scenario_8_max_insurance_searches_only_requested_provider(client, seeded_hospital_data):
    """8. 'Is Max Insurance accepted?' searches only Max and reports result accurately."""
    session_id = "test-ins-8-max"
    resp = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "Is Max Insurance accepted at Aarogya One Hospital?"
    })
    assert resp.status_code == 200
    data = resp.json()
    reply = data["reply"]
    assert "Max" in reply
    # Active hospital network does not list Max Insurance; must report clearly without dumping other providers
    assert "not currently listed" in reply.lower() or "not currently part" in reply.lower()
    assert "Star Health" not in reply
    assert "Bharat Care" not in reply
    assert "Aarogya Shield" not in reply
    assert "1800-100-4200" in reply or "desk" in reply.lower()


def test_scenario_9_matching_provider_returns_only_matching_plans(client, seeded_hospital_data):
    """9. A matching provider (Bharat Care) returns only its matching plans and offer."""
    session_id = "test-ins-9-bharat"
    resp = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "Do you accept Bharat Care Assurance?"
    })
    assert resp.status_code == 200
    data = resp.json()
    reply = data["reply"]
    assert "Bharat Care" in reply
    assert "Bharat Care Basic Reimbursement" in reply
    # Must NOT dump other unrelated providers
    assert "Aarogya Gold Cashless" not in reply
    assert "check a particular treatment or consultation" in reply


def test_scenario_10_unknown_provider_does_not_return_entire_catalogue(client, seeded_hospital_data):
    """10. An unknown provider does not return the entire catalogue."""
    session_id = "test-ins-10-unknown"
    resp = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "Do you take Reliance General Insurance?"
    })
    assert resp.status_code == 200
    data = resp.json()
    reply = data["reply"]
    assert "Reliance General" in reply
    assert "not currently listed in" in reply or "not currently part of" in reply
    # Entire catalogue should NOT be dumped
    assert "Aarogya Gold Cashless" not in reply
    assert "Bharat Care Basic" not in reply
    assert "1800-100-4200" in reply


def test_scenario_11_general_request_returns_complete_catalogue(client, seeded_hospital_data):
    """11. A general request for all accepted insurance providers returns the full active catalogue."""
    session_id = "test-ins-11-general"
    resp = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "What insurance providers do you accept? Give me the full list."
    })
    assert resp.status_code == 200
    data = resp.json()
    reply = data["reply"]
    assert "Aarogya Shield Health Insurance" in reply
    assert "Bharat Care Assurance" in reply
    assert "Disclaimer: Informational only" in reply


def test_scenario_12_plan_specific_questions_return_plan_info(client, seeded_hospital_data):
    """12. Plan-specific questions return relevant plan information only."""
    session_id = "test-ins-12-plan"
    resp = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "Tell me about the Aarogya Senior Care Plan"
    })
    assert resp.status_code == 200
    data = resp.json()
    reply = data["reply"]
    assert "Aarogya Senior Care" in reply
    assert "Bharat Care Basic" not in reply


def test_scenario_13_treatment_coverage_explains_preauth_and_no_guarantee(client, seeded_hospital_data):
    """13. Treatment coverage questions explain policy eligibility & TPA pre-authorization without guaranteeing claim approval."""
    session_id = "test-ins-13-treatment"
    resp = client.post("/api/v1/agent/chat", json={
        "session_id": session_id,
        "message": "Is angioplasty surgery covered under my insurance?"
    })
    assert resp.status_code == 200
    data = resp.json()
    reply = data["reply"]
    assert "pre-authorization" in reply.lower() or "pre-auth" in reply.lower()
    assert "tpa" in reply.lower()
    assert "cannot be guaranteed" in reply.lower() or "not guarantee" in reply.lower()
    assert "48" in reply or "waiting periods" in reply.lower()


def test_scenario_14_no_invented_insurance_matches():
    """14. No invented insurance-provider matches or coverage terms."""
    from app.agent.adapters import extract_insurance_search_filters, format_insurance_search_reply

    # Provider extraction strictly returns recognized or explicitly stated names, not arbitrary words
    filters = extract_insurance_search_filters("naaku cashless hospital details kavali")
    assert filters.get("provider_name") is None

    # Empty provider query yields clear error without fabrication
    mock_data = {
        "providers": [],
        "plans": [],
        "searched_filters": {"provider_name": "NonExistentHealthCo"},
    }
    reply = format_insurance_search_reply("en", mock_data, user_message="NonExistentHealthCo coverage")
    assert "NonExistentHealthCo" in reply
    assert "not currently listed in" in reply or "not currently part of" in reply


def test_scenario_15_multilingual_indic_language_specialty_and_insurance(client, seeded_hospital_data):
    """15. English and Indic languages (Telugu and Hindi) support specialty and insurance intelligence."""
    # Telugu: "నాకు కార్డియాలజిస్ట్ కావాలి" (I need a cardiologist)
    session_te = "test-spec-15-telugu"
    r_te = client.post("/api/v1/agent/chat", json={
        "session_id": session_te,
        "message": "నాకు కార్డియాలజిస్ట్ కన్సల్టేషన్ కావాలి"
    })
    assert r_te.status_code == 200
    d_te = r_te.json()
    assert d_te["draft"]["specialty"] == "Cardiology"
    assert "Cardiology" in d_te["reply"]

    # Hindi: "क्या Aarogya One Hospital में Bharat Care स्वीकार किया जाता है?"
    session_hi = "test-ins-15-hindi"
    r_hi = client.post("/api/v1/agent/chat", json={
        "session_id": session_hi,
        "message": "क्या Aarogya One Hospital में Bharat Care बीमा स्वीकार किया जाता है?"
    })
    assert r_hi.status_code == 200
    d_hi = r_hi.json()
    assert "Bharat Care" in d_hi["reply"]
    assert "डेस्क" in d_hi["reply"] or "desk" in d_hi["reply"].lower()
