"""Add signed Points ledger, voucher catalog, redemptions, and issued vouchers."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260830_0016"
down_revision = "20260826_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE reward_source_type_enum ADD VALUE IF NOT EXISTS 'VOUCHER_REDEMPTION'")
    op.execute("ALTER TYPE reward_transaction_type_enum ADD VALUE IF NOT EXISTS 'VOUCHER_REDEMPTION'")
    op.execute("ALTER TYPE reward_transaction_type_enum ADD VALUE IF NOT EXISTS 'VOUCHER_REFUND'")
    op.execute("ALTER TYPE reward_transaction_status_enum ADD VALUE IF NOT EXISTS 'POSTED'")
    op.drop_constraint("ck_reward_transactions_points_nonnegative", "reward_transactions", type_="check")
    op.alter_column("reward_transactions", "points", new_column_name="points_delta")
    op.create_check_constraint(
        "ck_reward_transactions_points_delta_nonzero", "reward_transactions", "points_delta <> 0"
    )
    op.drop_constraint("uq_reward_transactions_source", "reward_transactions", type_="unique")
    op.create_unique_constraint(
        "uq_reward_transactions_source_transaction_type",
        "reward_transactions",
        ["source_type", "source_reference", "transaction_type"],
    )

    redemption_status = postgresql.ENUM(
        "COMPLETED", "REFUNDED", name="reward_redemption_status_enum", create_type=False
    )
    voucher_status = postgresql.ENUM(
        "ISSUED", "APPLIED", "EXPIRED", "CANCELLED", name="parking_voucher_status_enum", create_type=False
    )
    bind = op.get_bind()
    redemption_status.create(bind, checkfirst=True)
    voucher_status.create(bind, checkfirst=True)
    op.create_table(
        "reward_catalog_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("points_cost", sa.Integer(), nullable=False),
        sa.Column("free_minutes", sa.Integer(), nullable=False),
        sa.Column("validity_days", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.CheckConstraint("points_cost > 0", name="ck_reward_catalog_items_points_cost_positive"),
        sa.CheckConstraint(
            "free_minutes > 0 AND free_minutes <= 60", name="ck_reward_catalog_items_free_minutes_range"
        ),
        sa.CheckConstraint("validity_days > 0", name="ck_reward_catalog_items_validity_days_positive"),
        sa.CheckConstraint("version >= 0", name="ck_reward_catalog_items_version_nonnegative"),
    )
    op.bulk_insert(
        sa.table(
            "reward_catalog_items",
            sa.column("id", sa.String),
            sa.column("code", sa.String),
            sa.column("name", sa.String),
            sa.column("points_cost", sa.Integer),
            sa.column("free_minutes", sa.Integer),
            sa.column("validity_days", sa.Integer),
            sa.column("is_active", sa.Boolean),
            sa.column("version", sa.Integer),
        ),
        [
            {
                "id": "REWARD-CATALOG-PARKING-15M",
                "code": "PARKING_15M",
                "name": "Miễn phí 15 phút đỗ xe",
                "points_cost": 100,
                "free_minutes": 15,
                "validity_days": 30,
                "is_active": True,
                "version": 0,
            },
            {
                "id": "REWARD-CATALOG-PARKING-30M",
                "code": "PARKING_30M",
                "name": "Miễn phí 30 phút đỗ xe",
                "points_cost": 200,
                "free_minutes": 30,
                "validity_days": 30,
                "is_active": True,
                "version": 0,
            },
            {
                "id": "REWARD-CATALOG-PARKING-60M",
                "code": "PARKING_60M",
                "name": "Miễn phí 60 phút đỗ xe",
                "points_cost": 400,
                "free_minutes": 60,
                "validity_days": 30,
                "is_active": True,
                "version": 0,
            },
        ],
    )
    op.create_table(
        "reward_redemptions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("parking_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "catalog_item_id",
            sa.String(64),
            sa.ForeignKey("reward_catalog_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("points_cost_snapshot", sa.Integer(), nullable=False),
        sa.Column("free_minutes_snapshot", sa.Integer(), nullable=False),
        sa.Column("validity_days_snapshot", sa.Integer(), nullable=False),
        sa.Column("status", redemption_status, nullable=False, server_default=sa.text("'COMPLETED'")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("points_cost_snapshot > 0", name="ck_reward_redemptions_points_cost_positive"),
        sa.CheckConstraint(
            "free_minutes_snapshot > 0 AND free_minutes_snapshot <= 60", name="ck_reward_redemptions_free_minutes_range"
        ),
        sa.CheckConstraint("validity_days_snapshot > 0", name="ck_reward_redemptions_validity_days_positive"),
        sa.CheckConstraint("version >= 0", name="ck_reward_redemptions_version_nonnegative"),
    )
    op.create_index("ix_reward_redemptions_user_id", "reward_redemptions", ["user_id"])
    op.create_table(
        "parking_vouchers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("parking_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "redemption_id",
            sa.String(64),
            sa.ForeignKey("reward_redemptions.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "catalog_item_id",
            sa.String(64),
            sa.ForeignKey("reward_catalog_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("catalog_code_snapshot", sa.String(64), nullable=False),
        sa.Column("points_cost_snapshot", sa.Integer(), nullable=False),
        sa.Column("free_minutes_snapshot", sa.Integer(), nullable=False),
        sa.Column("validity_days_snapshot", sa.Integer(), nullable=False),
        sa.Column("status", voucher_status, nullable=False, server_default=sa.text("'ISSUED'")),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "applied_session_id",
            sa.String(64),
            sa.ForeignKey("parking_sessions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("points_cost_snapshot > 0", name="ck_parking_vouchers_points_cost_positive"),
        sa.CheckConstraint(
            "free_minutes_snapshot > 0 AND free_minutes_snapshot <= 60", name="ck_parking_vouchers_free_minutes_range"
        ),
        sa.CheckConstraint("validity_days_snapshot > 0", name="ck_parking_vouchers_validity_days_positive"),
        sa.CheckConstraint("expires_at > issued_at", name="ck_parking_vouchers_expiry_after_issue"),
        sa.CheckConstraint("version >= 0", name="ck_parking_vouchers_version_nonnegative"),
    )
    op.create_index("ix_parking_vouchers_user_id", "parking_vouchers", ["user_id"])
    op.create_index(
        "uq_parking_vouchers_applied_session",
        "parking_vouchers",
        ["applied_session_id"],
        unique=True,
        postgresql_where=sa.text("applied_session_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_parking_vouchers_applied_session", table_name="parking_vouchers")
    op.drop_index("ix_parking_vouchers_user_id", table_name="parking_vouchers")
    op.drop_table("parking_vouchers")
    op.drop_index("ix_reward_redemptions_user_id", table_name="reward_redemptions")
    op.drop_table("reward_redemptions")
    op.drop_table("reward_catalog_items")
    op.drop_constraint("uq_reward_transactions_source_transaction_type", "reward_transactions", type_="unique")
    op.create_unique_constraint(
        "uq_reward_transactions_source", "reward_transactions", ["source_type", "source_reference"]
    )
    op.drop_constraint("ck_reward_transactions_points_delta_nonzero", "reward_transactions", type_="check")
    op.alter_column("reward_transactions", "points_delta", new_column_name="points")
    op.create_check_constraint("ck_reward_transactions_points_nonnegative", "reward_transactions", "points >= 0")
