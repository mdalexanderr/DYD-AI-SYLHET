"""Flask extension instances — created here, bound in the app factory.

plan.md §9.1 ("db, migrate, login_manager, csrf, bcrypt, limiter, cache, mail").

WHY THE INSTANCES LIVE IN THEIR OWN MODULE
    Models import ``db``; the app factory imports the models. If ``db`` were
    defined in ``app/__init__.py`` that would be a circular import, and the usual
    workaround — importing inside a function — hides real dependency cycles
    instead of removing them.

    Keeping them unbound also means one process can build two applications with
    different configs, which is what the test suite does on every run.
"""

from __future__ import annotations

import logging

from flask import Flask
from flask_bcrypt import Bcrypt
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """The declarative base, named explicitly rather than reached through db.Model.

    Flask-SQLAlchemy creates a declarative base implicitly behind ``db.Model``, but
    ``db.Model`` is a dynamically generated attribute: mypy cannot resolve it as a
    base class and reported ``Name "db.Model" is not defined`` for all 17 models.
    The alternatives were to silence a rule for the whole models package — hiding
    real name errors alongside it — or to name the base. Naming it is the SQLAlchemy
    2.0 pattern, types correctly, and costs four lines.

    Every model subclasses this instead of ``db.Model``. ``db`` still owns the
    engine, the session and ``db.metadata``, which is what migrations read.
    """

    pass


db = SQLAlchemy(model_class=Base)
# render_as_batch=True: SQLite has no ALTER COLUMN and no DROP CONSTRAINT, so
# without it every future migration that changes a column fails on the SQLite dev
# database with "SQLite does not support ALTER" — and the failure appears at the
# moment a developer is trying to migrate, not when the code was written. Alembic
# instead rebuilds the table (create new → copy → drop → rename). It is a no-op on
# MySQL, so production is unaffected.
#
# compare_type=True: autogenerate does not detect column TYPE changes by default,
# so a widened VARCHAR or a changed ENUM would be silently absent from the
# generated migration — a schema drift that only shows up in production.
migrate = Migrate(compare_type=True, render_as_batch=True)
login_manager = LoginManager()
csrf = CSRFProtect()
bcrypt = Bcrypt()
cache = Cache()
mail = Mail()

# Limits are declared explicitly per route (§12): 3 logins per 10 minutes, 3
# contact posts per hour, and a rate limit on the participant filter to blunt
# enumeration. RATELIMIT_DEFAULT is a backstop, not the design.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    headers_enabled=True,
)

# ── Flask-Login configuration (§12.1) ────────────────────────────────────────
# There is exactly ONE kind of user. There is no `login` view to redirect to by
# default, so an unauthenticated admin request must not be sent to a guessable
# path — it 404s instead, which is the same thing /admin does.
login_manager.login_view = None
login_manager.session_protection = "strong"
login_manager.login_message = None


def init_extensions(app: Flask) -> None:
    """Bind every extension to the app, in dependency order."""
    db.init_app(app)
    migrate.init_app(app, db, directory=str(app.config["BASE_DIR"] / "migrations"))
    login_manager.init_app(app)
    csrf.init_app(app)
    bcrypt.init_app(app)
    cache.init_app(app)
    mail.init_app(app)

    # Limiter reads its storage and default limits from config, but only if they
    # are set before init_app. Assigned here rather than in the factory so the
    # extension owns its own configuration surface.
    app.config.setdefault("RATELIMIT_STORAGE_URI", "memory://")
    app.config.setdefault("RATELIMIT_HEADERS_ENABLED", True)
    limiter.init_app(app)

    # Flask-Login stores the id as a string in the session.
    @login_manager.user_loader
    def load_admin(admin_id: str):
        from app.models.admin import AdminUser

        if not str(admin_id).isdigit():
            return None
        return db.session.get(AdminUser, int(admin_id))

    logging.getLogger("app").debug("extensions bound to %s", app.config["APP_ENV"])
