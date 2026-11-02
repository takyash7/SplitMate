"""Add expense creator

Revision ID: 58c0c86fb81e
Revises: 39354d83c28a
Create Date: 2026-11-01 11:32:35.665882

"""

from alembic import op
import sqlalchemy as sa


revision = '58c0c86fb81e'
down_revision = '39354d83c28a'
branch_labels = None
depends_on = None


def upgrade():

    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('created_by_id', sa.Integer(), nullable=True)
        )

        batch_op.create_index(
            'ix_expenses_created_by_id',
            ['created_by_id'],
            unique=False
        )

        batch_op.create_foreign_key(
            'fk_expenses_created_by_id_users',
            'users',
            ['created_by_id'],
            ['id']
        )


def downgrade():

    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_expenses_created_by_id_users',
            type_='foreignkey'
        )

        batch_op.drop_index('ix_expenses_created_by_id')

        batch_op.drop_column('created_by_id')