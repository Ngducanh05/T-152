"""Backward-compatible ORM model imports.

The canonical declarative base and models live in :mod:`src.core.db_models`.
"""

from src.core.db_models import (
    AppRoleEnum,
    Base,
    MapEdge,
    MapNode,
    ParkingEvent,
    ParkingReservation,
    ParkingSession,
    ParkingSlot,
    ParkingUser,
    Profile,
    Vehicle,
)

__all__ = [
    "AppRoleEnum",
    "Base",
    "MapEdge",
    "MapNode",
    "ParkingEvent",
    "ParkingReservation",
    "ParkingSession",
    "ParkingSlot",
    "ParkingUser",
    "Profile",
    "Vehicle",
]
