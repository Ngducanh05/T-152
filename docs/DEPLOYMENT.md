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
```

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
20260824_0010
```

Run migrations once as a pre-deploy or release step. Do not run migrations
independently from every horizontally scaled application worker.

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
8. Create a wrong-parking report with a real JPG.
9. Confirm the DB stores `evidence_storage_path`.
10. Confirm the object exists in the private bucket.
11. Log in as admin.
12. Open the report.
13. Request a signed evidence URL.
14. Confirm the image renders.
15. Confirm a regular user cannot call the admin evidence endpoint.
16. Hard-delete the report.
17. Confirm the DB row is gone.
18. Confirm the Storage object is gone.

Do not mark the real smoke flow as passed unless it was executed against the
deployed backend and real Supabase project.
