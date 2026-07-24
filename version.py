"""Single source of truth for the application version.

Bump APP_VERSION here for every release and add a matching entry in ``changelog.py``.
The version shown in the UI is forced from this constant (not from settings.json), so an
old saved settings file can never pin a stale version number.
"""

APP_VERSION = "1.010"
