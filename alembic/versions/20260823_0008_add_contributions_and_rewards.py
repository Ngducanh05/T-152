"""Add verified community contributions and ParkSmart Points.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-23
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


slot_observation_status_enum = postgresql.ENUM(
    "PENDING", "VERIFIED", "REJECTED", "EXPIRED",
    name="slot_observation_status_enum",
    create_type=False,
)
report_verification_outcome_enum = postgresql.ENUM(
    "PENDING", "CONFIRMED", "REJECTED", "DUPLICATE", "UNVERIFIABLE",
    name="wrong_parking_report_verification_outcome_enum",
    create_type=False,
)
reward_source_type_enum = postgresql.ENUM(
    "ADJACENT_SLOT_OBSERVATION", "WRONG_PARKING_REPORT",
    name="reward_source_type_enum",
    create_type=False,
)
reward_transaction_type_enum = postgresql.ENUM(
    "CONTRIBUTION_REWARD", "REWARD_REVERSAL", "ADMIN_ADJUSTMENT",
    name="reward_transaction_type_enum",
    create_type=False,
)
reward_transaction_status_enum = postgresql.ENUM(
    "PENDING", "EARNED", "CANCELLED",
    name="reward_transaction_status_enum",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    slot_observation_status_enum.create(bind, checkfirst=True)
    report_verification_outcome_enum.create(bind, checkfirst=True)
    reward_source_type_enum.create(bind, checkfirst=True)
    reward_transaction_type_enum.create(bind, checkfirst=True)
    reward_transaction_status_enum.create(bind, checkfirst=True)
    op.execute("ALTER TYPE actor_type_enum ADD VALUE IF NOT EXISTS 'ADMIN'")

    op.create_table(
        "slot_observations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("observer_user_id", sa.String(length=64), nullable=False),
        sa.Column("observer_session_id", sa.String(length=64), nullable=False),
        sa.Column("slot_id", sa.String(length=64), nullable=False),
        sa.Column(
            "observed_status",
            postgresql.ENUM(name="slot_status_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("verification_status", slot_observation_status_enum, server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("reward_points", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("observed_slot_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.String(length=64), nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("reward_points >= 0", name="ck_slot_observations_reward_nonnegative"),
        sa.CheckConstraint("version >= 0", name="ck_slot_observations_version_nonnegative"),
        sa.CheckConstraint("observed_slot_version >= 0", name="ck_slot_observations_slot_version_nonnegative"),
        sa.CheckConstraint("expires_at > created_at", name="ck_slot_observations_expiry_after_creation"),
        sa.ForeignKeyConstraint(["observer_user_id"], ["parking_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["observer_session_id"], ["parking_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["slot_id"], ["parking_slots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("observer_session_id", "slot_id", name="uq_slot_observations_session_slot"),
    )
    op.create_index("ix_slot_observations_verification_created", "slot_observations", ["verification_status", "created_at"])
    op.create_index("ix_slot_observations_slot_created", "slot_observations", ["slot_id", "created_at"])
    op.create_index("ix_slot_observations_user_created", "slot_observations", ["observer_user_id", "created_at"])

    op.create_table(
        "reward_transactions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", reward_source_type_enum, nullable=False),
        sa.Column("source_reference", sa.String(length=64), nullable=False),
        sa.Column("transaction_type", reward_transaction_type_enum, server_default=sa.text("'CONTRIBUTION_REWARD'"), nullable=False),
        sa.Column("status", reward_transaction_status_enum, server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.CheckConstraint("points >= 0", name="ck_reward_transactions_points_nonnegative"),
        sa.ForeignKeyConstraint(["user_id"], ["parking_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type", "source_reference", name="uq_reward_transactions_source"),
    )
    op.create_index("ix_reward_transactions_user_status_created", "reward_transactions", ["user_id", "status", "created_at"])

    op.add_column("wrong_parking_reports", sa.Column("verification_outcome", report_verification_outcome_enum, nullable=True))
    op.add_column("wrong_parking_reports", sa.Column("reward_points", sa.Integer(), nullable=True))
    op.add_column("wrong_parking_reports", sa.Column("duplicate_candidate_of_id", sa.String(length=64), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE wrong_parking_reports
            SET verification_outcome = CASE
                    WHEN status = 'OPEN' THEN 'PENDING'::wrong_parking_report_verification_outcome_enum
                    ELSE 'UNVERIFIABLE'::wrong_parking_report_verification_outcome_enum
                END,
                reward_points = 0
            """
        )
    )
    op.alter_column("wrong_parking_reports", "verification_outcome", existing_type=report_verification_outcome_enum, nullable=False, server_default=sa.text("'PENDING'"))
    op.alter_column("wrong_parking_reports", "reward_points", existing_type=sa.Integer(), nullable=False, server_default=sa.text("0"))
    op.create_check_constraint("ck_wrong_parking_reports_reward_nonnegative", "wrong_parking_reports", "reward_points >= 0")
    op.create_foreign_key("fk_wrong_parking_reports_duplicate_candidate", "wrong_parking_reports", "wrong_parking_reports", ["duplicate_candidate_of_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_wrong_parking_reports_duplicate_candidate_of_id", "wrong_parking_reports", ["duplicate_candidate_of_id"])


def downgrade() -> None:
    op.drop_index("ix_wrong_parking_reports_duplicate_candidate_of_id", table_name="wrong_parking_reports")
    op.drop_constraint("fk_wrong_parking_reports_duplicate_candidate", "wrong_parking_reports", type_="foreignkey")
    op.drop_constraint("ck_wrong_parking_reports_reward_nonnegative", "wrong_parking_reports", type_="check")
    op.drop_column("wrong_parking_reports", "duplicate_candidate_of_id")
    op.drop_column("wrong_parking_reports", "reward_points")
    op.drop_column("wrong_parking_reports", "verification_outcome")

    op.drop_index("ix_reward_transactions_user_status_created", table_name="reward_transactions")
    op.drop_table("reward_transactions")
    op.drop_index("ix_slot_observations_user_created", table_name="slot_observations")
    op.drop_index("ix_slot_observations_slot_created", table_name="slot_observations")
    op.drop_index("ix_slot_observations_verification_created", table_name="slot_observations")
    op.drop_table("slot_observations")

    bind = op.get_bind()
    reward_transaction_status_enum.drop(bind, checkfirst=True)
    reward_transaction_type_enum.drop(bind, checkfirst=True)
    reward_source_type_enum.drop(bind, checkfirst=True)
    report_verification_outcome_enum.drop(bind, checkfirst=True)
    slot_observation_status_enum.drop(bind, checkfirst=True)
    # PostgreSQL enum values cannot be removed safely in-place; ADMIN remains.
