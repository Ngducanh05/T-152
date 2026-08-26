"""Merge ParkSmart Points with the applied auth and report-evidence head.

Revision ID: 20260824_0010
Revises: 0008, 20260822_0009
Create Date: 2026-08-24
"""

revision = "20260824_0010"
down_revision = ("0008", "20260822_0009")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Join the two already-defined schema histories without changing schema."""


def downgrade() -> None:
    """Split the history back to the ParkSmart Points and auth/evidence heads."""
