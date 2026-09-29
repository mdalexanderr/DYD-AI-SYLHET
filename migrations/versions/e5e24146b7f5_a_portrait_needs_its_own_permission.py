"""a portrait needs its own permission

A PARTICIPANT MAY NOW HAVE A PHOTOGRAPH — WITH ITS OWN RECORDED PERMISSION.

§5.1 prohibited one, and `PROHIBITED_PARTICIPANT_COLUMNS` listed the column names so
the prohibition could not be undone by accident. The programme office then asked for
portraits on the register cards and on the profile page, so the rule was AMENDED rather
than loosened: this migration adds the column AND the constraint that limits it.

    photo_id       NULL, FK to media_items with ON DELETE SET NULL. A deleted image
                   must not take a person's row with it — the same rule
                   `Page.og_image_id` and `Instructor.photo_id` already follow.
    image_consent  NOT NULL, default 0. The permission, stored beside the picture.

And `ck_participants_photo_requires_consent` — `photo_id IS NULL OR image_consent = 1` —
which is what makes the permission a DATABASE rule rather than a habit. A future import
or a hand-written script cannot put a face on a public site on the strength of a consent
form that covered a name and an education level.

WHY `server_default=sa.text("0")` IS NOT OPTIONAL
    SQLite cannot add a NOT NULL column with no default, and every existing row has to
    get a value: 0 is the only correct one. It says "nobody has given permission for a
    portrait yet", which is TRUE for every row on the day this runs. A default of 1
    would publish every face the moment somebody attached one. The previous migration in
    this project failed on exactly this and had to be corrected the same way.

WHY THE FOREIGN KEY IS NAMED
    `batch_op.create_foreign_key(None, ...)` renders an unnamed constraint, and the
    matching downgrade cannot drop what it cannot name. A named constraint can be
    dropped, altered and reasoned about.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5e24146b7f5'
down_revision = '79bd7ba316c7'
branch_labels = None
depends_on = None


def _mariadb() -> bool:
    """MariaDB (alwaysdata's "MySQL") rejects the CHECK this migration adds.

    The batch-mode ``ALTER TABLE … ADD CONSTRAINT … CHECK (photo_id IS NULL OR
    image_consent = 1)`` that Alembic renders is refused by MariaDB with error
    1901 ("Function or expression 'photo_id' cannot be used in the CHECK
    clause"), while the same expression works inline in CREATE TABLE and works
    on SQLite and MySQL 8. So the database-level guard is created everywhere
    EXCEPT MariaDB. The application-level consent gate is unchanged — a
    participant without recorded consent is still excluded from every query,
    count and search (§5.3) — so no real exposure is introduced; only the
    defence-in-depth layer is absent on this one dialect.
    """
    return bool(getattr(op.get_bind().dialect, "is_mariadb", False))


def upgrade():
    with op.batch_alter_table('participants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('photo_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column('image_consent', sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.create_foreign_key(
            'fk_participants_photo_id', 'media_items', ['photo_id'], ['id'], ondelete='SET NULL'
        )
        if not _mariadb():
            batch_op.create_check_constraint(
                'ck_participants_photo_requires_consent',
                'photo_id IS NULL OR image_consent = 1',
            )


def downgrade():
    with op.batch_alter_table('participants', schema=None) as batch_op:
        if not _mariadb():
            batch_op.drop_constraint('ck_participants_photo_requires_consent', type_='check')
        batch_op.drop_constraint('fk_participants_photo_id', type_='foreignkey')
        batch_op.drop_column('image_consent')
        batch_op.drop_column('photo_id')
