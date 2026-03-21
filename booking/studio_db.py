
"""
Studio database management utilities.

Each studio has its own SQLite database file named db_studio_<slug>.sqlite3.
The platform (admin) database remains at db.sqlite3 (the 'default' alias).

Usage in views/decorators:
    from .studio_db import activate_studio, deactivate_studio
    activate_studio(studio)   # sets thread-local DB alias
    deactivate_studio()       # clears it after request
"""
import sqlite3
import threading
import sys

from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

_local = threading.local()
_verified_studio_aliases = set()

STUDIO_DB_PREFIX = 'studio_'
_RUNNING_TESTS = 'test' in sys.argv


def slug_to_alias(slug: str) -> str:
    """Return the DB alias for a studio slug, e.g. 'my-studio' → 'studio_my_studio'."""
    return STUDIO_DB_PREFIX + slug.replace('-', '_')


def get_current_studio_alias() -> str | None:
    """Return the active studio DB alias for the current thread, or None."""
    return getattr(_local, 'studio_db_alias', None)


def set_current_studio_alias(alias: str | None) -> None:
    """Set (or clear) the active studio DB alias for the current thread."""
    _local.studio_db_alias = alias


def register_studio_db(slug: str) -> str:
    """
    Ensure a studio's database is registered in settings.DATABASES.
    Safe to call multiple times – a no-op if already registered.
    Returns the DB alias.
    """
    alias = slug_to_alias(slug)
    if alias not in settings.DATABASES:
        db_path = settings.BASE_DIR / f'db_studio_{slug}.sqlite3'
        settings.DATABASES[alias] = {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': db_path,
            # Django 6's configure_settings() is a @cached_property that runs
            # only once (at first access) and fills in default connection keys
            # for all then-registered databases.  New databases added after
            # that point must include the required defaults explicitly or
            # DatabaseWrapper.check_settings() raises a KeyError.
            'ATOMIC_REQUESTS': False,
            'AUTOCOMMIT': True,
            'CONN_MAX_AGE': 0,
            'CONN_HEALTH_CHECKS': False,
            'OPTIONS': {},
            'TIME_ZONE': None,
            'USER': '',
            'PASSWORD': '',
            'HOST': '',
            'PORT': '',
            'TEST': {
                'CHARSET': None,
                'COLLATION': None,
                'MIGRATE': True,
                'MIRROR': None,
                'NAME': None,
            },
        }
    return alias


def _studio_db_has_booking_schema(slug: str) -> bool:
    """Return True when the studio SQLite file already contains booking tables."""
    db_path = settings.BASE_DIR / f'db_studio_{slug}.sqlite3'
    if not db_path.exists() or db_path.stat().st_size == 0:
        return False

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='booking_yogaclass'"
        ).fetchone()
    return row is not None


def ensure_studio_database(slug: str, verbosity: int = 0) -> str:
    """Register the studio DB and ensure booking migrations are applied."""
    alias = register_studio_db(slug)
    if _RUNNING_TESTS or alias in _verified_studio_aliases:
        return alias

    call_command('migrate', 'booking', database=alias, verbosity=verbosity, interactive=False)

    _verified_studio_aliases.add(alias)
    return alias


def register_all_studio_dbs() -> None:
    """Register DB connections for every Studio row in the platform database."""
    from .models import Studio  # late import to avoid circular reference at module load

    for slug in Studio.objects.using('default').values_list('slug', flat=True):
        register_studio_db(slug)


def activate_studio(studio_or_slug) -> str:
    """
    Make *studio_or_slug* the active database for the current thread.
    Accepts a Studio instance or a slug string.
    Returns the DB alias that was activated.
    """
    if _RUNNING_TESTS:
        # Keep tests on the default DB unless a specific test opts into
        # multi-DB behavior explicitly.
        set_current_studio_alias(None)
        return 'default'

    slug = studio_or_slug if isinstance(studio_or_slug, str) else studio_or_slug.slug
    alias = ensure_studio_database(slug)
    set_current_studio_alias(alias)
    return alias


def provision_studio_database(slug: str, verbosity: int = 0) -> str:
    """
    Register and migrate a studio database.

    Returns the registered DB alias.
    """
    alias = ensure_studio_database(slug, verbosity=verbosity)
    return alias


def get_studio_migration_status(slug: str) -> dict:
    """Return booking migration status details for a studio database."""
    alias = register_studio_db(slug)
    connection = connections[alias]
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes('booking')
    plan = executor.migration_plan(targets)
    pending_migrations = [
        migration.name
        for migration, backwards in plan
        if not backwards and migration.app_label == 'booking'
    ]
    return {
        'alias': alias,
        'database_name': str(connection.settings_dict.get('NAME', '')),
        'pending_migrations': pending_migrations,
    }


def deactivate_studio() -> None:
    """Clear the active studio database for the current thread."""
    _local.studio_db_alias = None
