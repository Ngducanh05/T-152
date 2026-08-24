# ParkSmart AI — Supabase Database Rollout

## Decision

```text
Browser -> Supabase Auth
Browser -> FastAPI -> SQLAlchemy/asyncpg -> Supabase PostgreSQL
```

The browser does not query ParkSmart business tables through Supabase Data API.

## Migration ownership

- Alembic is authoritative for `public.*` ParkSmart business schema.
- Supabase platform hardening owns only:
  - `public.profiles.id -> auth.users.id`
  - RLS enablement
  - Data API grant lockdown

Do not duplicate the ParkSmart business schema into `supabase/migrations`.

## Phase A — Local Supabase stack

From repository root:

```powershell
npx supabase --version
npx supabase init
npx supabase start
npx supabase status
```

Typical local defaults:

```text
API URL:    http://127.0.0.1:54321
DB URL:     postgresql://postgres:postgres@127.0.0.1:54322/postgres
Studio URL: http://127.0.0.1:54323
```

Use the actual values printed by `supabase status`.

Backend local `.env`:

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=<key from supabase status>
DEMO_MODE=false
```

Frontend local `.env.local`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable key from supabase status>
NEXT_PUBLIC_DEMO_MODE=false
```

## Phase B — Replay authoritative schema

```powershell
uv run alembic upgrade head
uv run alembic current
```

Expected head:

```text
20260824_0010
```

Confirm these tables exist in Studio:

```text
profiles
map_nodes
parking_users
vehicles
map_edges
parking_slots
parking_reservations
parking_sessions
parking_events
wrong_parking_reports
slot_observations
reward_transactions
```

`location_checkpoints` must not exist.

## Phase C — Apply Supabase platform hardening

Apply `P152_SUPABASE_PLATFORM_HARDENING.sql` after Alembic.

```powershell
psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" `
  -f .\docs\database\P152_SUPABASE_PLATFORM_HARDENING.sql
```

Verify profile identity FK:

```sql
select conname, pg_get_constraintdef(oid)
from pg_constraint
where conrelid = 'public.profiles'::regclass
order by conname;
```

Verify RLS:

```sql
select schemaname, tablename, rowsecurity
from pg_tables
where schemaname = 'public'
  and tablename in (
    'profiles',
    'parking_users',
    'vehicles',
    'map_nodes',
    'map_edges',
    'parking_slots',
    'parking_reservations',
    'parking_sessions',
    'parking_events',
    'wrong_parking_reports',
    'slot_observations',
    'reward_transactions'
  )
order by tablename;
```

Every listed table must have `rowsecurity = true`.

## Phase D — Seed business data

```powershell
uv run python scripts\seed_demo.py
uv run python scripts\seed_demo.py
```

The second run must be idempotent.

Seed owns:

```text
canonical F1/F2/F3 map (161 nodes, 177 edges)
120 parking slots (40 on each floor)
USER-001
VEHICLE-001
```

Do not store passwords in ParkSmart tables.

Verify the multi-floor seed before sharing the environment:

```sql
select floor_id, count(*)
from public.parking_slots
group by floor_id
order by floor_id;
```

Expected result is `F1=40`, `F2=40`, `F3=40`. The repeated seed command must keep these
counts unchanged.

## Phase E — Create development Auth identities

Use Supabase Studio Authentication > Users.

Create:

```text
user@example.com
admin@example.com
```

Use development-only passwords.

## Phase F — Link Auth users to ParkSmart profiles

User:

```sql
insert into public.profiles (
    id,
    email,
    full_name,
    app_role,
    parking_user_id,
    default_vehicle_id
)
select
    id,
    email,
    'ParkSmart Test User',
    'user'::app_role_enum,
    'USER-001',
    'VEHICLE-001'
from auth.users
where email = 'user@example.com'
on conflict (id) do update
set
    email = excluded.email,
    full_name = excluded.full_name,
    app_role = excluded.app_role,
    parking_user_id = excluded.parking_user_id,
    default_vehicle_id = excluded.default_vehicle_id;
```

Admin:

```sql
insert into public.profiles (
    id,
    email,
    full_name,
    app_role,
    parking_user_id,
    default_vehicle_id
)
select
    id,
    email,
    'ParkSmart Test Admin',
    'admin'::app_role_enum,
    null,
    null
from auth.users
where email = 'admin@example.com'
on conflict (id) do update
set
    email = excluded.email,
    full_name = excluded.full_name,
    app_role = excluded.app_role,
    parking_user_id = null,
    default_vehicle_id = null;
```

## Phase G — Verify identity bridge

```sql
select
    p.id,
    p.email,
    p.app_role,
    p.parking_user_id,
    p.default_vehicle_id,
    au.id as auth_user_id
from public.profiles p
join auth.users au on au.id = p.id
order by p.email;
```

Expected:

```text
admin@example.com -> admin -> no parking identity
user@example.com  -> user  -> USER-001 / VEHICLE-001
```

## Phase H — Verify backend before frontend

Start FastAPI:

```powershell
uv run uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/docs
```

Prove manually before Playwright:

1. Supabase password login returns a session.
2. `GET /api/v1/auth/me` with bearer token returns `200`.
3. User profile returns `role=user`, `USER-001`, `VEHICLE-001`.
4. Admin returns `role=admin` without parking identity.
5. User cannot call admin-only APIs.
6. Cross-user parking operations are rejected.

## Phase I — Remote P-152 project

Create a dedicated Supabase project for P-152. Do not reuse P-092.

Then:

1. Obtain project URL and publishable key.
2. Obtain DB connection string.
3. Apply Alembic through `20260824_0010`.
4. Apply the same platform hardening SQL.
5. Seed intended dev/staging business data.
6. Create Auth users.
7. Link profiles.
8. Run Supabase security/performance advisors.
9. Test Swagger against the remote project.

## Safety

Until remote P-152 passes verification:

- keep current local PostgreSQL data intact;
- do not delete the Docker volume;
- do not modify P-092;
- do not make remote Supabase the only copy of business data.
