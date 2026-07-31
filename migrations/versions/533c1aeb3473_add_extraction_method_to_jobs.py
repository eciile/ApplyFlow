"""add extraction method to jobs

Revision ID: 533c1aeb3473
Revises: 0ef992c599a2
Create Date: 2026-07-31 15:07:47.291558

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '533c1aeb3473'
down_revision: Union[str, Sequence[str], None] = '0ef992c599a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "extraction_method",
            sa.String(length=30),
            nullable=False,
            server_default="json_ld",
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "jobs",
        "extraction_method",
    )