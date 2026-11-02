"""Create patients table for patient records and registration

Revision ID: 0004_create_patients_table
Revises: 0003_maintenance_work_orders
Create Date: 2026-11-02 10:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0004_create_patients_table"
down_revision: Union[str, None] = "0003_maintenance_work_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_reference", sa.String(length=100), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("patient_reference", name="uq_patients_patient_reference"),
    )
    op.create_index("ix_patients_patient_reference", "patients", ["patient_reference"])
    op.create_index("ix_patients_full_name", "patients", ["full_name"])
    op.create_index("ix_patients_phone_number", "patients", ["phone_number"])


def downgrade() -> None:
    op.drop_index("ix_patients_phone_number", table_name="patients")
    op.drop_index("ix_patients_full_name", table_name="patients")
    op.drop_index("ix_patients_patient_reference", table_name="patients")
    op.drop_table("patients")

