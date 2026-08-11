"""Backward-compatible database imports.

New code must import database infrastructure from :mod:`src.core.database`.
"""

from src.core.database import (
    check_database_connection,
    get_db_session,
    get_engine,
    get_session_factory,
)

__all__ = [
    "check_database_connection",
    "get_db_session",
    "get_engine",
    "get_session_factory",
]
