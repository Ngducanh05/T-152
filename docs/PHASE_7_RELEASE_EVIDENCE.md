# Phase 7 release evidence

## Audit decision

**ORIGINAL AUDIT STOPPED — mandatory gate 4 failed. A working-tree fix is now
verified, but it is not yet merged into `develop`; do not tag yet.**

- Audit timestamp: `2026-08-13T16:38:04.2510035+07:00`
- Time zone: `Asia/Saigon` (`UTC+07:00`)
- Audited branch: `release/mvp-week-1`
- Audited commit: `a85d5cff43440d684b1530e0bc322e622b043ea5`
- `develop` and `origin/develop`: `a85d5cff43440d684b1530e0bc322e622b043ea5`
- Tag recommendation: **NO**. Do not create `mvp-week-1` until the failed
  clean-database migration gate is fixed and the complete audit is rerun.

This report records the first failing mandatory gate and stops subsequent release
execution as required. `NOT RUN` is not a pass.

## Gate evidence

### 1. Working tree is clean — PASS (before evidence report creation)

Command:

```powershell
git status --short --branch
```

Observed result at audit start:

```text
## release/mvp-week-1
```

There were no staged, modified, or untracked paths. Creating this evidence file
changes the working tree after the recorded clean snapshot; it must go through
the normal commit/review process before the audit is rerun.

### 2. All Phase 7 issues are merged into develop — PASS

Commands:

```powershell
git branch --show-current
git rev-parse HEAD
git log --oneline --decorate --graph -30
```

Observed merge evidence on `develop`/`origin/develop`:

```text
a85d5cf Merge pull request #110 ... docs/phase7-release-runbook   (P7-04)
114b16a Merge pull request #108 ... test/phase7-e2e              (P7-03)
719987f Merge pull request #106 ... fix/phase7-reservation-expiry (P7-02)
2120a4e Merge pull request #104 ... feat/phase7-demo-reset        (P7-01)
```

The audited release branch, local `develop`, and `origin/develop` all pointed to
`a85d5cff43440d684b1530e0bc322e622b043ea5`.

### 3. Alembic has one valid head — PASS

Commands:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
uv run alembic heads
uv run alembic history --verbose
```

Observed result:

```text
20260813_0004 (head)
20260813_0004 -> 20260812_0003 -> 20260811_0002 -> 20260804_0001 -> base
```

Exactly one head and one linear revision chain were reported.

### 4. Migrations apply to a clean PostgreSQL database — FAIL

The auditor created a dedicated empty database named
`parksmart_release_audit`, separate from `parksmart` and `parksmart_e2e`, then
ran:

```powershell
$env:DATABASE_URL='<configured PostgreSQL server>/parksmart_release_audit'
$env:UV_CACHE_DIR='.uv-cache'
uv run alembic upgrade head
```

Observable failure:

```text
Running upgrade 20260812_0003 -> 20260813_0004
asyncpg.exceptions.ForeignKeyViolationError:
insert or update on table "map_edges" violates foreign key constraint
"map_edges_from_node_fkey"
DETAIL: Key (from_node)=(F1-A-W) is not present in table "map_nodes".
```

Post-failure verification:

```powershell
uv run alembic current
```

No current revision was printed for the audit database, confirming that the
clean migration sequence did not complete.

- Failing step: clean PostgreSQL `alembic upgrade head`
- Affected component:
  `alembic/versions/20260813_0004_attach_slots_to_nearest_aisle.py`
- Request ID: not applicable; this was an Alembic/database operation, not HTTP
- Cause observed from code and database error: revision `20260813_0004`
  unconditionally bulk-inserts 40 canonical aisle-to-slot edges. A clean schema
  has no seeded `map_nodes` or slot nodes yet, so its foreign keys cannot resolve.
- Smallest recommended fix: make this data migration operate only on canonical
  slot rows that already exist (and only insert an edge when both endpoint nodes
  exist). An empty clean schema must remain a valid no-op; the documented seed
  command should create canonical data after migrations. Preserve upgrade and
  downgrade behavior for an already-seeded database, and add a regression test
  for both empty-schema and seeded-schema upgrade paths.

### 5. Seed succeeds twice without duplicate data — NOT RUN

Blocked by mandatory gate 4. The seed command was not run against the failed
clean migration database.

### 6. Public reset restores documented baseline — NOT RUN

Blocked by mandatory gate 4.

### 7. Backend Ruff and full pytest — NOT RUN

Blocked by mandatory gate 4. Prior checklist results were not substituted for a
fresh release audit run.

### 8. Frontend lint, Vitest and production build — NOT RUN

Blocked by mandatory gate 4.

### 9. Real-stack happy path three consecutive times — NOT RUN

Blocked by mandatory gate 4.

### 10. Stale recommendation error path — NOT RUN

Blocked by mandatory gate 4.

### 11. Agent failure produces no fake slot or route — NOT RUN

Blocked by mandatory gate 4.

### 12. No QR-related behavior exists — NOT RUN

Blocked by mandatory gate 4. No release pass is claimed.

### 13. No secrets or generated test artifacts are tracked — NOT RUN

Blocked by mandatory gate 4. A preliminary tracked-path query returned no
`.env`, `playwright-report`, `test-results`, `node_modules`, `.next`, coverage,
trace, video, or zip paths, but the complete gate was not executed and is not
marked passed.

## Release conclusion

The audited commit is not eligible for tag `mvp-week-1`. The remediation below
must be committed, reviewed, and merged into `develop`, then the audit must start
again from a clean working tree. No tag was created.

## Remediation verification

- Verification timestamp: `2026-08-13T16:46:59.8555545+07:00`
- Base commit: `a85d5cff43440d684b1530e0bc322e622b043ea5`
- Status: working-tree candidate; not committed or merged

The migration now discovers canonical rows already present and rewrites only
attachments whose parking slot, slot node, and aisle node all exist. It is a
no-op on a new empty schema, allowing the documented seed command to run after
migrations. Offline SQL generation skips this optional seed-data rewrite.

### Regression and database verification — PASS

```powershell
uv run ruff check alembic\versions\20260813_0004_attach_slots_to_nearest_aisle.py tests\test_core\test_database_models.py
uv run pytest tests\test_core\test_database_models.py -q
```

Result: `10 passed`; the two new tests verify that an empty canonical dataset
causes no edge update or insert, while a seeded dataset rewrites all 40 edges.

Clean PostgreSQL sequence:

```powershell
$env:DATABASE_URL='<configured PostgreSQL server>/parksmart_release_audit'
uv run alembic upgrade head
uv run alembic current
uv run python scripts\seed_demo.py
uv run python scripts\seed_demo.py
```

Result:

```text
20260813_0004 (head)
Demo seed complete: 154 row(s) created (nodes=54, edges=58, slots=40, users=1, vehicles=1).
Demo seed complete: 0 row(s) created (nodes=0, edges=0, slots=0, users=0, vehicles=0).
```

Seeded upgrade sequence `base -> 20260812_0003 -> seed -> head` also passed:

```text
seeded upgrade verified: slots=40, edges=58, slot_edges=40
```

### Public reset — PASS

Against a temporary FastAPI process connected to `parksmart_release_audit`:

```powershell
$env:PARKSMART_API_BASE_URL='http://127.0.0.1:8200/api/v1'
uv run python scripts\reset_demo.py
```

Result: `40 total, 39 available, 0 reserved, 1 occupied`.

### Backend and frontend regression gates — PASS

```powershell
uv run ruff check src tests scripts alembic
uv run pytest tests\test_core tests\test_api tests\test_agents -q
Set-Location frontend
npm run lint
npm test
npm run build
```

Results:

- Ruff: PASS
- pytest: `247 passed, 1 skipped` (the skip is the optional live-provider eval)
- ESLint: PASS
- Vitest: `23 passed`
- Next.js 16.3 production build: PASS

Four explicit Agent failure tests also passed, confirming no fake slot, route,
session, or stale route is exposed after tool failure.

### Real-stack Playwright — PASS

```powershell
Set-Location frontend
npm run test:e2e
```

Result: `2 passed, 1 optional live-Agent test skipped`. The passing serial test
contains three consecutive happy-path iterations; the stale recommendation
`SLOT_NOT_AVAILABLE` browser path also passed.

### QR, secrets and artifacts — PASS with historical note

- No QR API or current source behavior exists. The only runtime check returned
  HTTP 404 for `/locations/QR`; the Agent prompt test excludes QR.
- `qr_payload` appears only in historical revisions that create then remove the
  old checkpoint table (`20260811_0002` and `20260812_0003`).
- No `.env`, Playwright artifacts, `node_modules`, `.next`, coverage, trace,
  video, or zip artifact is tracked.
- Secret-pattern review found only documented placeholder values such as
  `sk-your-key-here`; no real credential was found.

### Non-release legacy diagnostic

`scripts/test_phase4_e2e.py` is not a documented Phase 7 release gate. Its main
happy path and no-QR case passed, but four legacy assertions expected a seeded
`USER-002` and HTTP 409. Phase 7 intentionally seeds only `USER-001`, so the API
correctly returned `404 USER_NOT_FOUND` (example request ID
`202a2c53-e35d-4134-9e2f-38692599a9f0`). This did not affect the full pytest or
Playwright release suites, but the legacy script should be aligned or retired in
a separate maintenance change.

### Current release decision

The migration defect is fixed and technically verified. The working tree is now
dirty by design (`migration`, regression test, and this evidence report), so the
mandatory clean-tree/merged-commit condition is not satisfied. Commit and review
the fix, merge it into `develop`, then rerun the audit before recommending tag
`mvp-week-1`.
