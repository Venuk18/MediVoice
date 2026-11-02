"""Add lab order verification code fields and hospital insurance models

Revision ID: 0002_lab_verification_and_insurance
Revises: 0001_initial_schema
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_lab_insurance"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend lab_orders with verification code and test_name columns
    with op.batch_alter_table("lab_orders") as batch_op:
        batch_op.add_column(sa.Column("test_name", sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column("verification_code", sa.String(length=6), nullable=True))
        batch_op.add_column(sa.Column("verification_code_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("verification_code_is_active", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(sa.Column("verification_code_used_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_lab_orders_test_name", ["test_name"])
        batch_op.create_index("ix_lab_orders_verification_code", ["verification_code"])
        batch_op.create_index("ix_lab_orders_verification_expires", ["verification_code_expires_at"])
        batch_op.create_index("ix_lab_orders_verification_active", ["verification_code_is_active"])

    # 2. Create insurance_providers table
    op.create_table(
        "insurance_providers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("hospital_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False, server_default="INS-DEMO"),
        sa.Column("support_contact", sa.String(length=150), nullable=False),
        sa.Column("desk_location", sa.String(length=200), nullable=True),
        sa.Column("contact_hours", sa.String(length=150), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_synthetic_demo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_insurance_provider_name"),
    )
    op.create_index("ix_insurance_providers_hospital_id", "insurance_providers", ["hospital_id"])
    op.create_index("ix_insurance_providers_name", "insurance_providers", ["name"])
    op.create_index("ix_insurance_providers_code", "insurance_providers", ["code"])
    op.create_index("ix_insurance_providers_is_active", "insurance_providers", ["is_active"])

    # 3. Create insurance_plans table
    op.create_table(
        "insurance_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=36), nullable=False),
        sa.Column("plan_name", sa.String(length=150), nullable=False),
        sa.Column("plan_type", sa.String(length=100), nullable=False, server_default="Individual & Family Floater"),
        sa.Column("coverage_summary", sa.Text(), nullable=False),
        sa.Column("covered_services", sa.Text(), nullable=False),
        sa.Column("copay_summary", sa.Text(), nullable=False),
        sa.Column("exclusions_and_limitations", sa.Text(), nullable=True),
        sa.Column("preauthorization_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cashless_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reimbursement_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("network_notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["insurance_providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "plan_name", name="uq_provider_plan_name"),
    )
    op.create_index("ix_insurance_plans_provider_id", "insurance_plans", ["provider_id"])
    op.create_index("ix_insurance_plans_plan_name", "insurance_plans", ["plan_name"])
    op.create_index("ix_insurance_plans_is_active", "insurance_plans", ["is_active"])


def downgrade() -> None:
    op.drop_table("insurance_plans")
    op.drop_table("insurance_providers")
    with op.batch_alter_table("lab_orders") as batch_op:
        batch_op.drop_index("ix_lab_orders_verification_active")
        batch_op.drop_index("ix_lab_orders_verification_expires")
        batch_op.drop_index("ix_lab_orders_verification_code")
        batch_op.drop_index("ix_lab_orders_test_name")
        batch_op.drop_column("verification_code_used_at")
        batch_op.drop_column("verification_code_is_active")
        batch_op.drop_column("verification_code_expires_at")
        batch_op.drop_column("verification_code")
        batch_op.drop_column("test_name")
