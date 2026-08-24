# ParkSmart AI Deployment Runbook

## Backend Required Environment Variables

```text
APP_ENV=production
DEBUG=false
DEMO_MODE=false
DATABASE_URL=<postgresql+asyncpg production URL>

SUPABASE_URL=<server-side Supabase project URL>
SUPABASE_ANON_KEY=<server-side auth verification public/anon key>
SUPABASE_SERVICE_ROLE_KEY=<SERVER ONLY>
SUPABASE_REPORT_EVIDENCE_BUCKET=wrong-parking-evidence

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

## Frontend Required Build/Runtime Environment

```text
NEXT_PUBLIC_API_BASE_URL=<deployed backend>/api/v1
NEXT_PUBLIC_SUPABASE_URL=<Supabase project URL>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<public browser key>
NEXT_PUBLIC_DEMO_MODE=false
NEXT_PUBLIC_AGENT_ENABLED=true
NEXT_PUBLIC_SPEECH_ENABLED=false
```

`AGENT_ENABLED` and `SPEECH_ENABLED` default to `true`. In production,
`LLM_API_KEY` is required when either backend feature is enabled; the backend may start
without that key only when both flags are `false`. All other production safety validation
remains required. Keep the backend and `NEXT_PUBLIC_` flags aligned. Public environment
variables are frozen into the browser bundle during `next build`, so rebuild the frontend
after changing them.

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
20260824_0011
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

## Health Checks

Liveness:

```text
GET /health
```

Database readiness:

```text
GET /api/v1/health/database
```

Use the database health endpoint as the deployment readiness check when the
platform supports it.

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
