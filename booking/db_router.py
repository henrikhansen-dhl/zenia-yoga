"""
Django multi-database router for the yoga-platforms project.

Database layout
---------------
default (db.sqlite3)
    All Django built-in tables (auth, sessions, admin, contenttypes, …)
    Platform booking models: Studio, Feature, StudioFeatureAccess, StudioMembership

studio_<slug>  (db_studio_<slug>.sqlite3)
    Per-studio booking models: YogaClass, Booking, Client, SmsReminderLog
"""
import sys

from .studio_db import STUDIO_DB_PREFIX, get_current_studio_alias

# Models that should always live in the platform/default database.
_PLATFORM_MODELS = frozenset([
    'studio',
    'feature',
    'studiofeatureaccess',
    'studiomembership',
    'studioinvoice',
    'studioinvoiceline',
])
_RUNNING_TESTS = 'test' in sys.argv


class StudioDatabaseRouter:
    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _studio_alias() -> str:
        """Return the active studio DB alias, falling back to 'default'."""
        active_alias = get_current_studio_alias()
        if active_alias:
            return active_alias
        return 'default'

    def _is_platform_booking_model(self, model_name: str | None) -> bool:
        if not model_name:
            return False
        return model_name in _PLATFORM_MODELS

    def _route_booking(self, model_name: str | None) -> str:
        # Route all booking models except explicit platform models to studio DB.
        # This includes auto-created many-to-many through models.
        if self._is_platform_booking_model(model_name):
            return 'default'
        return self._studio_alias()

    # ------------------------------------------------------------------
    # Router interface
    # ------------------------------------------------------------------

    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'booking':
            return self._route_booking(model._meta.model_name)
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'booking':
            return self._route_booking(model._meta.model_name)
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Allow all relations; cross-database FKs use db_constraint=False so
        # referential integrity is enforced at the application layer only.
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == 'default':
            if _RUNNING_TESTS:
                # Keep the historical single-DB test setup unless a test
                # explicitly activates a studio alias.
                return True
            # Booking app platform models migrate on default only.
            if app_label == 'booking':
                return self._is_platform_booking_model(model_name)
            return True

        if db.startswith(STUDIO_DB_PREFIX):
            if _RUNNING_TESTS:
                return False
            # Booking app non-platform models migrate on studio DBs only.
            if app_label == 'booking':
                return not self._is_platform_booking_model(model_name)
            # All non-booking apps (auth, contenttypes, …) are excluded from
            # studio databases.
            return False

        return None
