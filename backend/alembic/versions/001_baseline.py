"""Baseline migration - marks existing schema as starting point

Revision ID: 001_baseline
Revises:
Create Date: 2026-03-06
"""
from alembic import op

revision = '001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This is a baseline migration.
    # The existing schema (schema.sql + marketing_tables.sql + blog_tables.sql)
    # is assumed to already be applied.
    # Future migrations will build on top of this baseline.
    pass


def downgrade() -> None:
    # Cannot downgrade past baseline
    pass
