"""a manual order for the register

`participants.display_order` — the number the operator types on a participant's screen,
which decides where that person appears. It drives both surfaces that show the register,
because both read the same `/api/v1/content` payload in the order the API returns it:
the home page's participant slider and `/participants`.

NULL MEANS "NOT PLACED", AND THAT IS THE POINT
    Twenty-five records do not need twenty-five numbers. A record with no
    `display_order` keeps the order it always had (batch, then id), and every placed
    record sorts before every unplaced one. Pin the three who should lead the page and
    leave the rest alone.

WHY NOT A `position` COLUMN WITH A UNIQUE CONSTRAINT
    Because then every insert and every reorder rewrites the rows around it, and a swap
    becomes a multi-row transaction that can half-succeed. A sparse integer means one
    row changes when one row is edited.

WHY PLAIN `add_column` AND NOT `batch_alter_table`
    On MySQL and MariaDB, batch mode RECREATES the table — copying every participant
    row to do it. The register is live and holds consent records this project exists to
    protect, so this migration is deliberately metadata-only: `ALTER TABLE ADD COLUMN`
    is instant, needs no copy, and cannot half-finish. (MariaDB also rejects the CHECK
    that batch mode emits in some cases — see e5e24146b7f5.)

The index is not for the API's ORDER BY — the register is twenty-five rows. It is for
the admin list and the CSV export, which sort on this column with filters applied and
will still be running when the register is two thousand.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d8f1a64b27'
down_revision = 'e5e24146b7f5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('participants', sa.Column('display_order', sa.Integer(), nullable=True))
    op.create_index(
        'ix_participants_display_order', 'participants', ['display_order'], unique=False
    )


def downgrade():
    op.drop_index('ix_participants_display_order', table_name='participants')
    op.drop_column('participants', 'display_order')
