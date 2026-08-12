"""Parking tool adapters are intentionally deferred to their implementation issue.

Tools added here must only call Core services and receive identity/dependencies via
``AgentToolRuntime``; they must never query the ORM directly.
"""

PARKING_TOOLS: tuple[()] = ()
