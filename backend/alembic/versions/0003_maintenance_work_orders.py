"""Add maintenance_work_orders table for Hospital Facilities & Maintenance operations

Revision ID: 0003_maintenance_work_orders
Revises: 0002_lab_verification_and_insurance
Create Date: 2026-10-27 10:30:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0003_maintenance_work_orders"
down_revision: Union[str, None] = "0002_lab_verification_and_insurance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "maintenance_work_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("hospital_id", sa.String(length=36), nullable=False),
        sa.Column("work_order_code", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="Facility & Safety"),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("equipment_reference", sa.String(length=120), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="OPEN"),
        sa.Column("reported_by", sa.String(length=120), nullable=False, server_default="Hospital Operations Desk"),
        sa.Column("assigned_to", sa.String(length=120), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("work_order_code", name="uq_maintenance_work_order_code"),
    )
    op.create_index("ix_maintenance_work_orders_hospital_id", "maintenance_work_orders", ["hospital_id"])
    op.create_index("ix_maintenance_work_orders_work_order_code", "maintenance_work_orders", ["work_order_code"])
    op.create_index("ix_maintenance_work_orders_category", "maintenance_work_orders", ["category"])
    op.create_index("ix_maintenance_work_orders_location", "maintenance_work_orders", ["location"])
    op.create_index("ix_maintenance_work_orders_priority", "maintenance_work_orders", ["priority"])
    op.create_index("ix_maintenance_work_orders_status", "maintenance_work_orders", ["status"])
    op.create_index("ix_maintenance_work_orders_assigned_to", "maintenance_work_orders", ["assigned_to"])


def downgrade() -> None:
    op.drop_index("ix_maintenance_work_orders_assigned_to", table_name="maintenance_work_orders")
    op.drop_index("ix_maintenance_work_orders_status", table_name="maintenance_work_orders")
    op.drop_index("ix_maintenance_work_orders_priority", table_name="maintenance_work_orders")
    op.drop_index("ix_maintenance_work_orders_location", table_name="maintenance_work_orders")
    op.drop_index("ix_maintenance_work_orders_category", table_name="maintenance_work_orders")
    op.drop_index("ix_maintenance_work_orders_work_order_code", table_name="maintenance_work_orders")
    op.drop_index("ix_maintenance_work_orders_hospital_id", table_name="maintenance_work_orders")
    op.drop_table("maintenance_work_orders")
