
"""Add active status to group members

Revision ID: e366819bf165
Revises: 58c0c86fb81e
Create Date: 2026-11-01 12:19:09.990541
"""

from alembic import op
import sqlalchemy as sa

revision = 'e366819bf165'
down_revision = '58c0c86fb81e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('group_members', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_active',
                sa.Boolean(),
                nullable=False,
                server_default=sa.true()
            )
        )


def downgrade():
    with op.batch_alter_table('group_members', schema=None) as batch_op:
        batch_op.drop_column('is_active')

