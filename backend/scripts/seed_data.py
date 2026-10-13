"""
Seed script for Aarogya One Hospital.
Populates:
- 1 Fictional Hospital (Aarogya One Hospital)
- 5 Departments (Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine)
- 6 Fictional Doctors across departments
- Multiple future appointment slots per doctor
- Synthetic appointments across different statuses (CONFIRMED, COMPLETED, CANCELLED)
- Synthetic lab orders, including an intentionally OVERDUE processing order
- Workflow exceptions and audit events

Idempotent: Checks for existing records before inserting.
"""

import sys
import os
from datetime import datetime, timedelta, timezone

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.session import SessionLocal, engine
from app.db.base import Base
from app.models.hospital import Hospital
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.appointment_slot import AppointmentSlot
from app.models.appointment import Appointment
from app.models.lab_order import LabOrder
from app.models.workflow_exception import WorkflowException
from app.models.audit_event import AuditEvent


def seed_database(db: Session, reset: bool = False):
    if reset:
        print("Resetting existing tables...")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    else:
        Base.metadata.create_all(bind=engine)

    print("Seeding Aarogya One Hospital data...")

    # 1. Hospital
    hosp_id = "11111111-1111-1111-1111-111111111111"
    hospital = db.scalars(select(Hospital).where(Hospital.id == hosp_id)).first()
    if not hospital:
        hospital = Hospital(
            id=hosp_id,
            name="Aarogya One Hospital",
            description="Leading multi-specialty tertiary healthcare center in Bengaluru, Karnataka.",
            address="Plot 42, Outer Ring Road, Bellandur, Bengaluru, Karnataka 560103",
            is_active=True,
        )
        db.add(hospital)
        db.flush()
        print("  [+] Added Hospital: Aarogya One Hospital")

    # 2. Departments
    dept_defs = [
        {"id": "22222222-0001-0000-0000-000000000001", "name": "Cardiology", "desc": "Adult & pediatric cardiovascular care, ECG, ECHO, and interventional cardiology."},
        {"id": "22222222-0002-0000-0000-000000000002", "name": "Neurology", "desc": "Comprehensive neurological disorders, stroke management, and neuro-diagnostics."},
        {"id": "22222222-0003-0000-0000-000000000003", "name": "Orthopedics", "desc": "Joint replacement, trauma care, spine, and sports medicine."},
        {"id": "22222222-0004-0000-0000-000000000004", "name": "Pediatrics", "desc": "Comprehensive child health, immunization, and pediatric subspecialties."},
        {"id": "22222222-0005-0000-0000-000000000005", "name": "General Medicine", "desc": "Internal medicine, preventive checkups, and chronic disease management."},
    ]
    dept_map = {}
    for d_def in dept_defs:
        existing_dept = db.scalars(select(Department).where(Department.id == d_def["id"])).first()
        if not existing_dept:
            existing_dept = Department(
                id=d_def["id"],
                hospital_id=hosp_id,
                name=d_def["name"],
                description=d_def["desc"],
                is_active=True,
            )
            db.add(existing_dept)
            db.flush()
            print(f"  [+] Added Department: {d_def['name']}")
        dept_map[d_def["name"]] = existing_dept

    # 3. Doctors (6 fictional doctors across departments)
    doctor_defs = [
        {
            "id": "33333333-0001-0000-0000-000000000001",
            "name": "Dr. Rajesh Sharma",
            "specialty": "Cardiology",
            "dept": "Cardiology",
        },
        {
            "id": "33333333-0002-0000-0000-000000000002",
            "name": "Dr. Priya Nair",
            "specialty": "Neurology",
            "dept": "Neurology",
        },
        {
            "id": "33333333-0003-0000-0000-000000000003",
            "name": "Dr. Arvind Swamy",
            "specialty": "Orthopedics",
            "dept": "Orthopedics",
        },
        {
            "id": "33333333-0004-0000-0000-000000000004",
            "name": "Dr. Ananya Sen",
            "specialty": "Pediatrics",
            "dept": "Pediatrics",
        },
        {
            "id": "33333333-0005-0000-0000-000000000005",
            "name": "Dr. Vikram Mehta",
            "specialty": "General Medicine",
            "dept": "General Medicine",
        },
        {
            "id": "33333333-0006-0000-0000-000000000006",
            "name": "Dr. Sunita Rao",
            "specialty": "Cardiology",
            "dept": "Cardiology",
        },
    ]

    doc_map = {}
    for doc_def in doctor_defs:
        existing_doc = db.scalars(select(Doctor).where(Doctor.id == doc_def["id"])).first()
        if not existing_doc:
            dept = dept_map[doc_def["dept"]]
            existing_doc = Doctor(
                id=doc_def["id"],
                hospital_id=hosp_id,
                department_id=dept.id,
                display_name=doc_def["name"],
                specialty=doc_def["specialty"],
                is_active=True,
            )
            db.add(existing_doc)
            db.flush()
            print(f"  [+] Added Doctor: {doc_def['name']} ({doc_def['specialty']})")
        doc_map[doc_def["name"]] = existing_doc

    # 4. Future Appointment Slots (Multiple future slots per doctor over next 3 days)
    now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    slot_count = 0
    slot_map = {}

    for doc_def in doctor_defs:
        doc_id = doc_def["id"]
        # Generate 6 future slots for each doctor (days 1, 2, 3: morning 10am, afternoon 2pm)
        for day_offset in [1, 2, 3]:
            for hour in [10, 14]:
                slot_start = (now_utc + timedelta(days=day_offset)).replace(hour=hour)
                slot_end = slot_start + timedelta(minutes=30)
                slot_key = f"{doc_id}_{slot_start.strftime('%Y%m%d%H%M')}"
                
                existing_slot = db.scalars(
                    select(AppointmentSlot).where(
                        AppointmentSlot.doctor_id == doc_id,
                        AppointmentSlot.start_time == slot_start,
                    )
                ).first()

                if not existing_slot:
                    existing_slot = AppointmentSlot(
                        doctor_id=doc_id,
                        start_time=slot_start,
                        end_time=slot_end,
                        status="AVAILABLE",
                    )
                    db.add(existing_slot)
                    db.flush()
                    slot_count += 1
                slot_map[slot_key] = existing_slot

    print(f"  [+] Configured future appointment slots ({slot_count} new slots generated)")

    # 5. Synthetic Appointments in different statuses
    # Let's create:
    # 1 CONFIRMED appointment for Dr. Rajesh Sharma
    # 1 COMPLETED appointment with follow-up recorded for Dr. Priya Nair
    # 1 CANCELLED appointment for Dr. Arvind Swamy
    
    # Slot 1: Dr. Rajesh Sharma (Day 1 at 10:00) -> CONFIRMED
    dr_sharma_id = doctor_defs[0]["id"]
    day1_10am_key = f"{dr_sharma_id}_{(now_utc + timedelta(days=1)).replace(hour=10).strftime('%Y%m%d%H%M')}"
    slot1 = slot_map.get(day1_10am_key)
    
    appt1_id = "44444444-0001-0000-0000-000000000001"
    existing_appt1 = db.scalars(select(Appointment).where(Appointment.id == appt1_id)).first()
    if not existing_appt1 and slot1:
        slot1.status = "BOOKED"
        existing_appt1 = Appointment(
            id=appt1_id,
            patient_reference="PAT-2024-9182",
            doctor_id=dr_sharma_id,
            slot_id=slot1.id,
            appointment_status="CONFIRMED",
            reason_category="Chest Pain & Palpitations Evaluation",
            follow_up_recommended=False,
        )
        db.add(existing_appt1)
        print("  [+] Added Synthetic Appointment: CONFIRMED (PAT-2024-9182 with Dr. Rajesh Sharma)")

    # Slot 2: Dr. Priya Nair -> COMPLETED with follow-up recommendation
    dr_nair_id = doctor_defs[1]["id"]
    day1_14pm_key = f"{dr_nair_id}_{(now_utc + timedelta(days=1)).replace(hour=14).strftime('%Y%m%d%H%M')}"
    slot2 = slot_map.get(day1_14pm_key)
    appt2_id = "44444444-0002-0000-0000-000000000002"
    existing_appt2 = db.scalars(select(Appointment).where(Appointment.id == appt2_id)).first()
    if not existing_appt2 and slot2:
        slot2.status = "BOOKED"
        existing_appt2 = Appointment(
            id=appt2_id,
            patient_reference="PAT-2024-3310",
            doctor_id=dr_nair_id,
            slot_id=slot2.id,
            appointment_status="COMPLETED",
            reason_category="Chronic Migraine & Aura Review",
            visit_completed_at=now_utc - timedelta(hours=2),
            follow_up_recommended=True,
            follow_up_date=now_utc + timedelta(days=30),
            follow_up_notes="Review headache frequency diary in 4 weeks. Repeat MRI if visual aura increases.",
        )
        db.add(existing_appt2)
        print("  [+] Added Synthetic Appointment: COMPLETED (PAT-2024-3310 with Dr. Priya Nair)")

    # Slot 3: Dr. Arvind Swamy -> CANCELLED (Slot remains AVAILABLE)
    dr_swamy_id = doctor_defs[2]["id"]
    day2_10am_key = f"{dr_swamy_id}_{(now_utc + timedelta(days=2)).replace(hour=10).strftime('%Y%m%d%H%M')}"
    slot3 = slot_map.get(day2_10am_key)
    appt3_id = "44444444-0003-0000-0000-000000000003"
    existing_appt3 = db.scalars(select(Appointment).where(Appointment.id == appt3_id)).first()
    if not existing_appt3 and slot3:
        # Note: In our model, a cancelled appointment releases its slot back to AVAILABLE
        slot3.status = "AVAILABLE"
        existing_appt3 = Appointment(
            id=appt3_id,
            patient_reference="PAT-2024-5501",
            doctor_id=dr_swamy_id,
            slot_id=slot3.id,
            appointment_status="CANCELLED",
            reason_category="Knee Arthroscopy Follow-up",
            follow_up_recommended=False,
        )
        db.add(existing_appt3)
        print("  [+] Added Synthetic Appointment: CANCELLED (PAT-2024-5501 with Dr. Arvind Swamy)")

    # 6. Synthetic Lab Orders (including an OVERDUE Processing order)
    lab_orders_defs = [
        {
            "id": "55555555-0001-0000-0000-000000000001",
            "patient_reference": "PAT-2024-9182",
            "dept_id": dept_map["Cardiology"].id,
            "test_category": "Cardiac Troponin I & Lipid Profile",
            "workflow_status": "Processing",
            # Intentionally overdue by 3 hours to verify Workflow Intelligence detection!
            "expected_completion_at": now_utc - timedelta(hours=3),
            "assigned_team": "Stat Biochemistry Core",
            "delay_reason": "Analyzer reagent recalibration in progress",
        },
        {
            "id": "55555555-0002-0000-0000-000000000002",
            "patient_reference": "PAT-2024-3310",
            "dept_id": dept_map["Neurology"].id,
            "test_category": "Serum Electrolytes & Vitamin B12",
            "workflow_status": "Completed",
            "expected_completion_at": now_utc - timedelta(hours=6),
            "assigned_team": "General Chemistry",
            "delay_reason": None,
        },
        {
            "id": "55555555-0003-0000-0000-000000000003",
            "patient_reference": "PAT-2024-7744",
            "dept_id": dept_map["General Medicine"].id,
            "test_category": "Glycated Hemoglobin (HbA1c)",
            "workflow_status": "Pending",
            "expected_completion_at": now_utc + timedelta(hours=4),
            "assigned_team": "Routine Hematology",
            "delay_reason": None,
        },
    ]

    for l_def in lab_orders_defs:
        existing_lab = db.scalars(select(LabOrder).where(LabOrder.id == l_def["id"])).first()
        if not existing_lab:
            existing_lab = LabOrder(
                id=l_def["id"],
                patient_reference=l_def["patient_reference"],
                ordering_department_id=l_def["dept_id"],
                test_category=l_def["test_category"],
                workflow_status=l_def["workflow_status"],
                expected_completion_at=l_def["expected_completion_at"],
                assigned_team=l_def["assigned_team"],
                delay_reason=l_def["delay_reason"],
            )
            db.add(existing_lab)
            print(f"  [+] Added Lab Order: {l_def['test_category']} (Status: {l_def['workflow_status']})")

    # 7. Workflow Exception & Audit Events
    exc_id = "66666666-0001-0000-0000-000000000001"
    existing_exc = db.scalars(select(WorkflowException).where(WorkflowException.id == exc_id)).first()
    if not existing_exc:
        existing_exc = WorkflowException(
            id=exc_id,
            exception_type="LAB_ORDER_OVERDUE",
            title="Turnaround Exceeded: Cardiac Troponin I (PAT-2024-9182)",
            description="Troponin turnaround exceeded standard 60-minute window for acute cardiac rule-out.",
            priority="CRITICAL",
            responsible_department="Cardiology",
            assigned_to="Stat Biochemistry Core",
            status="OPEN",
            affected_record_type="LabOrder",
            affected_record_id="55555555-0001-0000-0000-000000000001",
            detected_at=now_utc - timedelta(hours=2),
        )
        db.add(existing_exc)
        print("  [+] Added Synthetic Workflow Exception: LAB_ORDER_OVERDUE")

    # Audit Events
    audit_id = "77777777-0001-0000-0000-000000000001"
    existing_audit = db.scalars(select(AuditEvent).where(AuditEvent.id == audit_id)).first()
    if not existing_audit:
        existing_audit = AuditEvent(
            id=audit_id,
            actor_reference="SYSTEM_BOOTSTRAP",
            action="SYSTEM_INITIALIZED",
            entity_type="Hospital",
            entity_id=hosp_id,
            details='{"event": "Aarogya One Hospital Phase 1 Seed Applied"}',
        )
        db.add(existing_audit)

    db.commit()
    print("Seed data successfully committed!")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        reset_flag = "--reset" in sys.argv
        seed_database(db, reset=reset_flag)
    finally:
        db.close()
