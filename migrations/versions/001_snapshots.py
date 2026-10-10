"""Create immutable dataset snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None


def upgrade():
    op.create_table(
        "dataset_snapshots",
        sa.Column("version", sa.String(80), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("dataset_snapshots")
