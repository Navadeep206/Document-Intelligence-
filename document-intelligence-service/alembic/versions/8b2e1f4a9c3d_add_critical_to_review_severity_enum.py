"""add_critical_to_review_severity_enum

Revision ID: 8b2e1f4a9c3d
Revises: 71ffd0d7fccb
Create Date: 2026-09-19 13:40:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b2e1f4a9c3d'
down_revision: Union[str, None] = '71ffd0d7fccb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add CRITICAL to review_severity_enum
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE review_severity_enum ADD VALUE IF NOT EXISTS 'CRITICAL'")


def downgrade() -> None:
    # PostgreSQL does not natively support removing an enum value from an enum type
    pass
