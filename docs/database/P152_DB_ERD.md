# ParkSmart AI — Authoritative Database ERD

Source of truth:
- `src/core/db_models.py`
- Alembic revisions through `20260830_0016`

This document describes the schema after Alembic revision `20260830_0016` and
Supabase platform hardening.

## Identity boundary

Supabase Auth owns authentication identities in `auth.users`.
ParkSmart owns authorization and parking-domain identity in `public`.

```mermaid
erDiagram
    AUTH_USERS ||--|| PROFILES : "same UUID; platform FK required"
    PROFILES o|--o| PARKING_USERS : "parking_user_id"
    PROFILES o|--o| VEHICLES : "default_vehicle_id"

    PARKING_USERS ||--o{ VEHICLES : owns
    MAP_NODES o|--o{ PARKING_USERS : current_location

    MAP_NODES ||--o{ PARKING_SLOTS : node
    MAP_NODES ||--o{ MAP_EDGES : from_node
    MAP_NODES ||--o{ MAP_EDGES : to_node

    VEHICLES o|--o{ PARKING_SLOTS : occupied_by

    PARKING_USERS ||--o{ PARKING_RESERVATIONS : creates
    VEHICLES ||--o{ PARKING_RESERVATIONS : reserves_for
    PARKING_SLOTS ||--o{ PARKING_RESERVATIONS : reserves

    PARKING_USERS ||--o{ PARKING_SESSIONS : owns
    VEHICLES ||--o{ PARKING_SESSIONS : parks
    PARKING_SLOTS ||--o{ PARKING_SESSIONS : used_by

    PARKING_SLOTS o|--o{ PARKING_EVENTS : event_for

    PARKING_USERS ||--o{ WRONG_PARKING_REPORTS : reports
    PARKING_SLOTS ||--o{ WRONG_PARKING_REPORTS : reported_slot
    WRONG_PARKING_REPORTS o|--o{ WRONG_PARKING_REPORTS : duplicate_candidate

    PARKING_USERS ||--o{ SLOT_OBSERVATIONS : observes
    PARKING_SESSIONS ||--o{ SLOT_OBSERVATIONS : during_session
    PARKING_SLOTS ||--o{ SLOT_OBSERVATIONS : observed_slot

    PARKING_USERS ||--o{ REWARD_TRANSACTIONS : ledger
    PARKING_USERS ||--o{ REWARD_REDEMPTIONS : redeems
    REWARD_CATALOG_ITEMS ||--o{ REWARD_REDEMPTIONS : selected
    REWARD_REDEMPTIONS ||--|| PARKING_VOUCHERS : issues
    PARKING_USERS ||--o{ PARKING_VOUCHERS : owns
```

## Table inventory

| Table | Responsibility | Primary key | Important foreign keys |
|---|---|---|---|
| `profiles` | App role + bridge from Supabase Auth to parking identity | `id uuid` | `id -> auth.users.id`; `parking_user_id -> parking_users.id`; `default_vehicle_id -> vehicles.id` |
| `parking_users` | Parking-domain user | `id varchar(64)` | `current_node_id -> map_nodes.id` |
| `vehicles` | Vehicles owned by a parking user | `id varchar(64)` | `user_id -> parking_users.id` |
| `map_nodes` | Canonical F1/F2/F3 routing graph nodes | `id varchar(64)` | — |
| `map_edges` | Routing graph edges | `(from_node, to_node)` | both endpoints -> `map_nodes.id` |
| `parking_slots` | Slot inventory + authoritative occupancy state | `id varchar(64)` | `node_id -> map_nodes.id`; `occupied_by_vehicle_id -> vehicles.id` |
| `parking_reservations` | Temporary reservation state | `id varchar(64)` | user, vehicle, slot |
| `parking_sessions` | Active/completed parking sessions | `id varchar(64)` | user, vehicle, slot |
| `parking_events` | Audit/event history | `id varchar(64)` | `slot_id -> parking_slots.id` |
| `wrong_parking_reports` | Wrong-parking report lifecycle | `id varchar(64)` | reporter user, slot |
| `slot_observations` | Pending/verified/rejected/expired adjacent observations | `id varchar(64)` | observer user, parking session, slot |
| `reward_transactions` | Authoritative signed Points ledger | `id varchar(64)` | user; source stored as immutable type/reference |
| `reward_catalog_items` | Operator-managed active reward policy | `id varchar(64)` | â€” |
| `reward_redemptions` | Snapshot of an atomic catalog redemption | `id varchar(64)` | user; catalog item |
| `parking_vouchers` | User-owned issued voucher snapshot | `id varchar(64)` | user; redemption (unique); catalog item; optional parking session |

`location_checkpoints` is historical only. It was created in `0002` and removed by `0003`.

## Important integrity

- `profiles.parking_user_id` is unique and nullable.
- Admin profiles do not require a parking identity.
- Backend validates `default_vehicle_id` belongs to `parking_user_id`.
- Active reservation uniqueness is enforced for user, vehicle and slot by partial unique indexes.
- Active parking-session uniqueness is enforced for user, vehicle and slot by partial unique indexes.
- `parking_slots.version` and `wrong_parking_reports.version` are optimistic-concurrency counters.
- `slot_observations(observer_session_id, slot_id)` is unique.
- `reward_transactions(source_type, source_reference, transaction_type)` is unique and prevents duplicate ledger effects.
- `parking_vouchers.redemption_id` is unique; the nullable `applied_session_id` has a partial unique index for future application work.
- Evidence stores only the private Storage object path/type/size; image bytes are not stored in PostgreSQL.

## Supabase identity constraint

The backend already assumes:

```text
auth.users.id == public.profiles.id
```

Supabase platform hardening enforces:

```text
public.profiles.id
    -> auth.users.id
       ON DELETE CASCADE
```

## Ownership model

```text
Supabase JWT
    |
    v
auth.users.id
    |
    v
profiles.id
    |
    +--> profiles.app_role        -> application authorization
    |
    +--> profiles.parking_user_id -> parking-domain ownership
                                      |
                                      v
                                  vehicles.user_id
```

The frontend must never choose or mutate `app_role`.
The frontend uses Supabase for authentication only; ParkSmart business operations remain authoritative through FastAPI.
