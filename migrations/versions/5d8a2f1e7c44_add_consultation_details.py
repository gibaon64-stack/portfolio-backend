"""Add consultation details and inquiry idempotency.

Revision ID: 5d8a2f1e7c44
Revises: 3c0e8a1594b2
Create Date: 2026-11-08 18:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = "5d8a2f1e7c44"
down_revision = "3c0e8a1594b2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inquiries", sa.Column("consultation_date", sa.Date(), nullable=True))
    op.add_column("inquiries", sa.Column("consultation_time", sa.String(length=5), nullable=True))
    op.add_column("inquiries", sa.Column("additional_requirements", sa.Text(), nullable=True))
    op.add_column("inquiries", sa.Column("idempotency_key", sa.String(length=64), nullable=True))
    op.create_index("ix_inquiries_idempotency_key", "inquiries", ["idempotency_key"], unique=True)


def downgrade():
    op.drop_index("ix_inquiries_idempotency_key", table_name="inquiries")
    op.drop_column("inquiries", "idempotency_key")
    op.drop_column("inquiries", "additional_requirements")
    op.drop_column("inquiries", "consultation_time")
    op.drop_column("inquiries", "consultation_date")
