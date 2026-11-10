"""Add profile technologies, milestone images, and project ordering.

Revision ID: 76d4b8c2f901
Revises: 5d8a2f1e7c44
Create Date: 2026-11-10 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "76d4b8c2f901"
down_revision = "5d8a2f1e7c44"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("profiles", sa.Column("technologies", sa.JSON(), nullable=True))
    op.add_column("journey_entries", sa.Column("organization", sa.String(length=180), nullable=True))
    op.add_column("journey_entries", sa.Column("image_urls", sa.JSON(), nullable=True))
    op.add_column(
        "projects",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    projects = sa.table(
        "projects",
        sa.column("id", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("position", sa.Integer()),
    )
    connection = op.get_bind()
    project_ids = list(connection.execute(
        sa.select(projects.c.id).order_by(projects.c.created_at.desc(), projects.c.id.desc())
    ).scalars())
    for position, project_id in enumerate(project_ids):
        connection.execute(
            projects.update().where(projects.c.id == project_id).values(position=position)
        )


def downgrade():
    op.drop_column("projects", "position")
    op.drop_column("journey_entries", "image_urls")
    op.drop_column("journey_entries", "organization")
    op.drop_column("profiles", "technologies")
