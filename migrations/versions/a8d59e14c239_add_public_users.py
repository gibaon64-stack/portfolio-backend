"""Add separately authenticated public users.

Revision ID: a8d59e14c239
Revises: 0142fa0601a3
Create Date: 2026-11-08 16:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "a8d59e14c239"
down_revision = "0142fa0601a3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inquiries", sa.Column("business_name", sa.String(length=160), nullable=True))
    op.add_column("inquiries", sa.Column("timeline", sa.String(length=120), nullable=True))
    op.add_column("inquiries", sa.Column("internal_notes", sa.Text(), nullable=False, server_default=""))
    op.add_column("services", sa.Column("pricing", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("services", sa.Column("image_url", sa.String(length=500), nullable=True))
    op.add_column("profiles", sa.Column("contact_image_url", sa.String(length=500), nullable=True))
    op.add_column("profiles", sa.Column("hero_image_url", sa.String(length=500), nullable=True))
    for column in (
        "about_intro",
        "about_who_we_are",
        "about_mission",
        "about_what_we_do",
        "about_approach",
        "about_why_choose_us",
    ):
        op.add_column("profiles", sa.Column(column, sa.Text(), nullable=False, server_default=""))
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index("ix_users_email", ["email"], unique=True)
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=255), nullable=False),
        sa.Column("secure_url", sa.String(length=1000), nullable=False),
        sa.Column("folder", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_email")
    op.drop_table("users")
    op.drop_table("media_assets")
    op.drop_column("services", "pricing")
    op.drop_column("services", "image_url")
    op.drop_column("profiles", "contact_image_url")
    op.drop_column("profiles", "hero_image_url")
    for column in (
        "about_why_choose_us",
        "about_approach",
        "about_what_we_do",
        "about_mission",
        "about_who_we_are",
        "about_intro",
    ):
        op.drop_column("profiles", column)
    op.drop_column("inquiries", "internal_notes")
    op.drop_column("inquiries", "timeline")
    op.drop_column("inquiries", "business_name")
