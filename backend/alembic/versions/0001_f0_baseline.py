"""F0 baseline migration.

Revision ID: 0001_f0_baseline
Revises:
Create Date: 2026-11-26 00:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_f0_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply baseline revision (tables added starting in F1)."""


def downgrade() -> None:
    """Revert baseline revision."""
