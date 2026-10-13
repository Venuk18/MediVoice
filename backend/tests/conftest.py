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
from app.models.lab_order import LabOrder

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
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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

    # Overdue lab order for testing workflow
    lab_overdue = LabOrder(
        id="lab-overdue-1",
        patient_reference="PAT-OVERDUE-01",
        ordering_department_id=cardio.id,
        test_category="Cardiac Enzymes",
        workflow_status="Processing",
        expected_completion_at=now_utc - timedelta(hours=4),
        assigned_team="Biochemistry Stat",
    )
    # Non-overdue lab order
    lab_pending = LabOrder(
        id="lab-pending-2",
        patient_reference="PAT-PENDING-02",
        ordering_department_id=neuro.id,
        test_category="EEG Workup",
        workflow_status="Pending",
        expected_completion_at=now_utc + timedelta(hours=8),
        assigned_team="Neuro Techs",
    )
    db_session.add_all([lab_overdue, lab_pending])

    db_session.commit()

    return {
        "hospital": hosp,
        "cardio_dept": cardio,
        "neuro_dept": neuro,
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
    }
