"""add_is_wildcard_to_recommendations

Revision ID: 49c47a54f264
Revises: b00467105c7b
Create Date: 2026-11-24 18:38:58.468960

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '49c47a54f264'
down_revision: Union[str, Sequence[str], None] = 'b00467105c7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("recommendations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_wildcard", sa.Boolean(), server_default=sa.text("0"), nullable=False)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("recommendations", schema=None) as batch_op:
        batch_op.drop_column("is_wildcard")
