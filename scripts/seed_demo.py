"""Idempotently add missing canonical ParkSmart demo data."""

from __future__ import annotations

import asyncio

from src.core.database import get_engine, get_session_factory
from src.core.seed import seed_if_missing


async def seed_demo() -> None:
    """Run the Core seed in its configured async SQLAlchemy session."""
    try:
        async with get_session_factory()() as session:
            result = await seed_if_missing(session)
    finally:
        await get_engine().dispose()

    print(
        "Demo seed complete: "
        f"{result.rows_created} row(s) created "
        f"(nodes={result.nodes_created}, edges={result.edges_created}, "
        f"slots={result.slots_created}, users={result.users_created}, "
        f"vehicles={result.vehicles_created})."
    )


def main() -> int:
    asyncio.run(seed_demo())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
