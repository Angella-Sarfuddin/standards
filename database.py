"""Compatibility alias for the relocated SQLAlchemy database module."""

import importlib
import sys


_database_module = importlib.import_module("app.db.database")
sys.modules[__name__] = _database_module
