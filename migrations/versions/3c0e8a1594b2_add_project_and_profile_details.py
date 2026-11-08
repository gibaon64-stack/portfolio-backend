"""Add profile details and project presentation fields.

Revision ID: 3c0e8a1594b2
Revises: a8d59e14c239
Create Date: 2026-11-08 17:45:00
"""
from alembic import op
import sqlalchemy as sa


revision = "3c0e8a1594b2"
down_revision = "a8d59e14c239"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("profiles", sa.Column("professional_title", sa.String(length=180), nullable=False, server_default=""))
    op.add_column("profiles", sa.Column("skills", sa.JSON(), nullable=True))
    op.add_column("profiles", sa.Column("experience", sa.JSON(), nullable=True))
    op.add_column("profiles", sa.Column("education", sa.JSON(), nullable=True))
    op.add_column("profiles", sa.Column("certifications", sa.JSON(), nullable=True))
    op.add_column("projects", sa.Column("detailed_description", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("projects", "featured")
    op.drop_column("projects", "detailed_description")
    op.drop_column("profiles", "certifications")
    op.drop_column("profiles", "education")
    op.drop_column("profiles", "experience")
    op.drop_column("profiles", "skills")
    op.drop_column("profiles", "professional_title")
