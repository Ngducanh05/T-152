# ParkSmart AI Deployment Runbook

## Backend Required Environment Variables

```text
APP_ENV=production
DEBUG=false
DEMO_MODE=false
SIMULATOR_ENABLED=false
DATABASE_URL=<postgresql+asyncpg production URL>

SUPABASE_URL=<server-side Supabase project URL>
SUPABASE_ANON_KEY=<server-side auth verification public/anon key>
SUPABASE_SERVICE_ROLE_KEY=<SERVER ONLY>
SUPABASE_REPORT_EVIDENCE_BUCKET=wrong-parking-evidence
REPORT_EVIDENCE_MAX_BYTES=5000000
WRONG_PARKING_REPORT_DAILY_LIMIT=5

LLM_API_KEY=<server only>
LLM_MODEL=<configured model>
AGENT_ENABLED=true
AGENT_DAILY_REQUEST_LIMIT=5
AGENT_MAX_STEPS=4
SPEECH_ENABLED=false

CORS_ORIGINS=<actual deployed frontend origin>

PORT=<provided by platform, optional locally because fallback is 8000>
```

`SUPABASE_SERVICE_ROLE_KEY` must never be exposed to frontend code and must never
be configured as a `NEXT_PUBLIC_` variable.

## Private Backend Image: Local Build to Render

Use this path when Render cannot use the GitHub Organization App: build the backend
locally, push it to a **private** Docker Hub repository, then configure a Render Web
Service with **Existing Image**. The repository must remain private because installed
Python packages can still be extracted from a container image even when repository files
are excluded from its filesystem.

Build and inspect the exact Linux platform locally before publishing:

```bash
docker buildx build --platform linux/amd64 --load \
  -t parksmart-ai-api:local-verify .
docker image inspect parksmart-ai-api:local-verify \
  --format '{{.Os}}/{{.Architecture}}'
```

Create an immutable release tag from the Git commit. Never use `latest` for production:

```bash
export IMAGE_REPOSITORY="<docker-hub-namespace>/<private-repository>"
export IMAGE_TAG="$(git rev-parse --short=12 HEAD)"
export IMAGE_REF="${IMAGE_REPOSITORY}:${IMAGE_TAG}"

docker buildx build --platform linux/amd64 --load -t "${IMAGE_REF}" .
docker push "${IMAGE_REF}"
```

Do not put a Docker Hub username, token, or real image reference in the repository. Use a
Docker Hub access token limited to read-only access for Render's private registry
credential. Keep push credentials only in the operator's local credential store; Render
does not need write access.

In Render:

1. Create or update a Web Service using **Existing Image** and the immutable
   `<docker-hub-namespace>/<private-repository>:<short-git-sha>` reference.
2. Attach the read-only private registry credential.
3. Configure backend environment variables in Render; do not bake secrets,
   `DATABASE_URL`, or `PORT` into the image.
4. Set Render's **Health Check Path** to `/api/v1/health/database`. This database
   readiness endpoint must succeed before Render treats the deployment as healthy.
   The image command binds `0.0.0.0` and reads Render's `PORT` automatically.
5. Run Alembic through the controlled release step, never in the image `CMD`.

`/health` is only the process liveness endpoint and is appropriate for a local container
smoke test. It does not prove that the deployed service can reach its database. Use
`/api/v1/health/database` for deployment readiness and as the Render Health Check Path.

An image-backed Render service does not auto-deploy from Git. For every release, build and
push a new short-SHA tag, update the service to that immutable image reference, then use
**Manual Deploy** / **Deploy latest reference** as appropriate. Record the deployed tag so
rollback selects a known immutable image rather than rebuilding source.

## Frontend Required Build/Runtime Environment

```text
NEXT_PUBLIC_API_BASE_URL=<deployed backend>/api/v1
NEXT_PUBLIC_SUPABASE_URL=<Supabase project URL>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<public browser key>
NEXT_PUBLIC_DEMO_MODE=false
NEXT_PUBLIC_AGENT_ENABLED=true
NEXT_PUBLIC_SPEECH_ENABLED=false
NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL=<real monitored email>
```

`AGENT_ENABLED` and `SPEECH_ENABLED` default to `true`. In production,
`LLM_API_KEY` is required when either backend feature is enabled; the backend may start
without that key only when both flags are `false`. All other production safety validation
remains required. Keep the backend and `NEXT_PUBLIC_` flags aligned. Public environment
variables are frozen into the browser bundle during `next build`, so rebuild the frontend
after changing them.

`NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL` is also a Next.js build-time variable. A real,
monitored contact email is a release blocker before opening the public beta. After changing
it, rebuild and redeploy the frontend. Before launch, open `/privacy`, verify that the
`mailto:` link targets the monitored inbox, and send a test deletion request. Complete an
admin hard-delete smoke test as well: confirm that it removes both the database report row
and its private Storage object.

## Production Admin RBAC Release Gate

Use [ADMIN_PROVISIONING.md](ADMIN_PROVISIONING.md) for public beta production admin
promotion and emergency revoke. It supplements, and does not replace, the existing
development/demo runbook.

Do not release until all checks pass:

- The dedicated admin account has a confirmed Supabase email.
- Its `profiles.app_role` is `admin`.
- Its `profiles.parking_user_id` and `profiles.default_vehicle_id` are null.
- `GET /api/v1/auth/me` returns the backend-owned admin profile without a parking identity.
- A regular user calling representative admin APIs receives `403 ADMIN_REQUIRED`.
- An anonymous request to an admin API receives `401 AUTH_REQUIRED`.
- Production has `DEMO_MODE=false`.
- Production has `SIMULATOR_ENABLED=false`.

Never provision a production admin through frontend metadata, an anon key, browser console,
or by enabling demo/simulator behavior.

If using the existing Next.js rewrite:

```text
PARKSMART_BACKEND_ORIGIN=<backend origin>
```

## Migration Release Step

Before switching traffic to a new backend revision:

```text
alembic upgrade head
alembic current
alembic heads
```

Expected target:

```text
20260824_0012
```

Run migrations once as a pre-deploy or release step. Do not run migrations
independently from every horizontally scaled application worker.

Seed the canonical map after the first migration of a new environment (the command is
idempotent and may safely be repeated):

```text
uv run python scripts/seed_demo.py
```

Verify that `parking_slots` contains 40 rows for each of F1, F2 and F3 (120 total), and
that `map_nodes` contains 55/53/53 rows respectively. A database with only 40 F1 slots is
not ready for the multi-floor UI.

## Backend Test Database Safety

Never run `pytest` while `DATABASE_URL` points to production, Supabase Direct, a
Supabase pooler, or any other remote database. The root pytest configuration validates the
effective `DATABASE_URL` before importing the application or collecting database fixtures.
It only accepts loopback hosts and the repository's Docker Compose database service; there
is no bypass flag.

Start and verify the repository PostgreSQL service before running backend tests:

```bash
docker compose up -d database
docker compose exec database pg_isready -U parksmart -d parksmart
export DATABASE_URL="postgresql+asyncpg://parksmart:parksmart@127.0.0.1:5432/parksmart"
uv run pytest -q
unset DATABASE_URL
```

Do not proceed unless `pg_isready` reports that the local service accepts connections.
Keep the explicit local override only in the same Git Bash terminal that runs pytest, and
always unset it immediately after the test command. The safety guard's failure message
intentionally does not print the configured URL, credentials, query string, or remote
project identifier.

## Daily Quota Data API Hardening Verification

After Alembic `20260824_0012`, apply the Supabase-specific
`docs/database/P152_SUPABASE_PLATFORM_HARDENING.sql` through the controlled platform
procedure. Do not encode Supabase roles in an Alembic migration.

Verify RLS is enabled for both quota tables:

```sql
select
    c.relname as table_name,
    c.relrowsecurity as rls_enabled
from pg_class as c
join pg_namespace as n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in ('agent_daily_usage', 'report_daily_usage')
order by c.relname;
```

Expected: exactly two rows and `rls_enabled=true` for both. Verify neither Data API role
has table privileges, including privileges inherited through other grants:

```sql
with targets(table_name) as (
    values ('agent_daily_usage'), ('report_daily_usage')
), data_api_roles(role_name) as (
    values ('anon'), ('authenticated')
)
select
    targets.table_name,
    data_api_roles.role_name,
    has_table_privilege(
        data_api_roles.role_name,
        format('public.%I', targets.table_name),
        'SELECT'
    ) as can_select,
    has_table_privilege(
        data_api_roles.role_name,
        format('public.%I', targets.table_name),
        'INSERT'
    ) as can_insert,
    has_table_privilege(
        data_api_roles.role_name,
        format('public.%I', targets.table_name),
        'UPDATE'
    ) as can_update,
    has_table_privilege(
        data_api_roles.role_name,
        format('public.%I', targets.table_name),
        'DELETE'
    ) as can_delete
from targets
cross join data_api_roles
order by targets.table_name, data_api_roles.role_name;
```

Expected: all four privilege columns are `false` for all four table/role combinations.

Before public beta, list leaked pytest schemas in production:

```sql
select schema_name
from information_schema.schemata
where left(schema_name, 5) = 'test_'
order by schema_name;
```

Production must return zero `test_*` schemas before release. Treat any result as a release
blocker and clean it up through a separately reviewed production operation; never use a
pytest run or this runbook verification step to delete production schemas automatically.

## Health Checks

Process liveness and local container smoke test only:

```text
GET /health
```

Database readiness:

```text
GET /api/v1/health/database
```

Use the database health endpoint as the deployment readiness check and configure it as
Render's Health Check Path. Do not substitute the liveness endpoint for this release gate.

When the frontend opens, `BackendReadinessGate` calls
`GET /api/v1/health/database` before mounting `AuthProvider` or any application
route. It shows the Render free-instance cold-start notice after about three
seconds, retries failed checks sequentially, and gives the user a manual retry
action after a readiness deadline of about 75 seconds. Each attempt has a
10-second timeout, followed by a four-second retry delay; requests never overlap.
After readiness succeeds, the gate stops checking and renders the application.

This is a startup readiness gate, not a keep-alive mechanism. Do not add periodic
pings after the application becomes ready. Keeping `AuthProvider` behind the gate
also prevents session initialization and `/auth/me` calls from treating a backend
cold start as an authentication failure.

## Supabase Storage Checklist

- Bucket name: `wrong-parking-evidence`
- Bucket must be private.
- Frontend must not have the service role key.
- Backend creates signed URLs for admin evidence access.
- User report upload is backend controlled.
- Admin evidence URL endpoint remains admin protected.

## Real Post-Deploy Smoke Flow

1. Register a regular user.
2. Confirm email if Supabase email confirmation is enabled.
3. Log in.
4. Confirm the first user has no vehicle.
5. Trigger a vehicle-required action.
6. Add first vehicle.
7. Confirm the original action resumes exactly once.
8. Open the wrong-parking dialog and choose a reason; confirm this selection alone does not
   send an API request.
9. Optionally enter a plate/description and attach a real JPG, then press the explicit send
   button.
10. Confirm the DB stores `evidence_storage_path` and the report reward is `PENDING` when
    eligible.
11. Confirm the object exists in the private bucket.
12. Open a second normal browser tab and log in as admin; confirm the first user tab remains
    a user session. Do not use “Duplicate tab” for this check because browsers may clone
    initial `sessionStorage`.
13. In admin, switch through F1/F2/F3 in both flat and isometric views and confirm all 40
    slots render on every floor.
14. Open the report from its warning slot, request a signed evidence URL and confirm the
    image renders.
15. Confirm the slot detail panel can be closed and its map selection highlight clears.
16. Resolve the report with an explicit verification outcome and confirm the user reward
    summary refreshes without a full page reload.
17. Confirm a regular user cannot call the admin evidence endpoint.
18. Hard-delete a separate pending report.
19. Confirm the DB row and its Storage object are gone while its reward ledger reference is
    retained and contains no plate, description or image data.

Do not mark the real smoke flow as passed unless it was executed against the
deployed backend and real Supabase project.
# Current schema head

This feature requires Alembic revision `20260831_0017`. Coordinate the schema migration and application release; this documentation does not indicate that a production migration has run.
