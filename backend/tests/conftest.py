import os
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.hospital import Hospital
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.appointment_slot import AppointmentSlot
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.lab_order import LabOrder
from app.models.insurance import InsuranceProvider, InsurancePlan
from app.services.lab_service import reset_verification_rate_limits

# Use isolated SQLite in-memory database with StaticPool for fast, thread-safe tests
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """Create fresh schema for each test function and clean up afterwards."""
    reset_verification_rate_limits()
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)
        reset_verification_rate_limits()


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency and offline MockReasoningAdapter default."""
    from app.agent.conversation_manager import conversation_manager
    from app.agent.adapters import MockReasoningAdapter

    reset_verification_rate_limits()
    previous_adapter = conversation_manager.adapter
    conversation_manager.adapter = MockReasoningAdapter()
    conversation_manager._sessions.clear()
    conversation_manager._voice_selected_languages.clear()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    conversation_manager.adapter = previous_adapter
    conversation_manager._sessions.clear()
    conversation_manager._voice_selected_languages.clear()
    reset_verification_rate_limits()


@pytest.fixture
def seeded_hospital_data(db_session):
    """Standard seeded environment for test assertions."""
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)

    # Hospital
    hosp = Hospital(
        id="test-hosp-1",
        name="Aarogya One Hospital",
        description="Fictional Multi-Specialty Hospital",
        address="Outer Ring Road, Bengaluru",
        is_active=True,
    )
    db_session.add(hosp)

    # Departments
    cardio = Department(
        id="test-dept-cardio",
        hospital_id=hosp.id,
        name="Cardiology",
        description="Cardiovascular Medicine",
        is_active=True,
    )
    neuro = Department(
        id="test-dept-neuro",
        hospital_id=hosp.id,
        name="Neurology",
        description="Neuroscience and Stroke Care",
        is_active=True,
    )
    db_session.add_all([cardio, neuro])
    db_session.flush()

    # Doctors
    doc1 = Doctor(
        id="doc-sharma-1",
        hospital_id=hosp.id,
        department_id=cardio.id,
        display_name="Dr. Rajesh Sharma",
        specialty="Cardiology",
        is_active=True,
    )
    doc2 = Doctor(
        id="doc-nair-2",
        hospital_id=hosp.id,
        department_id=neuro.id,
        display_name="Dr. Priya Nair",
        specialty="Neurology",
        is_active=True,
    )
    doc_inactive = Doctor(
        id="doc-inactive-3",
        hospital_id=hosp.id,
        department_id=cardio.id,
        display_name="Dr. Inactive Doctor",
        specialty="Cardiology",
        is_active=False,
    )
    db_session.add_all([doc1, doc2, doc_inactive])
    db_session.flush()

    # Slots for Dr. Sharma (future slots)
    slot1 = AppointmentSlot(
        id="slot-sharma-avail-1",
        doctor_id=doc1.id,
        start_time=now_utc + timedelta(days=1, hours=2),
        end_time=now_utc + timedelta(days=1, hours=2, minutes=30),
        status="AVAILABLE",
    )
    slot2 = AppointmentSlot(
        id="slot-sharma-avail-2",
        doctor_id=doc1.id,
        start_time=now_utc + timedelta(days=2, hours=3),
        end_time=now_utc + timedelta(days=2, hours=3, minutes=30),
        status="AVAILABLE",
    )
    slot_booked = AppointmentSlot(
        id="slot-sharma-booked-3",
        doctor_id=doc1.id,
        start_time=now_utc + timedelta(days=3, hours=1),
        end_time=now_utc + timedelta(days=3, hours=1, minutes=30),
        status="BOOKED",
    )
    # Past slot
    slot_past = AppointmentSlot(
        id="slot-sharma-past-4",
        doctor_id=doc1.id,
        start_time=now_utc - timedelta(days=1),
        end_time=now_utc - timedelta(days=1, minutes=-30),
        status="AVAILABLE",
    )
    # Slot for Dr. Nair
    slot_nair = AppointmentSlot(
        id="slot-nair-avail-1",
        doctor_id=doc2.id,
        start_time=now_utc + timedelta(days=1, hours=4),
        end_time=now_utc + timedelta(days=1, hours=4, minutes=30),
        status="AVAILABLE",
    )
    db_session.add_all([slot1, slot2, slot_booked, slot_past, slot_nair])

    # Existing appointment for slot_booked
    existing_appt = Appointment(
        id="appt-existing-1",
        patient_reference="PAT-EXISTING-99",
        doctor_id=doc1.id,
        slot_id=slot_booked.id,
        appointment_status="CONFIRMED",
        reason_category="Prior Routine Checkup",
    )
    db_session.add(existing_appt)

    # Overdue lab order for testing workflow (with leading-zero 6-digit verification code "048271")
    lab_overdue = LabOrder(
        id="lab-overdue-1",
        patient_reference="PAT-OVERDUE-01",
        ordering_department_id=cardio.id,
        test_name="Cardiac Troponin I & Lipid Profile",
        test_category="Cardiac Enzymes",
        workflow_status="Processing",
        expected_completion_at=now_utc - timedelta(hours=4),
        assigned_team="Biochemistry Stat",
        verification_code="048271",
        verification_code_expires_at=now_utc + timedelta(hours=72),
        verification_code_is_active=True,
    )
    # Non-overdue lab order (with 6-digit verification code "839201")
    lab_pending = LabOrder(
        id="lab-pending-2",
        patient_reference="PAT-PENDING-02",
        ordering_department_id=neuro.id,
        test_name="EEG Workup",
        test_category="EEG Workup",
        workflow_status="Pending",
        expected_completion_at=now_utc + timedelta(hours=8),
        assigned_team="Neuro Techs",
        verification_code="839201",
        verification_code_expires_at=now_utc + timedelta(hours=72),
        verification_code_is_active=True,
    )
    db_session.add_all([lab_overdue, lab_pending])

    # Synthetic Insurance Providers & Plans
    ins_provider_1 = InsuranceProvider(
        id="ins-prov-aarogya-shield",
        hospital_id=hosp.id,
        name="Aarogya Shield Health Insurance",
        code="ASHI-01",
        support_contact="1800-100-4201 (Ext. 402)",
        is_active=True,
    )
    ins_provider_2 = InsuranceProvider(
        id="ins-prov-bharat-care",
        hospital_id=hosp.id,
        name="Bharat Care Assurance",
        code="BCA-02",
        support_contact="1800-200-8810 (Ext. 403)",
        is_active=True,
    )
    ins_provider_inactive = InsuranceProvider(
        id="ins-prov-inactive",
        hospital_id=hosp.id,
        name="Legacy Metro Assurance (Inactive)",
        code="LMA-99",
        support_contact="N/A",
        is_active=False,
    )
    db_session.add_all([ins_provider_1, ins_provider_2, ins_provider_inactive])
    db_session.flush()

    ins_plan_1 = InsurancePlan(
        id="ins-plan-gold-1",
        provider_id=ins_provider_1.id,
        plan_name="Aarogya Gold Cashless",
        plan_type="Individual & Family Floater",
        coverage_summary="Comprehensive inpatient hospitalization, ICU, cardiology, neurology, and OPD consultations.",
        covered_services="Inpatient Hospitalization, ICU, Cardiology Procedures, Neurology Care, OPD Consultations",
        copay_summary="0% co-pay in standard private room; 10% co-pay in luxury suite.",
        preauthorization_required=True,
        cashless_available=True,
        reimbursement_available=True,
        network_notes="24/7 cashless pre-authorization at Aarogya One Insurance Desk.",
        is_active=True,
    )
    ins_plan_2 = InsurancePlan(
        id="ins-plan-senior-2",
        provider_id=ins_provider_1.id,
        plan_name="Aarogya Senior Care",
        plan_type="Senior Citizen",
        coverage_summary="Dedicated senior citizen coverage for cardiac care, OPD consultations, and diagnostics.",
        covered_services="Cardiology, Neurology, OPD Consultations, Pathology & Lab Tests, Orthopedics",
        copay_summary="15% co-pay on outpatient consultations and inpatient claims.",
        preauthorization_required=True,
        cashless_available=True,
        reimbursement_available=True,
        network_notes="Present senior citizen policy card at OPD Billing Counter 3.",
        is_active=True,
    )
    ins_plan_3 = InsurancePlan(
        id="ins-plan-bharat-3",
        provider_id=ins_provider_2.id,
        plan_name="Bharat Care Basic Reimbursement",
        plan_type="Family Floater",
        coverage_summary="Covers inpatient medical and surgical admissions, maternity, and pediatrics on reimbursement basis.",
        covered_services="Inpatient Hospitalization, Pediatrics, Maternity, General Medicine, Orthopedic Trauma",
        copay_summary="10% co-pay across all inpatient claims.",
        preauthorization_required=False,
        cashless_available=False,
        reimbursement_available=True,
        network_notes="Reimbursement-only plan; certified discharge documents provided at billing desk.",
        is_active=True,
    )
    ins_plan_inactive = InsurancePlan(
        id="ins-plan-inactive-4",
        provider_id=ins_provider_1.id,
        plan_name="Discontinued Silver Plan",
        plan_type="Legacy",
        coverage_summary="Discontinued plan.",
        covered_services="None",
        copay_summary="50% co-pay.",
        preauthorization_required=True,
        cashless_available=False,
        reimbursement_available=True,
        network_notes="Discontinued.",
        is_active=False,
    )
    db_session.add_all([ins_plan_1, ins_plan_2, ins_plan_3, ins_plan_inactive])

    db_session.commit()

    return {
        "hospital": hosp,
        "cardio_dept": cardio,
        "neuro_dept": neuro,
        "dept_cardio": cardio,
        "dept_neuro": neuro,
        "dept_gen": cardio,
        "doc_sharma": doc1,
        "doc_nair": doc2,
        "doc_inactive": doc_inactive,
        "slot_available": slot1,
        "slot_available_2": slot2,
        "slot_booked": slot_booked,
        "slot_past": slot_past,
        "slot_nair": slot_nair,
        "existing_appt": existing_appt,
        "lab_overdue": lab_overdue,
        "lab_pending": lab_pending,
        "ins_provider_1": ins_provider_1,
        "ins_provider_2": ins_provider_2,
        "ins_provider_inactive": ins_provider_inactive,
        "ins_plan_1": ins_plan_1,
        "ins_plan_2": ins_plan_2,
        "ins_plan_3": ins_plan_3,
        "ins_plan_inactive": ins_plan_inactive,
    }

