"""baseline

Empty baseline: locks the existing empire.db schema as revision 0.
Future migrations run forward from here. Detected cosmetic drift
(TEXT vs String, identical on SQLite) is intentionally ignored.

Revision ID: 2aa62647e5cc
Revises:
Create Date: 2026-04-16 19:07:27.420518
"""
from typing import Sequence, Union


revision: str = "2aa62647e5cc"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
