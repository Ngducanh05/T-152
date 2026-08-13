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




##chạy frontend
```bash
cd frontend
npm.cmd run dev
```
1. Khởi động database và backend bằng Docker:
bash
```
  cd D:\learn\2026\VinAI\Project\P-152
  docker compose up -d --build
```
  2. Chạy migration database:
bash
```
  docker compose exec backend alembic upgrade head
```
  3. Seed dữ liệu bản đồ:
bash
```
  docker compose exec backend python -c "import asyncio; from src.core.database import get_session_factory; from src.core.seed import
  seed_if_missing; print(asyncio.run(seed_if_missing(get_session_factory()())))"
```
  4. Kiểm tra backend:
bash
```
  Invoke-RestMethod http://localhost:8000/health
```
  5. Khởi động frontend:
bash
```
  cd frontend
  npm install
  npm run dev
```
  6. Mở giao diện:

  http://localhost:3000 (http://localhost:3000)

  Không cần chạy thêm uvicorn, vì docker compose up đã khởi động backend trên cổng 8000.

  Những lần chạy sau, thông thường chỉ cần:
  bash
```
  docker compose up -d
  npm --prefix frontend run dev
```
  Khi muốn dừng hệ thống:
bash
```
  docker compose down
```
  Và nhấn Ctrl + C trong terminal đang chạy frontend.