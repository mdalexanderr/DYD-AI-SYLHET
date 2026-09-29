"""Drop every table in the DATABASE_URL database.

Used by alwaysdata-bootstrap.sh to recover from a half-applied migration.
MySQL and MariaDB run DDL non-transactionally: a migration interrupted between
"column added" and "revision stamped" leaves a schema Alembic can no longer
reconcile — the classic "Duplicate column name" on the next upgrade. The only
reliable recovery is a clean schema. This is safe to run on a bootstrap box,
which by definition holds no real data.

Reads DATABASE_URL from the environment. Fails loudly if it is missing.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy.engine import make_url
import pymysql


def main() -> int:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        print("reset_db: DATABASE_URL is not set", file=sys.stderr)
        return 2

    url = make_url(raw)
    conn = pymysql.connect(
        host=url.host,
        port=url.port or 3306,
        user=url.username,
        password=url.password or "",
        database=url.database,
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema=%s",
                (url.database,),
            )
            tables = [row[0] for row in cur.fetchall()]
            for name in tables:
                cur.execute(f"DROP TABLE IF EXISTS `{name}`")
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
        print(f"reset_db: dropped {len(tables)} tables")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
