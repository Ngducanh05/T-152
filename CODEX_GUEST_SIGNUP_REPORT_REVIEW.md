# P-152 Codex Task — Guest Preview, Signup/Onboarding, Vehicle Gate, Report Evidence & Admin Review

Work in the current P-152 repo/branch. **Do not commit or push. Do not discard existing changes.**
Goal: implement the requirements below by extending the current architecture, not replacing it.

## 0) Read/compare first

Before editing, inspect current code and git diff. Start with these files, then search only as needed:

- `src/services/auth_service.py`
- `src/api/dependencies.py`
- `src/api/routes/auth.py`
- `src/api/routes/reports.py`
- `src/api/routes/admin.py`
- `src/core/db_models.py`
- `src/core/parking_report.py`
- `src/models/auth.py`
- `src/models/schemas.py`
- latest Alembic revisions, especially `20260819_0006*`, `20260819_0007*`
- `frontend/app/page.tsx`, `frontend/app/login/page.tsx`
- `frontend/components/auth/*`
- `frontend/components/reports/WrongParkingReportDialog.tsx`
- `frontend/components/admin/AdminDashboard.tsx`
- `frontend/components/admin/ReportDetailDrawer.tsx`
- `frontend/lib/api.ts`, `auth.ts`, `types.ts`, `report-updates.ts`
- related backend/frontend tests.

Preserve these boundaries:

- Supabase Auth owns password/session/JWT.
- FastAPI owns authorization, onboarding, ownership and business rules.
- PostgreSQL/Alembic owns ParkSmart business schema.
- Frontend never chooses `role`, `parking_user_id`, owner IDs, or admin privilege.
- Business tables stay behind FastAPI; do not make browser query them directly.
- Keep existing report create/admin lifecycle, optimistic versioning, polling and auth guards unless a requirement below explicitly extends them.
- Do not create a second auth system, large refactor, or unrelated architecture.

## 1) Public guest preview + progressive auth

Change `/` from full-route auth wall to a **public preview**.

Guest behavior:
- Guest can open `/` and see a static/preview version of the current user UI.
- Preview must not call authenticated/business APIs or expose authoritative live parking data.
- Guest may view UI/intro only.
- Any ParkSmart business action must trigger an auth gate: e.g. find parking, find vehicle, location, report, send chat, voice, reserve, personalized route.
- Pure UI actions such as close/open informational UI do not require auth.
- Keep `/login` usable for direct navigation. Add registration UX (`/register` or login/register tabs/modal) with the smallest clean change.
- Authenticated admin still routes to `/admin`.

**Preserve user intent across the auth gate.**
At minimum support pending intents for:
- find parking
- find vehicle
- confirm/select location
- open wrong-parking report
- send chat text

After login/register succeeds, resume the intended action instead of forcing the user to click it again. Do not persist sensitive content unnecessarily.

## 2) Public user registration + ParkSmart onboarding

Registration fields:
- full/display name
- email
- password
- confirm password

Rules:
- Use Supabase `signUp`; ParkSmart never stores passwords.
- No role selector. Self-registration always becomes `user`.
- Never expose/use service-role key in frontend.
- Correctly handle both Supabase outcomes: immediate session OR email-confirmation-required. Never bypass Supabase verification.
- A newly authenticated Supabase user without a ParkSmart profile must be provisionable safely instead of ending in permanent `PROFILE_NOT_FOUND`.

Add an authenticated, idempotent onboarding capability (route name may follow repo conventions; `/api/v1/auth/onboarding` is preferred):

1. verify bearer token directly with Supabase;
2. get trusted Auth UUID/email;
3. if profile already exists, return existing identity and **never alter its role**;
4. otherwise, in one DB transaction:
   - generate a collision-safe server-side `ParkingUser` ID (do not use `MAX()+1`);
   - create `ParkingUser`;
   - create `Profile` with same Auth UUID, `app_role=user`, linked `parking_user_id`, and `default_vehicle_id=NULL`;
5. retrying onboarding must not create duplicates.

Important:
- Do not implement onboarding by calling `get_current_user()` first, because that currently requires the profile to exist.
- It is acceptable for the auth/session flow to detect only `PROFILE_NOT_FOUND`, call onboarding once, then retry `/auth/me`.
- Never auto-rewrite an existing profile or elevate a manually created Auth user.
- Keep admin profiles valid without ParkingUser/Vehicle.

## 3) Vehicle registration after login, not during signup

A user may enter the authenticated app with:

`Profile + ParkingUser + default_vehicle_id=NULL`.

Do **not** force vehicle creation during signup or immediately after login.

Add only the minimum “add first vehicle” capability/UI needed now:
- plate number
- `requires_charging` / EV choice

Backend:
- derive owner from JWT -> Profile -> `parking_user_id`; frontend must not choose/send owner `user_id`;
- generate collision-safe vehicle ID server-side;
- create the vehicle under the authenticated ParkingUser;
- if this is the user's first/default vehicle, set `profiles.default_vehicle_id`;
- return/refetch current identity after success;
- validate duplicate/invalid input using current DB constraints/conventions.

UX:
- authenticated user without vehicle can still use capabilities that do not need a vehicle (general chat, report, location, etc.);
- vehicle-required actions (reserve, confirm parking, find my vehicle, session actions) open a vehicle gate instead of failing obscurely;
- after first vehicle is added, resume the pending vehicle-required intent when practical;
- do not build full multi-vehicle management in this task.

## 4) Wrong-parking report: one image evidence

Extend the existing report system; do not create a second subsystem.

Current “standard reason submits immediately” UX must change to an explicit submit flow:

`slot -> reason -> capture/select image -> optional plate/description -> Submit`.

Requirements:
- one image per new report for this scope;
- mobile-friendly camera/file input (`image/*`, camera capture where supported);
- validate type and configurable size limit;
- do not store image bytes/base64 in PostgreSQL;
- store image in a **private Supabase Storage bucket**;
- backend controls upload/access (backend upload or backend-issued signed mechanism); no public bucket and no arbitrary client-chosen storage path;
- add only minimal report metadata, e.g. storage path, content type, size;
- legacy rows may have no image; new UI/API-created reports should require evidence;
- admin can securely view the evidence (short-lived signed URL or protected backend response);
- hard-delete of a report must also clean its stored image; avoid obvious orphan/half-created states and perform best-effort cleanup on cross-system failure;
- do not log image bytes, signed URLs, tokens, password, observed plate, description or other sensitive report text.

In authenticated mode, derive reporter from JWT/parking identity. Keep demo/test compatibility only where needed; do not trust arbitrary client `user_id`.

## 5) Admin review state: verify report correctness

Keep existing operational lifecycle:

- `status = OPEN | RESOLVED`

Add a separate review dimension:

- `review_status = PENDING | CONFIRMED | REJECTED`
- also store minimal audit fields: `reviewed_at`, `reviewed_by`, optional `review_note`.

Do not collapse review and operational status into one enum.

Expected semantics:
- new report: `OPEN + PENDING`;
- confirm: `CONFIRMED`, report remains operationally `OPEN`;
- reject: `REJECTED` and close it from actionable/open operational alerts (prefer resolving it atomically while preserving separate review metadata);
- keep existing resolve/reopen/version-concurrency behavior as intact as possible;
- define safe behavior for reopen of a rejected report (reset review to `PENDING` if needed) and cover it with tests.

Admin report detail must show:
- image
- slot
- reason
- observed plate
- description
- reporter
- created time
- review status
- operational status
- review/resolve actions

Add explicit admin actions:
- Confirm report
- Reject report
- existing Resolve/Reopen remain distinct.

All admin review mutations remain backend role-protected and version-safe.

## 6) Admin “new report” notification UX — reuse current mechanism

Do **not** add a notification database, WebSocket, Firebase, email, or Supabase Realtime in this task.

Reuse current authoritative polling/refetch + existing browser report-update signal.

Add lightweight UX:
- detect newly observed report IDs while admin dashboard is open;
- show badge/toast such as “New report at …”;
- click it to open the relevant report/slot detail;
- avoid notifying repeatedly for the same report in the same page session;
- backend polling/refetch remains source of truth; BroadcastChannel is only an optimization.

## 7) Schema/migrations/security

Use Alembic for public business schema changes.

Likely changes include:
- report evidence metadata;
- report review enum/fields;
- indexes/constraints needed by the new query/state flow.

Keep current identity constraints:
- `profiles.id == auth.users.id`;
- `profiles.parking_user_id` unique;
- admin may have null parking identity;
- `default_vehicle_id` must belong to the linked ParkingUser.

If Supabase Storage bucket/platform setup cannot be represented safely in Alembic, add a minimal documented/bootstrap step. Do not weaken existing RLS/grant hardening or expose business tables to browser roles.

## 8) Tests / acceptance

Update old tests only when the product requirement intentionally changed; do not paper over regressions.

Required coverage:

### Guest/auth
- guest `/` sees preview and triggers no business-data fetch;
- protected preview action opens auth gate;
- pending intent resumes after login/register;
- invalid login/register errors are safe;
- direct `/login` still works;
- admin still routes to `/admin`;
- self-registration cannot choose admin role.

### Onboarding
- new verified Supabase identity -> Profile + ParkingUser, no vehicle;
- onboarding retry is idempotent;
- existing profile role is never changed;
- profile-missing login can onboard safely;
- no password/token logs.

### Vehicle
- authenticated no-vehicle user is valid;
- first vehicle creation derives owner from backend identity;
- first vehicle becomes default;
- cross-user/forged ownership is impossible;
- vehicle-required UX gates and can resume.

### Report/evidence/review
- new report requires valid image in new flow;
- storage path is backend-controlled/private;
- user A cannot report as user B;
- admin can view evidence;
- non-admin cannot access admin evidence/review APIs;
- create => `OPEN + PENDING`;
- confirm => `OPEN + CONFIRMED`;
- reject => non-actionable/closed + `REJECTED`;
- version conflicts remain stable;
- reopen behavior is tested;
- hard-delete removes DB report and evidence;
- sensitive report/image/auth data is absent from logs;
- admin new-report badge/toast does not duplicate endlessly.

### Gates
Run targeted tests first. Do not run `npm ci` unless dependencies changed.

Then run:
```powershell
# backend: isolate tests from local .env
$env:DEMO_MODE="true"
$env:SIMULATOR_ENABLED="true"
uv run ruff check src tests scripts
uv run pytest tests\test_core tests\test_api tests\test_agents -q
Remove-Item Env:DEMO_MODE -ErrorAction SilentlyContinue
Remove-Item Env:SIMULATOR_ENABLED -ErrorAction SilentlyContinue

cd frontend
npm run lint
npm test
npm run build
```

Run/update relevant Playwright auth/release E2E if present and practical. Do not waste time debugging the known unrelated Next dev/HMR issue if production build is green.

## 9) Scope exclusions

Do not add:
- social login, MFA, forgot-password
- admin self-signup or role picker
- full multi-vehicle CRUD
- public live parking APIs
- multi-image/video evidence
- notification DB, push/email, WebSocket, Supabase Realtime business reads
- unrelated refactors or multi-floor/QR changes.

## 10) Execution + final report

Do not stop at audit. Implement, migrate, test, and fix failures caused by this work.

Before finishing:
- `git diff --check`
- inspect `git status` / diff for secrets, generated artifacts, debug logs, accidental scope creep.

Final response must be concise:
1. `Implemented`
2. `Schema/API changes`
3. `Tests/gates` with pass/fail counts
4. `Remaining blockers` (only real blockers)
5. `Files changed`

Do not commit or push.
