import os
import sys
from logging.config import fileConfig
import sqlalchemy as sa
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Append app path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings, normalize_database_url
from app.db.base import Base
# Ensure all models are loaded for target_metadata inspection
from app.models import (
    Hospital,
    Department,
    Doctor,
    AppointmentSlot,
    Appointment,
    Patient,
    LabOrder,
    InsuranceProvider,
    InsurancePlan,
    WorkflowException,
    AuditEvent,
    MaintenanceWorkOrder,
)

config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set database URL dynamically from app settings if not overridden
db_url = normalize_database_url(os.getenv("DATABASE_URL", settings.DATABASE_URL))
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    from sqlalchemy import create_engine

    connectable = create_engine(
        db_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
    connection=connection,
    target_metadata=target_metadata,
    version_table_pk=True,
    version_table="alembic_version",
    version_table_column_type=sa.String(length=255),
)

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
