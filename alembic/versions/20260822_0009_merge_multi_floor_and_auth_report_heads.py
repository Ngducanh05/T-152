"""Merge multi-floor and auth/report migration heads.

Revision ID: 20260822_0009
Revises: 0007, 20260821_0008
Create Date: 2026-08-22
"""

revision = "20260822_0009"
down_revision = ("0007", "20260821_0008")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge the two existing migration branches without changing schema."""
    pass


def downgrade() -> None:
    """Downgrade from the merge point back to both parent heads."""
    pass
