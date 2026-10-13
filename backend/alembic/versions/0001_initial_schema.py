"""Initial schema for MediVoice AI - Aarogya One Hospital

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Hospitals
    op.create_table(
        "hospitals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hospitals_name", "hospitals", ["name"])

    # 2. Departments
    op.create_table(
        "departments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("hospital_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_departments_hospital_id", "departments", ["hospital_id"])
    op.create_index("ix_departments_name", "departments", ["name"])

    # 3. Doctors
    op.create_table(
        "doctors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("hospital_id", sa.String(length=36), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("specialty", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_doctors_hospital_id", "doctors", ["hospital_id"])
    op.create_index("ix_doctors_department_id", "doctors", ["department_id"])
    op.create_index("ix_doctors_display_name", "doctors", ["display_name"])
    op.create_index("ix_doctors_specialty", "doctors", ["specialty"])

    # 4. Appointment Slots
    op.create_table(
        "appointment_slots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("doctor_id", sa.String(length=36), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="AVAILABLE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doctor_id", "start_time", name="uq_doctor_slot_start_time"),
    )
    op.create_index("ix_appointment_slots_doctor_id", "appointment_slots", ["doctor_id"])
    op.create_index("ix_appointment_slots_start_time", "appointment_slots", ["start_time"])
    op.create_index("ix_appointment_slots_status", "appointment_slots", ["status"])

    # 5. Appointments
    op.create_table(
        "appointments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_reference", sa.String(length=100), nullable=False),
        sa.Column("doctor_id", sa.String(length=36), nullable=False),
        sa.Column("slot_id", sa.String(length=36), nullable=False),
        sa.Column("appointment_status", sa.String(length=30), nullable=False, server_default="CONFIRMED"),
        sa.Column("reason_category", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("visit_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up_recommended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("follow_up_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slot_id"], ["appointment_slots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slot_id", name="uq_appointment_slot_id"),
    )
    op.create_index("ix_appointments_patient_reference", "appointments", ["patient_reference"])
    op.create_index("ix_appointments_doctor_id", "appointments", ["doctor_id"])
    op.create_index("ix_appointments_appointment_status", "appointments", ["appointment_status"])
    op.create_index("ix_appointments_reason_category", "appointments", ["reason_category"])

    # 6. Lab Orders
    op.create_table(
        "lab_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_reference", sa.String(length=100), nullable=False),
        sa.Column("ordering_department_id", sa.String(length=36), nullable=True),
        sa.Column("test_category", sa.String(length=100), nullable=False),
        sa.Column("workflow_status", sa.String(length=30), nullable=False, server_default="Pending"),
        sa.Column("expected_completion_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_team", sa.String(length=100), nullable=False),
        sa.Column("delay_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ordering_department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_orders_patient_reference", "lab_orders", ["patient_reference"])
    op.create_index("ix_lab_orders_ordering_dept_id", "lab_orders", ["ordering_department_id"])
    op.create_index("ix_lab_orders_workflow_status", "lab_orders", ["workflow_status"])
    op.create_index("ix_lab_orders_expected_completion", "lab_orders", ["expected_completion_at"])

    # 7. Workflow Exceptions
    op.create_table(
        "workflow_exceptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("exception_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column("responsible_department", sa.String(length=100), nullable=False),
        sa.Column("assigned_to", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="OPEN"),
        sa.Column("affected_record_type", sa.String(length=50), nullable=False),
        sa.Column("affected_record_id", sa.String(length=100), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wf_exceptions_status", "workflow_exceptions", ["status"])
    op.create_index("ix_wf_exceptions_priority", "workflow_exceptions", ["priority"])
    op.create_index("ix_wf_exceptions_affected_id", "workflow_exceptions", ["affected_record_id"])

    # 8. Audit Events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_reference", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("workflow_exceptions")
    op.drop_table("lab_orders")
    op.drop_table("appointments")
    op.drop_table("appointment_slots")
    op.drop_table("doctors")
    op.drop_table("departments")
    op.drop_table("hospitals")
