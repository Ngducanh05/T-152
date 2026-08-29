# Hướng dẫn cài đặt dependency

Dự án **ParkSmart AI** yêu cầu:

- Python `>=3.11,<3.13` (nên sử dụng Python 3.11 hoặc 3.12).
- Các dependency chính được khai báo trong `pyproject.toml`.
- Nhóm dependency phục vụ phát triển (`dev`) gồm `pytest`, `pytest-asyncio`,
  `pytest-cov` và `ruff`.

Thực hiện các lệnh dưới đây tại thư mục gốc của dự án, nơi chứa file
`pyproject.toml`.

## Phương án 1: Sử dụng uv (khuyến nghị)

### 1. Cài uv

Nếu máy chưa có `uv`, cài đặt bằng một trong các cách sau:

```powershell
# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Mở lại terminal nếu lệnh `uv` chưa được nhận diện, sau đó kiểm tra:

```bash
uv --version
```

### 2. Cài dependency

Dự án đã có `uv.lock`. Để tạo môi trường ảo `.venv` và cài đúng các phiên bản
đã được khóa, bao gồm dependency phát triển, chạy:

```bash
uv sync --extra dev
```

Nếu chỉ cần dependency để chạy ứng dụng, không cần công cụ phát triển:

```bash
uv sync
```

Không bắt buộc phải kích hoạt môi trường ảo khi dùng `uv`; có thể chạy lệnh
trong môi trường dự án bằng `uv run`, ví dụ:

```bash
uv run pytest
uv run ruff check .
```

Nếu muốn kích hoạt môi trường ảo theo cách truyền thống:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux/macOS
source .venv/bin/activate
```

## Phương án 2: Sử dụng pip

### 1. Kiểm tra phiên bản Python

```bash
python --version
```

Kết quả phải là Python 3.11.x hoặc 3.12.x. Trên một số hệ thống, cần thay
`python` bằng `python3` hoặc `py -3.11` trong các lệnh bên dưới.

### 2. Tạo và kích hoạt môi trường ảo

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Nâng cấp công cụ đóng gói

```bash
python -m pip install --upgrade pip setuptools wheel
```

### 4. Cài dependency

Cài dự án cùng toàn bộ dependency phát triển:

```bash
python -m pip install -e ".[dev]"
```

Nếu chỉ cần dependency để chạy ứng dụng:

```bash
python -m pip install -e .
```

Tùy chọn `-e` cài dự án ở chế độ editable, vì vậy thay đổi trong mã nguồn được
áp dụng ngay mà không cần cài lại package.

> **Lưu ý:** Nên cài trực tiếp từ `pyproject.toml` bằng các lệnh trên. Không nên
> dùng `pip install -r requirements.txt`, vì file `requirements.txt` hiện không
> đồng bộ hoàn toàn với dependency và giới hạn phiên bản trong `pyproject.toml`.

## Kiểm tra cài đặt

Sau khi cài xong, chạy:

```bash
python --version
python -c "import fastapi, langgraph, sqlalchemy; print('Dependencies installed successfully')"
```

Nếu đã cài nhóm `dev`, có thể kiểm tra thêm:

```bash
pytest --version
ruff --version
```

Để thoát khỏi môi trường ảo đã kích hoạt:

```bash
deactivate
```

## Chạy frontend với Docker Compose

1. Khởi động database và backend:

   ```powershell
   Set-Location D:\learn\2026\VinAI\Project\P-152
   docker compose up -d --build
   ```

1. Chạy migration database:

   ```powershell
   docker compose exec backend alembic upgrade head
   ```

1. Seed dữ liệu bản đồ:

   ```powershell
   docker compose exec backend python -c "import asyncio; from src.core.database import get_session_factory; from src.core.seed import seed_if_missing; print(asyncio.run(seed_if_missing(get_session_factory()())))"
   ```

1. Kiểm tra backend:

   ```powershell
   Invoke-RestMethod http://localhost:8000/health
   ```

1. Khởi động frontend:

   ```powershell
   npm --prefix frontend install
   npm --prefix frontend run dev
   ```

1. Mở [giao diện local](http://localhost:3000).

Không cần chạy thêm Uvicorn vì Docker Compose đã khởi động backend trên cổng 8000. Những
lần chạy sau thường chỉ cần:

```powershell
docker compose up -d
npm --prefix frontend run dev
```

Khi muốn dừng hệ thống, chạy `docker compose down` và nhấn Ctrl+C trong terminal frontend.

Các lệnh phát triển hữu ích khác:

```powershell
uv run python scripts/reset_demo.py
uv run uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
npx vercel deploy --prod --logs
```

## Chạy lại Agent benchmark

Contract và cách diễn giải evidence nằm tại
[`docs/BENCHMARKING.md`](docs/BENCHMARKING.md). Trước tiên chạy scorer và artifact tests;
lệnh này không gọi LLM provider:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://parksmart:parksmart@localhost:5432/parksmart_test"
uv run pytest tests/test_agents/test_golden_eval.py -q
```

Live LLM benchmark chỉ chạy khi có explicit opt-in. Nếu thiếu một trong hai biến
`RUN_LIVE_LLM_EVAL=1` hoặc `LLM_API_KEY`, pytest sẽ skip và không gọi provider:

```powershell
$env:RUN_LIVE_LLM_EVAL = "1"
$env:GOLDEN_LIVE_REPETITIONS = "3"
$env:LLM_API_KEY = "<key>"
uv run pytest tests/test_agents/test_golden_live.py -m live_llm -q
uv run python scripts/run_golden_eval.py
```

`GOLDEN_LIVE_REPETITIONS` nhận giá trị từ `1` đến `20`, mặc định `1`. Mọi lần chạy thật
đều có archive JSON trong `eval/results/runs/`. Run thiếu case/repetition vẫn được archive
với trạng thái partial nhưng không cập nhật `eval/results/golden_eval_raw.json`; chỉ canonical
complete mới được dùng để sinh `eval/results/golden_eval_report.md`.

Benchmark này chạy LangGraph/model với fake tools tất định. Nó không gọi FastAPI/database,
không phải full-system E2E và không được công bố như full-system accuracy. Correctness của
mutation được chấm bằng tool contract tất định, không dùng LLM-as-judge.
