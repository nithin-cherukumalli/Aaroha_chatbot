"""initial production schema

Revision ID: 20261011_0001
Revises:
Create Date: 2026-10-11
"""
from alembic import op
from app.database import Base
from app import models  # noqa: F401

revision = "20261011_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
