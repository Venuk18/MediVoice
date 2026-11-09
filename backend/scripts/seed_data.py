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
from app.models.insurance import InsuranceProvider, InsurancePlan
from app.models.workflow_exception import WorkflowException
from app.models.audit_event import AuditEvent
from app.models.maintenance import MaintenanceWorkOrder
from app.services.doctor_service import generate_upcoming_slots_for_doctors



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

    now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    # 4. Future Appointment Slots across the next 20 calendar days for all active doctors
    slot_count = generate_upcoming_slots_for_doctors(db, days=20)
    print(f"  [+] Configured 20-day appointment availability ({slot_count} new slots generated)")

    # 5. Synthetic Appointments in different statuses
    # Slot 1: Dr. Rajesh Sharma -> CONFIRMED
    dr_sharma_id = doctor_defs[0]["id"]
    appt1_id = "44444444-0001-0000-0000-000000000001"
    existing_appt1 = db.scalars(select(Appointment).where(Appointment.id == appt1_id)).first()
    if not existing_appt1:
        sharma_slots = db.scalars(
            select(AppointmentSlot).where(
                AppointmentSlot.doctor_id == dr_sharma_id,
                AppointmentSlot.status == "AVAILABLE",
            ).order_by(AppointmentSlot.start_time.asc())
        ).all()
        # Reserve the second available slot for Dr. Sharma so earlier slot remains available for next-slot tests
        slot1 = sharma_slots[1] if len(sharma_slots) > 1 else (sharma_slots[0] if sharma_slots else None)
        if slot1:
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
    appt2_id = "44444444-0002-0000-0000-000000000002"
    existing_appt2 = db.scalars(select(Appointment).where(Appointment.id == appt2_id)).first()
    if not existing_appt2:
        nair_slots = db.scalars(
            select(AppointmentSlot).where(
                AppointmentSlot.doctor_id == dr_nair_id,
                AppointmentSlot.status == "AVAILABLE",
            ).order_by(AppointmentSlot.start_time.asc())
        ).all()
        slot2 = nair_slots[0] if nair_slots else None
        if slot2:
            slot2.status = "BOOKED"
            existing_appt2 = Appointment(
                id=appt2_id,
                patient_reference="PAT-2024-3310",
                doctor_id=dr_nair_id,
                slot_id=slot2.id,
                appointment_status="COMPLETED",
                reason_category="Chronic Migraine & Aura Review",
                visit_completed_at=datetime.now(timezone.utc) - timedelta(hours=2),
                follow_up_recommended=True,
                follow_up_date=datetime.now(timezone.utc) + timedelta(days=30),
                follow_up_notes="Review headache frequency diary in 4 weeks. Repeat MRI if visual aura increases.",
            )
            db.add(existing_appt2)
            print("  [+] Added Synthetic Appointment: COMPLETED (PAT-2024-3310 with Dr. Priya Nair)")

    # Slot 3: Dr. Arvind Swamy -> CANCELLED (Slot remains AVAILABLE)
    dr_swamy_id = doctor_defs[2]["id"]
    appt3_id = "44444444-0003-0000-0000-000000000003"
    existing_appt3 = db.scalars(select(Appointment).where(Appointment.id == appt3_id)).first()
    if not existing_appt3:
        swamy_slots = db.scalars(
            select(AppointmentSlot).where(
                AppointmentSlot.doctor_id == dr_swamy_id,
                AppointmentSlot.status == "AVAILABLE",
            ).order_by(AppointmentSlot.start_time.asc())
        ).all()
        slot3 = swamy_slots[1] if len(swamy_slots) > 1 else (swamy_slots[0] if swamy_slots else None)
        if slot3:
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

    # 6. Synthetic Lab Orders with 6-digit verification codes (including leading-zero code "048271")
    lab_orders_defs = [
        {
            "id": "55555555-0001-0000-0000-000000000001",
            "patient_reference": "PAT-2024-9182",
            "dept_id": dept_map["Cardiology"].id,
            "test_name": "Cardiac Troponin I & Lipid Profile",
            "test_category": "Cardiac Troponin I & Lipid Profile",
            "workflow_status": "Processing",
            # Intentionally overdue by 3 hours to verify Workflow Intelligence detection!
            "expected_completion_at": now_utc - timedelta(hours=3),
            "assigned_team": "Stat Biochemistry Core",
            "delay_reason": "Analyzer reagent recalibration in progress",
            "verification_code": "048271",
            "verification_code_expires_at": now_utc + timedelta(hours=72),
            "verification_code_is_active": True,
        },
        {
            "id": "55555555-0002-0000-0000-000000000002",
            "patient_reference": "PAT-2024-3310",
            "dept_id": dept_map["Neurology"].id,
            "test_name": "Serum Electrolytes & Vitamin B12",
            "test_category": "Serum Electrolytes & Vitamin B12",
            "workflow_status": "Completed",
            "expected_completion_at": now_utc - timedelta(hours=6),
            "assigned_team": "General Chemistry",
            "delay_reason": None,
            "verification_code": "384920",
            "verification_code_expires_at": now_utc + timedelta(hours=72),
            "verification_code_is_active": True,
        },
        {
            "id": "55555555-0003-0000-0000-000000000003",
            "patient_reference": "PAT-2024-7744",
            "dept_id": dept_map["General Medicine"].id,
            "test_name": "Glycated Hemoglobin (HbA1c)",
            "test_category": "Glycated Hemoglobin (HbA1c)",
            "workflow_status": "REGISTERED",
            "expected_completion_at": now_utc + timedelta(hours=4),
            "assigned_team": "Routine Hematology",
            "delay_reason": None,
            "verification_code": "729104",
            "verification_code_expires_at": now_utc + timedelta(hours=72),
            "verification_code_is_active": True,
        },
        {
            "id": "55555555-0004-0000-0000-000000000004",
            "patient_reference": "PAT-2026-4409",
            "dept_id": dept_map["General Medicine"].id,
            "test_name": "Complete Blood Count (CBC) & ESR",
            "test_category": "Complete Blood Count (CBC) & ESR",
            "workflow_status": "SAMPLE_COLLECTED",
            "expected_completion_at": now_utc + timedelta(hours=5),
            "assigned_team": "Hematology Core",
            "delay_reason": None,
            "verification_code": "019482",
            "verification_code_expires_at": now_utc + timedelta(hours=72),
            "verification_code_is_active": True,
        },
        {
            "id": "55555555-0005-0000-0000-000000000005",
            "patient_reference": "PAT-2024-5501",
            "dept_id": dept_map["Orthopedics"].id,
            "test_name": "Synovial Fluid Culture & Sensitivity",
            "test_category": "Synovial Fluid Culture & Sensitivity",
            "workflow_status": "CANCELLED",
            "expected_completion_at": now_utc - timedelta(hours=12),
            "assigned_team": "Microbiology Lab",
            "delay_reason": "Order cancelled prior to sample collection",
            "verification_code": "905318",
            "verification_code_expires_at": now_utc + timedelta(hours=72),
            "verification_code_is_active": True,
        },
    ]

    for l_def in lab_orders_defs:
        existing_lab = db.scalars(select(LabOrder).where(LabOrder.id == l_def["id"])).first()
        if not existing_lab:
            existing_lab = LabOrder(
                id=l_def["id"],
                patient_reference=l_def["patient_reference"],
                ordering_department_id=l_def["dept_id"],
                test_name=l_def["test_name"],
                test_category=l_def["test_category"],
                workflow_status=l_def["workflow_status"],
                expected_completion_at=l_def["expected_completion_at"],
                assigned_team=l_def["assigned_team"],
                delay_reason=l_def["delay_reason"],
                verification_code=l_def["verification_code"],
                verification_code_expires_at=l_def["verification_code_expires_at"],
                verification_code_is_active=l_def["verification_code_is_active"],
            )
            db.add(existing_lab)
            print(f"  [+] Added Lab Order: {l_def['test_category']} (Status: {l_def['workflow_status']})")
        else:
            # Ensure verification fields are populated on existing records idempotently
            if not existing_lab.verification_code:
                existing_lab.verification_code = l_def["verification_code"]
                existing_lab.verification_code_expires_at = l_def["verification_code_expires_at"]
                existing_lab.verification_code_is_active = l_def["verification_code_is_active"]
            if not existing_lab.test_name:
                existing_lab.test_name = l_def["test_name"]

    # 7. Synthetic Hospital Insurance Providers & Plans
    insurance_provider_defs = [
        {
            "id": "88888888-0001-0000-0000-000000000001",
            "name": "Aarogya Shield Health Insurance",
            "code": "ASHI-01",
            "support_Contact": "1800-100-4201 (Desk Ext. 402)",
            "is_active": True,
            "plans": [
                {
                    "id": "99999999-0001-0000-0000-000000000001",
                    "plan_name": "Aarogya Shield Gold Cashless Plus",
                    "plan_type": "Individual & Family Floater",
                    "coverage_summary": "Comprehensive inpatient hospitalization, ICU, day-care surgeries, and pre/post-hospitalization diagnostics.",
                    "covered_services": "Inpatient Hospitalization, ICU, Cardiology Procedures, Neurology Care, Orthopedic Surgery, Emergency Stabilization, Pre/Post Hospitalization Diagnostics",
                    "copay_Summary": "0% co-pay for network tertiary care in standard private room; 10% co-pay for luxury suite upgrades.",
                    "preauthorization_Required": True,
                    "cashless_Available": True,
                    "reimbursement_Available": True,
                    "network_Notes": "24/7 cashless pre-authorization available at Aarogya One Insurance Desk (Ground Floor, Block A).",
                    "is_active": True,
                },
                {
                    "id": "99999999-0002-0000-0000-000000000002",
                    "plan_name": "Aarogya Shield OPD & Diagnostics Care",
                    "plan_type": "OPD & Preventive Rider",
                    "coverage_summary": "Covers specialist outpatient consultations, prescribed laboratory tests, and radiology up to annual rider limit.",
                    "covered_services": "OPD Consultations, Pathology & Lab Tests, X-Ray, ECG, Ultrasound, Preventive Health Checkup",
                    "copay_Summary": "15% co-pay on outpatient consultations and diagnostic laboratory orders.",
                    "preauthorization_Required": False,
                    "cashless_Available": True,
                    "reimbursement_Available": True,
                    "network_Notes": "Present digital policy card at OPD Billing Counter 3 for direct outpatient billing.",
                    "is_active": True,
                },
            ],
        },
        {
            "id": "88888888-0002-0000-0000-000000000002",
            "name": "Bharat Care Assurance",
            "code": "BCA-02",
            "support_Contact": "1800-200-8810 (Desk Ext. 403)",
            "is_active": True,
            "plans": [
                {
                    "id": "99999999-0003-0000-0000-000000000003",
                    "plan_name": "Bharat Care Family Floater Prime",
                    "plan_type": "Family Floater",
                    "coverage_summary": "Covers inpatient medical and surgical admissions, maternity care, and pediatric hospitalization.",
                    "covered_services": "Inpatient Hospitalization, Pediatrics, Maternity & Neonatal Care, General Medicine, Orthopedic Trauma, Day-Care Procedures",
                    "copay_Summary": "10% mandatory co-pay across all inpatient claims; 20% co-pay for age 60+.",
                    "preauthorization_Required": True,
                    "cashless_Available": True,
                    "reimbursement_Available": True,
                    "network_Notes": "Planned surgeries require pre-authorization submission at least 48 hours prior to admission.",
                    "is_active": True,
                },
                {
                    "id": "99999999-0004-0000-0000-000000000004",
                    "plan_name": "Bharat Care Basic Reimbursement Saver",
                    "plan_type": "Individual Indemnity",
                    "coverage_summary": "Standard inpatient hospitalization coverage on a reimbursement basis with itemized discharge summary.",
                    "covered_services": "Inpatient Hospitalization, General Medicine, Emergency Care, Basic Surgical Procedures",
                    "copay_Summary": "20% co-pay on admissible inpatient bill amount.",
                    "preauthorization_Required": False,
                    "cashless_Available": False,
                    "reimbursement_Available": True,
                    "network_Notes": "Cashless facility is not enabled on Basic Saver tier; hospital provides certified claim documents for reimbursement.",
                    "is_active": True,
                },
            ],
        },
        {
            "id": "88888888-0003-0000-0000-000000000003",
            "name": "Deccan Star Mediclaim",
            "code": "DSM-03",
            "support_Contact": "1800-300-5599 (Desk Ext. 404)",
            "is_active": True,
            "plans": [
                {
                    "id": "99999999-0005-0000-0000-000000000005",
                    "plan_name": "Deccan Star Senior Citizen Shield",
                    "plan_type": "Senior Citizen Care",
                    "coverage_summary": "Dedicated coverage for senior citizens including cardiac care, stroke rehabilitation, and joint replacement.",
                    "covered_services": "Cardiology, Neurology & Stroke Care, Knee & Hip Joint Replacement, Dialysis, Cataract, Inpatient Nursing",
                    "copay_Summary": "15% co-pay in twin-sharing room; 25% co-pay in single AC room.",
                    "preauthorization_Required": True,
                    "cashless_Available": True,
                    "reimbursement_Available": True,
                    "network_Notes": "Pre-existing disease waiting period rules apply per policy schedule; verify at TPA Desk.",
                    "is_active": True,
                },
            ],
        },
        {
            "id": "88888888-0004-0000-0000-000000000004",
            "name": "Kaveri National Health TPA",
            "code": "KNHT-04",
            "support_Contact": "1800-400-7722 (Desk Ext. 405)",
            "is_active": True,
            "plans": [
                {
                    "id": "99999999-0006-0000-0000-000000000006",
                    "plan_name": "Kaveri Corporate Group Cashless Premier",
                    "plan_type": "Corporate Group Health",
                    "coverage_summary": "Zero-deductible corporate group coverage for inpatient admissions, emergency trauma, and diagnostic panels.",
                    "covered_services": "Inpatient Hospitalization, Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine, Emergency & ICU, Diagnostics",
                    "copay_Summary": "0% co-pay for employees; 10% co-pay for dependent parents.",
                    "preauthorization_Required": True,
                    "cashless_Available": True,
                    "reimbursement_Available": True,
                    "network_Notes": "Requires corporate employee ID and TPA e-card at Aarogya One Corporate Helpdesk.",
                    "is_active": True,
                },
            ],
        },
        {
            "id": "88888888-0005-0000-0000-000000000005",
            "name": "Legacy Metro Assurance (Discontinued)",
            "code": "LMA-99",
            "support_Contact": "N/A",
            "is_active": False,
            "plans": [],
        },
    ]

    for p_def in insurance_provider_defs:
        existing_prov = db.scalars(select(InsuranceProvider).where(InsuranceProvider.id == p_def["id"])).first()
        if not existing_prov:
            existing_prov = InsuranceProvider(
                id=p_def["id"],
                hospital_id=hosp_id,
                name=p_def["name"],
                code=p_def["code"],
                support_contact=p_def["support_Contact"],
                is_active=p_def["is_active"],
            )
            db.add(existing_prov)
            db.flush()
            print(f"  [+] Added Insurance Provider: {p_def['name']} (Active: {p_def['is_active']})")

        for plan_def in p_def["plans"]:
            existing_plan = db.scalars(select(InsurancePlan).where(InsurancePlan.id == plan_def["id"])).first()
            if not existing_plan:
                existing_plan = InsurancePlan(
                    id=plan_def["id"],
                    provider_id=p_def["id"],
                    plan_name=plan_def["plan_name"],
                    plan_type=plan_def["plan_type"],
                    coverage_summary=plan_def["coverage_summary"],
                    covered_services=plan_def["covered_services"],
                    copay_summary=plan_def["copay_Summary"],
                    preauthorization_required=plan_def["preauthorization_Required"],
                    cashless_available=plan_def["cashless_Available"],
                    reimbursement_available=plan_def["reimbursement_Available"],
                    network_notes=plan_def["network_Notes"],
                    is_active=plan_def["is_active"],
                )
                db.add(existing_plan)
                print(f"      [+] Added Insurance Plan: {plan_def['plan_name']}")

    # 8. Workflow Exception & Audit Events
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

    # 9. Synthetic Hospital Maintenance Work Orders
    maintenance_defs = [
        {
            "id": "aaaaaaaa-0001-0000-0000-000000000001",
            "work_order_code": "MWO-2026-1041",
            "title": "Negative-Pressure HEPA Damper Drift — ICU Isolation Bay 3",
            "description": "Differential pressure sensor reading -1.4 Pa (target -2.5 Pa minimum). Immediate damper actuator calibration required.",
            "category": "HVAC & Environmental",
            "location": "Block A • 3rd Floor • Cardiac & Medical ICU Bay 3",
            "equipment_reference": "HVAC-AHU-304B",
            "priority": "CRITICAL",
            "status": "IN_PROGRESS",
            "reported_by": "ICU Charge Nurse Desk",
            "assigned_to": "Karthik Subramanian (Biomedical & HVAC Lead)",
            "resolution_notes": "Actuator linkage inspected; replacing differential pressure transducer module.",
            "resolved_at": None,
        },
        {
            "id": "aaaaaaaa-0002-0000-0000-000000000002",
            "work_order_code": "MWO-2026-1042",
            "title": "Automated Chemiluminescence Analyzer Optical Sensor Cleaning",
            "description": "Routine optical path warning triggered during stat cardiac enzyme batch run.",
            "category": "Biomedical Equipment",
            "location": "Block B • Ground Floor • Central Diagnostics Lab",
            "equipment_reference": "BIO-CHEM-8820",
            "priority": "HIGH",
            "status": "ASSIGNED",
            "reported_by": "Vikram Deshmukh (Central Diagnostics)",
            "assigned_to": "Rohan Kulkarni (Biomedical Engineering)",
            "resolution_notes": None,
            "resolved_at": None,
        },
        {
            "id": "aaaaaaaa-0003-0000-0000-000000000003",
            "work_order_code": "MWO-2026-1043",
            "title": "UPS Backup Battery Bank B2 Voltage Imbalance Alert",
            "description": "Quarterly load test flagged cell #14 voltage drop on secondary UPS line serving Outpatient Wing.",
            "category": "Electrical & Power",
            "location": "Basement Level 1 • Electrical Substation Room B2",
            "equipment_reference": "ELEC-UPS-B2-14",
            "priority": "MEDIUM",
            "status": "OPEN",
            "reported_by": "Facility Telemetry Monitor",
            "assigned_to": None,
            "resolution_notes": None,
            "resolved_at": None,
        },
        {
            "id": "aaaaaaaa-0004-0000-0000-000000000004",
            "work_order_code": "MWO-2026-1039",
            "title": "Reverse Osmosis Water Purification Pre-Filter Replacement",
            "description": "Scheduled 5-micron sediment and carbon block replacement for Diagnostics & Sterilization feed line.",
            "category": "Sanitation & Plumbing",
            "location": "Block B • Utility Mezzanine • Water Plant",
            "equipment_reference": "PLB-RO-210",
            "priority": "LOW",
            "status": "RESOLVED",
            "reported_by": "Central Sterile Supply Department (CSSD)",
            "assigned_to": "Suresh Babu (Plumbing & Water Systems)",
            "resolution_notes": "Replaced 5-micron and activated carbon cartridges; post-filtration TDS verified at 12 ppm.",
            "resolved_at": now_utc - timedelta(hours=5),
        },
    ]

    for m_def in maintenance_defs:
        existing_mwo = db.scalars(
            select(MaintenanceWorkOrder).where(
                (MaintenanceWorkOrder.id == m_def["id"])
                | (MaintenanceWorkOrder.work_order_code == m_def["work_order_code"])
            )
        ).first()
        if not existing_mwo:
            existing_mwo = MaintenanceWorkOrder(
                id=m_def["id"],
                hospital_id=hosp_id,
                work_order_code=m_def["work_order_code"],
                title=m_def["title"],
                description=m_def["description"],
                category=m_def["category"],
                location=m_def["location"],
                equipment_reference=m_def["equipment_reference"],
                priority=m_def["priority"],
                status=m_def["status"],
                reported_by=m_def["reported_by"],
                assigned_to=m_def["assigned_to"],
                resolution_notes=m_def["resolution_notes"],
                resolved_at=m_def["resolved_at"],
            )
            db.add(existing_mwo)
            print(f"  [+] Added Maintenance Work Order: {m_def['work_order_code']} ({m_def['status']})")

    db.commit()
    print("Seed data successfully committed!")



if __name__ == "__main__":
    db = SessionLocal()
    try:
        reset_flag = "--reset" in sys.argv
        seed_database(db, reset=reset_flag)
    finally:
        db.close()

