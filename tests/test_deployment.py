"""Deployment: the entry point, the proxy, the cache headers and the backup.

execution-plan step P9; plan.md §17.2, §17.5, §17.6.

WHY THESE ARE TESTS AND NOT A CHECKLIST IN A README
    Each one covers a rule that is invisible on the developer's machine and only
    breaks on the host:

    * the ORDER of `APP_ENV` and the app import — reversed, a public site is a
      development instance, and nothing on the page says so;
    * the proxy headers — without them every absolute URL and the HSTS decision are
      made from an Apache-to-uWSGI connection, which is http;
    * the cache headers — a wrong one serves a stale stylesheet for a year;
    * the backup — the only artefact that matters on the day the database is gone,
      and the one thing a person cannot test by looking at the site.

    A rule that only a careful deploy can get right is a rule that will be got
    wrong, so each is asserted here against the real files a host reads.
"""

from __future__ import annotations

import gzip
import io
import os
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from flask import Response

from app import _cache_static
from app.cli import _dump_mysql
from app.constants import BackupKind, BackupStatus
from app.extensions import db
from app.models import Backup

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: A DSN that satisfies ProdConfig.validate() without a server anywhere near it.
#: Nothing below connects: SQLAlchemy builds an engine on first use, and the point of
#: these tests is that the app can be *built* on a host whose database is briefly
#: unreachable — which is the state a deploy is in for its first ten seconds.
FAKE_PRODUCTION_DSN = (
    "mysql+pymysql://acct:not-a-real-password@mysql-acct.alwaysdata.net/"
    "acct_sylhet?charset=utf8mb4"
)


# ─────────────────────────────────────────────────────────────────────────────
# The entry point
# ─────────────────────────────────────────────────────────────────────────────


def test_the_entry_point_chooses_production_before_the_app_reads_its_config():
    """`app/config.py` decides its class AT IMPORT TIME, so the order is load-bearing.

    `os.environ.setdefault("APP_ENV", "production")` that runs one line late means the
    config module has already picked the development class, and the site comes up in
    debug mode with secure cookies off — on a public host, with the panel showing a
    perfectly healthy site.
    """
    source = (PROJECT_ROOT / "wsgi.py").read_text(encoding="utf-8")

    assert 'os.environ.setdefault("APP_ENV", "production")' in source
    assert "def _build_application" in source
    assert source.index("setdefault(\"APP_ENV\"") < source.index("def _build_application"), (
        "the APP_ENV default must be set before the app is imported"
    )

    # The import is INSIDE the builder, so it can only run after the line above. The
    # docstring also mentions `create_app`, which is why the search starts at the
    # function rather than at the top of the file.
    builder = source[source.index("def _build_application"):]
    assert builder.index("from app import create_app") < builder.index("create_app()"), (
        "the app must be imported at call time, not at import time"
    )


def test_the_entry_point_puts_its_own_directory_on_the_path():
    """uWSGI does not guarantee the application root is importable.

    "Working directory" in the panel sets the process's cwd, which is a different
    thing, and ModuleNotFoundError here surfaces as a bare 500 with a log line that
    says only "could not import".
    """
    source = (PROJECT_ROOT / "wsgi.py").read_text(encoding="utf-8")

    assert "PROJECT_ROOT = Path(__file__).resolve().parent" in source
    assert "sys.path.insert(0, str(PROJECT_ROOT))" in source


def test_the_entry_point_exposes_both_names_a_host_might_look_for():
    """uWSGI looks for `application`; some tooling looks for `app`. Both must exist."""
    source = (PROJECT_ROOT / "wsgi.py").read_text(encoding="utf-8")

    assert "application = _build_application()" in source
    assert "app = application" in source


def test_the_passenger_entry_point_hands_over_instead_of_bootstrapping_again():
    """One bootstrap, two hosts.

    cPanel's panel points at a FILENAME and alwaysdata's at a FILE PATH, so there are
    two entry files — but the ordering rule that matters must exist in exactly one
    place, or the second copy is the one that is wrong.
    """
    source = (PROJECT_ROOT / "passenger_wsgi.py").read_text(encoding="utf-8")

    assert "from wsgi import app, application" in source
    assert "create_app" not in source, "passenger_wsgi.py must not build an app of its own"
    assert 'setdefault("APP_ENV"' not in source, "it must not repeat the APP_ENV decision"


def test_the_production_entry_point_builds_an_app(tmp_path):
    """The end-to-end claim: `import wsgi` with a production environment yields a Flask
    application. Run in a subprocess, because `app/config.py` reads the environment at
    import time and this test process has already imported it as a test config."""
    environment = {
        **os.environ,
        "APP_ENV": "production",
        "SECRET_KEY": "a" * 48,
        "DATABASE_URL": FAKE_PRODUCTION_DSN,
        "ALLOWED_HOSTS": "acct.alwaysdata.net",
        "APP_URL": "https://acct.alwaysdata.net",
        "ADMIN_URL_PREFIX": "admin",
        "TRUST_PROXY_HEADERS": "true",
        "MAIL_PROVIDER": "dryrun",
        "UPLOAD_ROOT": str(tmp_path / "uploads"),
        "BACKUP_ROOT": str(tmp_path / "backups"),
        "VAR_DIR": str(tmp_path / "var"),
        "LOG_DIR": str(tmp_path / "logs"),
        "CACHE_DIR": str(tmp_path / "cache"),
        "PYTHONIOENCODING": "utf-8",
    }
    completed = subprocess.run(
        [sys.executable, "-c",
         "import wsgi; print('BUILT', type(wsgi.application).__name__, "
         "wsgi.app is wsgi.application, wsgi.application.config['APP_ENV'])"],
        cwd=PROJECT_ROOT, env=environment, capture_output=True, text=True, timeout=180,
    )

    assert completed.returncode == 0, completed.stderr[-3000:]
    assert "BUILT Flask True production" in completed.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Proxy, HSTS and static caching
# ─────────────────────────────────────────────────────────────────────────────


def test_the_proxy_headers_are_not_trusted_outside_production(app):
    """Trusting X-Forwarded-* means believing a header a client can send.

    Safe exactly when the app cannot be reached except through the proxy. Believing it
    anywhere else lets a visitor claim to be on https, and a spoofed client address
    walks straight past the admin IP allowlist.
    """
    from werkzeug.middleware.proxy_fix import ProxyFix

    assert not isinstance(app.wsgi_app, ProxyFix)


def test_production_turns_the_proxy_on_by_default():
    """The failure it prevents is silent: without it `request.is_secure` is False on an
    HTTPS site, so HSTS is not sent and the sitemap advertises http:// URLs."""
    from app.config import ProdConfig

    assert ProdConfig.TRUST_PROXY_HEADERS is True


def test_a_hashed_asset_is_cacheable_for_a_year_and_a_plain_one_is_not(client):
    """Vite puts a content hash in the filename, so an asset URL is that file for ever.

    `/static/css/app.css` keeps its name across builds, which is exactly why it must
    be revalidated: `immutable` on an unhashed file serves the old stylesheet for a
    year after a deploy, and the operator's only clue is a layout that looks wrong to
    other people.
    """
    hashed = client.get("/static/spa/spa-assets/index-CuTxjTqP.css")
    assert hashed.status_code == 200
    assert "immutable" in hashed.headers["Cache-Control"]
    assert "max-age=31536000" in hashed.headers["Cache-Control"]

    plain = client.get("/static/css/app.css")
    assert plain.status_code == 200
    assert "immutable" not in plain.headers["Cache-Control"]
    assert "max-age=3600" in plain.headers["Cache-Control"]


def test_the_cache_rule_leaves_an_answer_that_is_already_decided_alone(app):
    """The media route sets its own `immutable` (§13.1) and a download has its own
    reasons. A blanket rule here would overwrite a more careful decision made closer
    to the data — and the file that gets re-served for a year is a photograph the
    participant asked to have withdrawn."""
    prefix = ("/static/spa/spa-assets/",)

    with app.test_request_context("/static/css/app.css"):
        decided = Response("x", headers={"Cache-Control": "private, no-store"})
        _cache_static(app, decided, prefix)
        assert decided.headers["Cache-Control"] == "private, no-store"

        undecided = Response("x")
        _cache_static(app, undecided, prefix)
        assert undecided.headers["Cache-Control"] == "public, max-age=3600"

    with app.test_request_context("/participants"):
        page = Response("<html>")
        _cache_static(app, page, prefix)
        assert "Cache-Control" not in page.headers, "only /static/ is touched"


def test_the_sitemap_advertises_the_configured_https_address(app, client, seeded):
    """Behind Apache, `wsgi.url_scheme` is http.

    A sitemap built from `request.url_root` therefore advertised http:// on an HTTPS
    site, and every entry in it was a redirect. `APP_URL` is the configured, checked,
    authoritative answer — `flask check-config` refuses anything but https.
    """
    from app.extensions import db
    from app.models import Page
    from app.routes.seo import invalidate_cache

    for page in db.session.execute(db.select(Page)).scalars():
        page.publish()
    db.session.commit()

    app.config["APP_URL"] = "https://acct.alwaysdata.net"
    invalidate_cache()  # the payload is cached for an hour, across tests too

    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "<loc>https://acct.alwaysdata.net" in body
    assert "http://" not in body.replace("http://www.sitemaps.org", "")


# ─────────────────────────────────────────────────────────────────────────────
# `flask backup`
# ─────────────────────────────────────────────────────────────────────────────


def _source_database(path: Path) -> None:
    """A database on disk with one Bangla row, so the round trip proves the encoding."""
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE participants (id INTEGER PRIMARY KEY, name_bn TEXT)")
        connection.execute("INSERT INTO participants (name_bn) VALUES (?)", ("রূপা আক্তার",))
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def backup_environment(app, tmp_path, monkeypatch):
    """A file database, an empty uploads directory and a private backup root."""
    source = tmp_path / "source.db"
    _source_database(source)
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "portrait.jpg").write_bytes(b"\xff\xd8\xff fake jpeg")

    monkeypatch.setitem(app.config, "SQLALCHEMY_DATABASE_URI", f"sqlite:///{source.as_posix()}")
    monkeypatch.setitem(app.config, "BACKUP_ROOT", str(tmp_path / "backups"))
    monkeypatch.setitem(app.config, "UPLOAD_ROOT", str(uploads))
    return tmp_path


def test_a_backup_writes_a_restorable_archive_and_a_row(app, session, runner, backup_environment):
    """The whole claim of the command: an archive that restores, and a record that it
    happened — because a backup nobody can prove was taken is a backup that will be
    re-taken with a hand on the wrong database."""
    result = runner.invoke(args=["backup", "--keep-days", "7"])

    assert result.exit_code == 0, result.output

    rows = list(session.execute(db.select(Backup)).scalars())
    kinds = {row.kind for row in rows}
    assert kinds == {BackupKind.DATABASE, BackupKind.UPLOADS}
    for row in rows:
        assert row.status is BackupStatus.OK
        assert row.size_bytes and row.size_bytes > 0
        assert row.offsite_ok is False, "BACKUP_OFFSITE_CMD is unset, so nothing was sent"
        assert row.expires_at is not None

    database_row = next(row for row in rows if row.kind is BackupKind.DATABASE)
    archives = list((backup_environment / "backups").glob("db-*.sql.gz"))
    assert [archive.name for archive in archives] == [database_row.filename]

    restored = backup_environment / "restored.db"
    with gzip.open(archives[0], "rb") as compressed:
        restored.write_bytes(compressed.read())

    connection = sqlite3.connect(restored)
    try:
        assert connection.execute("SELECT name_bn FROM participants").fetchone() == ("রূপা আক্তার",)
    finally:
        connection.close()

    upload_row = next(row for row in rows if row.kind is BackupKind.UPLOADS)
    with tarfile.open(backup_environment / "backups" / upload_row.filename) as archive:
        # `make_archive` writes members relative to the root directory, with the `./`
        # prefix tar uses for them.
        names = archive.getnames()
        assert any(name.endswith("portrait.jpg") for name in names), names


def test_a_backup_that_cannot_be_taken_is_recorded_as_a_failure(app, session, runner,
                                                                tmp_path, monkeypatch):
    """A cron run that fails in the dark must not look like one that never ran.

    The screen that shows this is /admin/backups, and it can only show it if the
    failure was written down before the command exited — so the row and the non-zero
    exit both happen, in that order.
    """
    monkeypatch.setitem(app.config, "SQLALCHEMY_DATABASE_URI", "sqlite://")  # in memory
    monkeypatch.setitem(app.config, "BACKUP_ROOT", str(tmp_path / "backups"))
    monkeypatch.setitem(app.config, "UPLOAD_ROOT", str(tmp_path / "uploads"))

    result = runner.invoke(args=["backup"])

    assert result.exit_code == 1
    failures = [row for row in session.execute(db.select(Backup)).scalars()
                if row.status is BackupStatus.FAILED]
    assert failures, "a failed backup must leave a row the admin screen can show"
    assert "in memory" in (failures[0].error or "")


def test_the_database_password_never_reaches_the_command_line(tmp_path, monkeypatch):
    """`ps` is world-readable on a shared host.

    The password goes to the dump tool through `MYSQL_PWD` — an environment variable,
    which does not appear in a process list. A backup that leaks the database password
    to every other account on the machine is a worse outcome than no backup.
    """
    import shutil
    import subprocess as subprocess_module

    seen: dict[str, object] = {}

    class _Dump:
        """Enough of a Popen to satisfy the streaming copy."""

        def __init__(self) -> None:
            self.stdout = io.BytesIO(b"-- MariaDB dump\nCREATE TABLE participants (id int);\n")
            self.stderr = io.BytesIO(b"")
            self.returncode = 0

        def wait(self) -> int:
            return self.returncode

    def _fake_popen(command, **kwargs):
        seen["argv"] = command
        seen["env"] = kwargs.get("env")
        return _Dump()

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/mariadb-dump")
    monkeypatch.setattr(subprocess_module, "Popen", _fake_popen)

    destination = tmp_path / "db.sql.gz"
    _dump_mysql(
        "mysql+pymysql://acct:s3cr3t-pw@mysql-acct.alwaysdata.net/acct_sylhet?charset=utf8mb4",
        destination,
    )

    argv = " ".join(str(part) for part in seen["argv"])  # type: ignore[arg-type]
    assert "s3cr3t-pw" not in argv
    assert seen["env"]["MYSQL_PWD"] == "s3cr3t-pw"  # type: ignore[index]

    # Consistent without locking the register, and dumpable without the PROCESS
    # privilege the shared host does not grant.
    assert "--single-transaction" in argv
    assert "--no-tablespaces" in argv
    assert "--default-character-set=utf8mb4" in argv

    with gzip.open(destination, "rb") as compressed:
        assert b"CREATE TABLE participants" in compressed.read()


def test_a_percent_encoded_password_is_decoded_exactly_once(tmp_path, monkeypatch):
    """The documented way to put a `#` or a space in the DSN is `%23` / `%20`.

    That only works if the string is decoded ONCE. `make_url` already decodes it, so a
    second `unquote` would turn a literal `p%2540` into `p@` — a password that is
    right in the file, right in the panel, and rejected by the dump tool with nothing
    in the message to explain why.
    """
    import shutil
    import subprocess as subprocess_module

    seen: dict[str, object] = {}

    class _Dump:
        def __init__(self) -> None:
            self.stdout = io.BytesIO(b"-- dump\n")
            self.stderr = io.BytesIO(b"")
            self.returncode = 0

        def wait(self) -> int:
            return self.returncode

    def _fake_popen(command, **kwargs):
        seen["argv"] = command
        seen["env"] = kwargs.get("env")
        return _Dump()

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/mariadb-dump")
    monkeypatch.setattr(subprocess_module, "Popen", _fake_popen)

    _dump_mysql(
        "mysql+pymysql://acct:p%40ss%20word%231@mysql-acct.alwaysdata.net/db?charset=utf8mb4",
        tmp_path / "db.sql.gz",
    )

    assert seen["env"]["MYSQL_PWD"] == "p@ss word#1"  # type: ignore[index]
    assert "p@ss word#1" not in " ".join(str(p) for p in seen["argv"])  # type: ignore[arg-type]


def test_no_backup_archive_is_left_behind_when_the_dump_fails(tmp_path, monkeypatch):
    """A truncated .sql.gz is worse than none: it restores to a database that looks
    real and is missing its last tables."""
    import shutil
    import subprocess as subprocess_module

    class _FailedDump:
        def __init__(self) -> None:
            self.stdout = io.BytesIO(b"")
            self.stderr = io.BytesIO(b"mysqldump: Got error: 1045: Access denied")
            self.returncode = 2

        def wait(self) -> int:
            return self.returncode

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/mysqldump")
    monkeypatch.setattr(subprocess_module, "Popen", lambda *a, **k: _FailedDump())

    destination = tmp_path / "db.sql.gz"
    with pytest.raises(RuntimeError) as raised:
        _dump_mysql("mysql+pymysql://acct:pw@host/db?charset=utf8mb4", destination)

    assert "Access denied" in str(raised.value)
    assert not destination.exists()
