"""Backward-compatible settings imports.

New code should import Settings and get_settings from src.core.config.
"""

from src.core.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
