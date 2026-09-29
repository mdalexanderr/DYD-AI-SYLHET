"""a stat's surface

Revision ID: 79bd7ba316c7
Revises: c876e5ccb600

WHY A STAT NEEDS A SURFACE
    `stats` is now read by two halves. The Jinja pages' `stat_strip` sections select
    their rows by id; the React home strip asks the content API for its four headline
    figures. Eleven rows exist, and without this column the strip would render all
    eleven — the classic "one table, two readers" failure, where each reader silently
    inherits the other's data.

    `group = 'programme'` is the React strip. Everything else keeps the empty default
    and is picked by section id exactly as before, so nothing that already worked
    changes behaviour.

    THE SERVER DEFAULT IS THE POINT, not decoration: SQLite cannot add a NOT NULL column
    to a populated table without one, and the existing eleven rows have to get a value.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '79bd7ba316c7'
down_revision = 'c876e5ccb600'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stats', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'group',
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("''"),
            )
        )
        batch_op.create_index(batch_op.f('ix_stats_group'), ['group'], unique=False)


def downgrade():
    with op.batch_alter_table('stats', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stats_group'))
        batch_op.drop_column('group')
