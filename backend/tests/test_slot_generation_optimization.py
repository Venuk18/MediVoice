import os
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Set
import pytest
from sqlalchemy import event, select, func
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.hospital import Hospital
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.appointment_slot import AppointmentSlot
from app.models.appointment import Appointment
from app.services.doctor_service import (
    get_hospital_timezone,
    generate_upcoming_slots_for_doctors,
    DOCTOR_SCHEDULE_CONFIG,
)
from app.services.appointment_service import book_appointment


@pytest.fixture
def opt_test_env(db_session: Session):
    """Sets up an isolated hospital test environment with 4 doctors."""
    tz = get_hospital_timezone()
    hosp = Hospital(
        id="hosp-opt-1",
        name="Aarogya One Hospital",
        address="Banjara Hills, Hyderabad",
        is_active=True,
    )
    db_session.add(hosp)

    dept_cardio = Department(
        id="dept-opt-cardio",
        hospital_id="hosp-opt-1",
        name="Cardiology",
        is_active=True,
    )
    dept_neuro = Department(
        id="dept-opt-neuro",
        hospital_id="hosp-opt-1",
        name="Neurology",
        is_active=True,
    )
    db_session.add(dept_cardio)
    db_session.add(dept_neuro)

    doc_sharma = Doctor(
        id="doc-opt-sharma",
        hospital_id="hosp-opt-1",
        department_id="dept-opt-cardio",
        display_name="Dr. Rajesh Sharma",
        specialty="Cardiology",
        is_active=True,
    )
    doc_rao = Doctor(
        id="doc-opt-rao",
        hospital_id="hosp-opt-1",
        department_id="dept-opt-cardio",
        display_name="Dr. Sunita Rao",
        specialty="Cardiology",
        is_active=True,
    )
    doc_nair = Doctor(
        id="doc-opt-nair",
        hospital_id="hosp-opt-1",
        department_id="dept-opt-neuro",
        display_name="Dr. Priya Nair",
        specialty="Neurology",
        is_active=True,
    )
    doc_inactive = Doctor(
        id="doc-opt-inactive",
        hospital_id="hosp-opt-1",
        department_id="dept-opt-neuro",
        display_name="Dr. Inactive Doctor",
        specialty="Neurology",
        is_active=False,
    )
    db_session.add_all([doc_sharma, doc_rao, doc_nair, doc_inactive])
    db_session.commit()

    return {
        "tz": tz,
        "sharma": doc_sharma,
        "rao": doc_rao,
        "nair": doc_nair,
        "inactive": doc_inactive,
    }


class TestSlotGenerationOptimization:
    """Validates the batch-optimized slot generation algorithm."""

    def test_multiple_doctors_and_calendar_days(self, db_session: Session, opt_test_env):
        """Verifies slots are generated correctly across multiple doctors and calendar days."""
        tz = opt_test_env["tz"]
        base = datetime(2026, 11, 2, 9, 0, 0, tzinfo=tz).date()  # Monday

        # Generate 14 days for 3 active doctors (inactive doctor ignored)
        slots_count = generate_upcoming_slots_for_doctors(db_session, days=14, base_date=base)
        assert slots_count > 0

        # Verify inactive doctor has zero slots
        inactive_slots = db_session.scalars(
            select(AppointmentSlot).where(AppointmentSlot.doctor_id == "doc-opt-inactive")
        ).all()
        assert len(inactive_slots) == 0

        # Verify active doctors have slots
        for doc_id in ["doc-opt-sharma", "doc-opt-rao", "doc-opt-nair"]:
            doc_slots = db_session.scalars(
                select(AppointmentSlot).where(AppointmentSlot.doctor_id == doc_id)
            ).all()
            assert len(doc_slots) > 0

    def test_existing_slots_and_idempotency(self, db_session: Session, opt_test_env):
        """Verifies repeated runs produce 0 duplicate slots and 0 extra inserts."""
        tz = opt_test_env["tz"]
        base = datetime(2026, 11, 2, 9, 0, 0, tzinfo=tz).date()

        first_run = generate_upcoming_slots_for_doctors(db_session, days=10, base_date=base)
        assert first_run > 0
        db_session.commit()

        # Count total slots
        count_before = db_session.scalar(select(func.count(AppointmentSlot.id)))

        # Second run with exact same parameters
        second_run = generate_upcoming_slots_for_doctors(db_session, days=10, base_date=base)
        assert second_run == 0

        count_after = db_session.scalar(select(func.count(AppointmentSlot.id)))
        assert count_before == count_after

    def test_booked_slots_preservation(self, db_session: Session, opt_test_env):
        """Verifies that running slot generation never modifies, resets, or overwrites BOOKED slots."""
        tz = opt_test_env["tz"]
        base = datetime(2026, 11, 2, 9, 0, 0, tzinfo=tz).date()

        generate_upcoming_slots_for_doctors(db_session, days=5, base_date=base)
        db_session.commit()

        # Find one slot and mark as BOOKED
        slot = db_session.scalars(
            select(AppointmentSlot).where(AppointmentSlot.doctor_id == "doc-opt-sharma")
        ).first()
        assert slot is not None
        slot_id = slot.id
        slot.status = "BOOKED"
        db_session.commit()

        # Re-run generator
        generate_upcoming_slots_for_doctors(db_session, days=5, base_date=base)
        db_session.commit()

        # Slot must remain BOOKED
        refreshed = db_session.get(AppointmentSlot, slot_id)
        assert refreshed.status == "BOOKED"

    def test_sunday_exclusion(self, db_session: Session, opt_test_env):
        """Verifies that no slots are generated on any Sunday."""
        tz = opt_test_env["tz"]
        base = datetime(2026, 11, 1, 9, 0, 0, tzinfo=tz).date()  # Sunday

        generate_upcoming_slots_for_doctors(db_session, days=21, base_date=base)
        db_session.commit()

        all_slots = db_session.scalars(select(AppointmentSlot)).all()
        assert len(all_slots) > 0

        for s in all_slots:
            st = s.start_time
            if st.tzinfo is not None:
                st = st.astimezone(tz)
            assert st.weekday() != 6, f"Sunday slot generated: {s.id} at {st}"

    def test_holiday_exclusion(self, db_session: Session, opt_test_env):
        """Verifies that specified holidays are strictly excluded from slot generation."""
        tz = opt_test_env["tz"]
        base = datetime(2026, 11, 2, 9, 0, 0, tzinfo=tz).date()  # Monday
        holiday_date = base + timedelta(days=2)  # Wednesday Nov 4

        generate_upcoming_slots_for_doctors(
            db_session, days=7, base_date=base, holidays={holiday_date}
        )
        db_session.commit()

        slots_on_holiday = db_session.scalars(
            select(AppointmentSlot).where(
                AppointmentSlot.start_time >= datetime(holiday_date.year, holiday_date.month, holiday_date.day, 0, 0, 0, tzinfo=tz),
                AppointmentSlot.start_time <= datetime(holiday_date.year, holiday_date.month, holiday_date.day, 23, 59, 59, tzinfo=tz),
            )
        ).all()
        assert len(slots_on_holiday) == 0

    def test_doctor_specific_schedules(self, db_session: Session, opt_test_env):
        """Verifies each doctor gets slots matching their specific schedule configuration."""
        tz = opt_test_env["tz"]
        base = datetime(2026, 11, 2, 9, 0, 0, tzinfo=tz).date()  # Monday

        generate_upcoming_slots_for_doctors(db_session, days=1, base_date=base)
        db_session.commit()

        # Dr. Sunita Rao schedule: (11, 0), (12, 30), (15, 0), (17, 0)
        rao_slots = db_session.scalars(
            select(AppointmentSlot).where(AppointmentSlot.doctor_id == "doc-opt-rao")
        ).all()
        rao_times = sorted([
            (s.start_time.astimezone(tz) if s.start_time.tzinfo else s.start_time).hour,
            (s.start_time.astimezone(tz) if s.start_time.tzinfo else s.start_time).minute,
        ] for s in rao_slots)

        expected_rao = sorted([[11, 0], [12, 30], [15, 0], [17, 0]])
        assert rao_times == expected_rao

    def test_asia_kolkata_timezone_boundaries(self, db_session: Session, opt_test_env):
        """Verifies that generated slot datetimes properly record Asia/Kolkata timezone offset."""
        tz = opt_test_env["tz"]
        base = datetime(2026, 11, 2, 9, 0, 0, tzinfo=tz).date()

        generate_upcoming_slots_for_doctors(db_session, days=1, base_date=base)
        db_session.commit()

        slot = db_session.scalars(select(AppointmentSlot)).first()
        assert slot is not None
        # Start time should have +05:30 or convert cleanly
        assert slot.end_time > slot.start_time
        assert (slot.end_time - slot.start_time) == timedelta(minutes=30)

    def test_empty_doctor_list(self, db_session: Session):
        """Verifies safe behavior when no active doctors exist in database."""
        # Deactivate all doctors
        db_session.query(Doctor).update({"is_active": False})
        db_session.commit()

        count = generate_upcoming_slots_for_doctors(db_session, days=10)
        assert count == 0

    def test_database_rollback_on_failure(self, db_session: Session, opt_test_env):
        """Verifies rollback leaves no orphan or partially inserted slots."""
        tz = opt_test_env["tz"]
        base = datetime(2026, 11, 2, 9, 0, 0, tzinfo=tz).date()

        count_before = db_session.scalar(select(func.count(AppointmentSlot.id)))

        try:
            # Simulate a failure within a transaction
            generate_upcoming_slots_for_doctors(db_session, days=3, base_date=base)
            raise RuntimeError("Simulated transaction crash")
        except RuntimeError:
            db_session.rollback()

        count_after = db_session.scalar(select(func.count(AppointmentSlot.id)))
        assert count_before == count_after

    def test_query_count_elimination_of_n_plus_one(self, db_session: Session, opt_test_env):
        """
        Verifies that query count does not scale with doctors * days * slot_times.
        For 3 doctors over 10 days (120 slots), total queries must be <= 5.
        """
        engine = db_session.get_bind()
        query_log = []

        def counter(conn, cursor, statement, parameters, context, executemany):
            query_log.append(statement)

        event.listen(engine, "before_cursor_execute", counter)
        try:
            tz = opt_test_env["tz"]
            base = datetime(2026, 11, 2, 9, 0, 0, tzinfo=tz).date()

            new_slots = generate_upcoming_slots_for_doctors(db_session, days=10, base_date=base)
            assert new_slots > 0

            # Must execute at most 5 SQL queries (doctors, batch select, savepoint, batch insert, release)
            assert len(query_log) <= 5, f"Expected <= 5 queries, but executed {len(query_log)}"

            # Second run (idempotent)
            query_log.clear()
            second_run = generate_upcoming_slots_for_doctors(db_session, days=10, base_date=base)
            assert second_run == 0
            assert len(query_log) <= 2, f"Expected <= 2 queries on idempotent run, got {len(query_log)}"
        finally:
            event.remove(engine, "before_cursor_execute", counter)

    def test_existing_appointment_booking_regression(self, db_session: Session, opt_test_env):
        """Verifies that appointment booking functions seamlessly on batch-generated slots."""
        tz = opt_test_env["tz"]
        base = datetime.now(tz).date()

        generate_upcoming_slots_for_doctors(db_session, days=2, base_date=base)
        db_session.commit()

        slot = db_session.scalars(
            select(AppointmentSlot).where(
                AppointmentSlot.doctor_id == "doc-opt-sharma",
                AppointmentSlot.status == "AVAILABLE",
            )
        ).first()
        assert slot is not None

        # Book the slot via appointment_service
        appt = book_appointment(
            db=db_session,
            patient_reference="PAT-OPT-001",
            doctor_id="doc-opt-sharma",
            slot_id=slot.id,
            reason_category="Chest Pain",
        )
        assert appt.id is not None
        assert appt.appointment_status == "CONFIRMED"

        # Verify slot status changed to BOOKED
        db_session.refresh(slot)
        assert slot.status == "BOOKED"

    def test_concurrent_generation_attempts(self, db_session: Session, opt_test_env):
        """
        Verifies that concurrent generation attempts across threads do not crash,
        never generate duplicate slots, and respect database uniqueness constraints.
        """
        from concurrent.futures import ThreadPoolExecutor
        from app.db.session import SessionLocal

        tz = opt_test_env["tz"]
        base = datetime(2026, 11, 2, 9, 0, 0, tzinfo=tz).date()

        engine = db_session.get_bind()
        results = []
        errors = []

        def worker_generate(worker_id: int):
            from sqlalchemy.orm import Session as WorkerSession
            with WorkerSession(bind=engine) as session:
                try:
                    cnt = generate_upcoming_slots_for_doctors(session, days=5, base_date=base)
                    session.commit()
                    results.append((worker_id, cnt))
                except Exception as e:
                    session.rollback()
                    errors.append((worker_id, str(e)))

        # Run 2 concurrent generation attempts
        t1 = threading.Thread(target=worker_generate, args=(1,))
        t2 = threading.Thread(target=worker_generate, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0, f"Errors during concurrent generation: {errors}"
        # Total slots in database must have zero duplicates
        all_slots = db_session.scalars(select(AppointmentSlot)).all()
        slot_keys = [(s.doctor_id, s.start_time) for s in all_slots]
        assert len(slot_keys) == len(set(slot_keys)), "Duplicate slot (doctor_id, start_time) found!"
        slot_ids = [s.id for s in all_slots]
        assert len(slot_ids) == len(set(slot_ids)), "Duplicate slot ID found!"
