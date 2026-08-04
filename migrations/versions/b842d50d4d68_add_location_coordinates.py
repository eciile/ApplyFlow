"""add location coordinates and commute radius

Revision ID: b842d50d4d68
Revises: 06146af5db5c
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b842d50d4d68"
down_revision: Union[str, Sequence[str], None] = "06146af5db5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("latitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("longitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "candidate_profiles",
        sa.Column("latitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "candidate_profiles",
        sa.Column("longitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "candidate_profiles",
        sa.Column(
            "max_commute_distance_km",
            sa.Float(),
            server_default="30",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "candidate_profiles",
        "max_commute_distance_km",
    )
    op.drop_column("candidate_profiles", "longitude")
    op.drop_column("candidate_profiles", "latitude")
    op.drop_column("jobs", "longitude")
    op.drop_column("jobs", "latitude")
