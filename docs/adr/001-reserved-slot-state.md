# ADR 001: Temporary RESERVED slot state and reservation rules

## Status

Accepted

## Context

ParkSmart AI needs a short-lived hold between recommending an available parking slot and confirming that the user's vehicle has parked there. Without this state, another user or the Simulator could take the recommended slot while the first user is travelling to it.

This hold must remain an MVP coordination mechanism. It is not a remote booking product, a long-term reservation, or a payment commitment. Parking State Service remains the source of truth for slot status.

## Decision

ParkSmart AI will represent the temporary hold with `RESERVED`. A reservation is created only after the user explicitly accepts a recommendation. Producing or displaying a recommendation does not reserve a slot.

Every slot or reservation state transition implemented after this ADR must create a `ParkingEvent` recording the transition and its actor or source. Recommendation must exclude `RESERVED` slots, and the Simulator must never occupy a `RESERVED` slot.

## Slot states

- `AVAILABLE`: the slot is empty and may be recommended or reserved.
- `RESERVED`: the slot is held temporarily for the user, vehicle, and active reservation that resulted from accepting a recommendation.
- `OCCUPIED`: a vehicle is physically confirmed as parked in the slot.

`SlotStatus` contains exactly `AVAILABLE`, `RESERVED`, and `OCCUPIED` for the MVP.

## Reservation states

- `ACTIVE`: the temporary hold exists and has not been confirmed, cancelled, or expired.
- `CONFIRMED`: the matching user or vehicle has confirmed parking before expiry.
- `EXPIRED`: the TTL elapsed before parking was confirmed.
- `CANCELLED`: the active hold was explicitly cancelled before parking was confirmed.

`CONFIRMED`, `EXPIRED`, and `CANCELLED` are terminal reservation states.

## Valid transitions

### Slot transitions

- `AVAILABLE -> RESERVED`: the user explicitly accepts a recommendation, and an `ACTIVE` reservation is created atomically with the slot update.
- `AVAILABLE -> OCCUPIED`: a simulated or physical vehicle without a reservation parks in an available slot.
- `RESERVED -> OCCUPIED`: the user or vehicle that owns the matching, unexpired `ACTIVE` reservation confirms parking; the reservation becomes `CONFIRMED` in the same transaction.
- `RESERVED -> AVAILABLE`: the owning `ACTIVE` reservation is cancelled or expires; the reservation becomes `CANCELLED` or `EXPIRED` in the same transaction.
- `OCCUPIED -> AVAILABLE`: the occupying vehicle leaves the slot.

### Reservation transitions

- A reservation is created in `ACTIVE` only as part of `AVAILABLE -> RESERVED` after the user accepts a recommendation.
- `ACTIVE -> CONFIRMED`: the owner confirms parking before `expires_at`.
- `ACTIVE -> EXPIRED`: the TTL elapses while the reservation is still active.
- `ACTIVE -> CANCELLED`: the owner cancels the reservation while it is still active.

## Invalid transitions

The following transitions or actions must be rejected:

- `OCCUPIED -> RESERVED`.
- `RESERVED -> RESERVED`, including replacing an existing reservation with another one.
- `AVAILABLE -> AVAILABLE` as a business state-transition event.
- Direct `RESERVED -> OCCUPIED` by the Simulator.
- Parking confirmation by a user, vehicle, or reservation reference that does not own the reservation.
- Reserving an `OCCUPIED` or `RESERVED` slot.
- Recommending a `RESERVED` slot.
- Any transition from terminal reservation states `CONFIRMED`, `EXPIRED`, or `CANCELLED`.

## TTL

The default reservation TTL is 300 seconds. It is configurable with `RESERVATION_TTL_SECONDS`.

An `ACTIVE` reservation records an `expires_at` value derived from the configured TTL. When the TTL elapses, expiry must atomically change the reservation to `EXPIRED` and change the slot from `RESERVED` to `AVAILABLE`, but only if that reservation still owns the slot. Expiry must also be checked when the reservation or slot is read or mutated; a periodic cleanup job may be added later but must not be the only expiry mechanism.

## Concurrency

Reservation and slot transitions must run in a PostgreSQL transaction. A mutating operation must lock the target slot row with `SELECT FOR UPDATE`, then re-read and validate the slot status, reservation ownership, and expiry before applying the transition.

When concurrent transactions try to reserve the same `AVAILABLE` slot, the row lock serializes them. Only the first valid transaction may create the `ACTIVE` reservation and change the slot to `RESERVED`; later transactions must observe the new state and fail with a conflict. The reservation update, slot update, and corresponding `ParkingEvent` records must commit or roll back together.

## Consequences

- A recommendation is advisory until the user explicitly accepts it.
- Users receive a bounded period to travel to a selected slot without that slot being recommended to another user or taken by the Simulator.
- Recommendation queries must consider only `AVAILABLE` slots.
- Parking State Service must enforce ownership, expiry, transition validation, locking, and event creation.
- Reservation, slot, and event writes require transactional boundaries and may wait briefly on a concurrent row lock.
- Expired or cancelled reservations release capacity for later recommendations.
- Every state change is auditable through `ParkingEvent`.

## Out of scope

- Remote or advance booking for a later date or time.
- Payment, pricing, billing, tickets, or guaranteed commercial booking.
- Implementing SQLAlchemy parking models, migrations, seed data, services, APIs, Simulator behavior, Recommendation logic, or background expiry jobs in this ADR.
- Parking Session behavior beyond identifying the valid `RESERVED -> OCCUPIED` boundary.
- QR, voice, LangGraph Agent, routing algorithms, frontend work, or changes to existing auth/template code.
