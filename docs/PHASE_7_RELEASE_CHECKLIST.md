# Phase 7 release checklist

Điền checklist này trên đúng commit chuẩn bị phát hành. Không ghi API key,
database password, prompt, tool payload hoặc dữ liệu nội bộ vào bằng chứng.

## Release identity

- [ ] Commit SHA: `git rev-parse HEAD` → `_______________________________`
- [ ] Working tree sạch: `git status --short` không có output.
- [x] Migration head: `uv run alembic heads` → `20260813_0004 (head)`.

Evidence P7-04 được chạy trên working tree dựa trên commit
`114b16a1c8d5ec03ad503148985ac989b1776868`. Điền SHA release mới và xác nhận
working tree sạch sau khi commit; không dùng SHA nền này thay cho release SHA.

## Environment versions

Chạy từ PowerShell và ghi output:

```powershell
python --version
uv --version
docker --version
docker compose version
node --version
npm --version
uv run python -c "import fastapi, sqlalchemy; print('FastAPI', fastapi.__version__); print('SQLAlchemy', sqlalchemy.__version__)"
Set-Location frontend
npm exec next -- --version
npm exec playwright -- --version
Set-Location ..
```

- [x] Python: `3.11.15`
- [x] uv: `0.11.31`
- [x] Docker/Compose/PostgreSQL image: `29.6.2` / `5.3.1` / `pgvector/pgvector:pg16`
- [x] Node.js/npm: `24.19.0` / `11.17.0`
- [x] FastAPI/SQLAlchemy: `0.139.2` / `2.0.51`
- [x] Next.js/React/Playwright: `16.3.0` / `19.2.8` / `1.62.1`

## Seed and quality gates

- [x] Migration upgrade: `uv run alembic upgrade head` — PASS
- [x] Seed run 1: `uv run python scripts\seed_demo.py` — PASS
- [x] Seed run 2 reports zero rows created — PASS
- [x] Backend Ruff: `uv run ruff check src tests scripts` — PASS
- [x] Backend tests: `uv run pytest tests\test_core tests\test_api tests\test_agents -q` — PASS (`245 passed, 1 skipped`)
- [x] Frontend lint: `npm run lint` — PASS
- [x] Frontend Vitest: `npm test` — PASS (`23 passed`)
- [x] Frontend production build: `npm run build` — PASS

## Real-stack Playwright

Run `npm run test:e2e` from `frontend`. Mỗi happy-path iteration bắt đầu bằng
public Reset Demo và dùng candidate thực tế do UI trả về.

- [x] E2E happy path run 1 — PASS
- [x] E2E happy path run 2 — PASS
- [x] E2E happy path run 3 — PASS
- [x] Error path (`SLOT_NOT_AVAILABLE`, refresh và chọn ô khác) — PASS
- [x] Optional live Agent (`RUN_LIVE_AGENT_E2E=1`) — PASS (`1 passed`)

## Observability spot check

- [x] Gửi một request lỗi với UUID trong `X-Request-ID`.
- [x] Response error và response header chứa cùng `request_id`.
- [x] Theo dõi cùng ID qua `request_failed`/`request_completed`,
      `agent_chat_*` và `agent_tool_completed` khi Agent tool được gọi.
- [x] Log không chứa secret, raw prompt, raw tool payload hay internal reasoning.
- [x] Frontend hiển thị lời Việt, `ApiError.code` và `request_id`.

## Known limitations

- Agent hội thoại cần provider LLM và có thể có độ trễ/biến thiên về câu chữ;
  tool/state transition vẫn được kiểm tra deterministic.
- Agent thread dùng in-memory checkpointer nên không tồn tại qua restart backend.
- Demo chỉ có bản đồ canonical tầng F1 và danh tính demo cố định.
- Simulator và Reset Demo chỉ dùng khi `DEMO_MODE=true` và
  `SIMULATOR_ENABLED=true`.
- Không có QR, Voice, WebSocket, deployment automation hoặc simulator dashboard.
