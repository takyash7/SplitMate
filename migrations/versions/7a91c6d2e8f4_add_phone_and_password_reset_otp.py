"""Add phone number and password reset OTP table.

Revision ID: 7a91c6d2e8f4
Revises: e366819bf165
"""

from alembic import op
import sqlalchemy as sa


# Migration identifiers
revision = "7a91c6d2e8f4"
down_revision = "e366819bf165"
branch_labels = None
depends_on = None


def upgrade():
    # Add optional phone number to users table
    op.add_column(
        "users",
        sa.Column(
            "phone_number",
            sa.String(length=15),
            nullable=True
        )
    )

    # Ensure phone number is unique
    op.create_index(
        "ix_users_phone_number",
        "users",
        ["phone_number"],
        unique=True
    )

    # Create password reset OTP table
    op.create_table(
        "password_reset_otps",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True
        ),

        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False
        ),

        sa.Column(
            "otp_hash",
            sa.String(length=255),
            nullable=False
        ),

        sa.Column(
            "expires_at",
            sa.DateTime(),
            nullable=False
        ),

        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default="0"
        ),

        sa.Column(
            "used_at",
            sa.DateTime(),
            nullable=True
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp()
        )
    )

    op.create_index(
        "ix_password_reset_otps_user_id",
        "password_reset_otps",
        ["user_id"],
        unique=False
    )


def downgrade():
    op.drop_index(
        "ix_password_reset_otps_user_id",
        table_name="password_reset_otps"
    )

    op.drop_table("password_reset_otps")

    op.drop_index(
        "ix_users_phone_number",
        table_name="users"
    )

    op.drop_column("users", "phone_number")