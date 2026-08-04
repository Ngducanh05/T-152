# ParkSmart AI – Agent Quản lý và Điều phối Gửi xe Thông minh

> Tóm tắt 1 câu: Quá tải hầm gửi xe doanh nghiệp vào giờ cao điểm → AI Agent điều phối, tự động hóa đặt chỗ và xử lý thủ tục đăng ký xe cho Cư dân, Bảo vệ và Ban quản lý tòa nhà.

## Vấn đề (Problem)

Mô tả pain point cụ thể:
- **Ai đang gặp vấn đề?** Cư dân, Khách vãng lai, Lực lượng Bảo vệ và Ban quản lý (BQL) tại các hầm gửi xe của doanh nghiệp bất động sản.
- **Vấn đề tốn bao nhiêu thời gian/tiền?**
  - Cư dân/Khách tốn nhiều thời gian lượn vòng tìm vị trí trống vào giờ cao điểm do không nắm rõ trạng thái chỗ đỗ.
  - BQL mất nhiều thời gian xử lý các thủ tục thủ công như đăng ký xe, đổi thẻ xe và giải quyết các yêu cầu đăng ký vượt định mức căn hộ.
- **Tại sao các giải pháp hiện tại chưa đủ?**
  - Các hệ thống hiện tại cập nhật chậm, không theo thời gian thực.
  - Các thủ tục đăng ký xe và kiểm tra xe khách vẫn phụ thuộc hoàn toàn vào quy trình thủ công.
  - Dễ xảy ra gian lận đăng ký, truy cập trái phép hoặc đăng ký vượt định mức xe nếu không được kiểm soát chặt chẽ.

## Giải pháp (Solution)

Sản phẩm giải quyết vấn đề bằng AI Agent tích hợp LangGraph, RAG và Realtime Simulator:
- **Feature 1 (Điều phối & Đặt chỗ đỗ xe):** Tra cứu vị trí trống gần thời gian thực, tự động tìm/gợi ý tầng, khu vực đỗ và đặt/hủy chỗ đỗ xe thông minh.
- **Feature 2 (Đăng ký phương tiện & Xe khách):** Quản lý xe cư dân và xe khách, hỗ trợ luồng duyệt tự động hoặc luồng duyệt thủ công (Human-in-the-Loop) từ BQL đối với các trường hợp đăng ký xe vượt định mức.
- **Feature 3 (Trợ lý AI & Trợ giúp nội quy - RAG):** Tự động giải đáp thắc mắc về nội quy, chính sách gửi xe, quy trình cấp/mất thẻ bằng RAG mà không làm lộ dữ liệu nhạy cảm.

## Target User

- **Primary:** Cư dân (`resident`) sinh sống tại tòa nhà cần tìm vị trí đỗ, đăng ký xe và đăng ký xe khách.
- **Secondary:** 
  - Nhân viên bảo vệ (`security`) cần đối soát và thực hiện check-in/check-out cho xe khách.
  - Ban quản lý (`admin`) cần phê duyệt các yêu cầu đăng ký xe vượt định mức và quản lý hệ thống.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Agent | LangGraph + GPT-4o-mini (Tool calling, Structured Output, RAG) |
| Backend | FastAPI + Python 3.11 + Pydantic + SQLAlchemy |
| Frontend | Next.js + TypeScript + App Router + Supabase Auth / Realtime |
| Database | PostgreSQL + pgvector (cho RAG knowledge base) |
| DevOps | Docker + Docker Compose + Railway/Vercel + GitHub Actions |

## Quick Start

```bash
# 1. Clone repo
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-152.git
cd P-152

# 2. Setup environment
cp .env.example .env
# Edit .env with your OPENAI_API_KEY, SUPABASE_URL, DATABASE_URL, etc.

# 3. Install dependencies using uv
uv sync --extra dev

# 4. Run development server
uv run uvicorn src.main:app --reload
```

## Project Structure

```
├── src/
│   ├── agents/          # LangGraph agent definitions
│   │   ├── graph.py     # Main graph (nodes + edges)
│   │   ├── state.py     # State schema
│   │   ├── nodes/       # Individual nodes
│   │   └── tools/       # Agent tools
│   ├── api/             # FastAPI routes & dependencies
│   ├── models/          # Pydantic schemas (DTOs)
│   ├── services/        # Business logic, database & rule engine
│   ├── config.py        # Settings (Pydantic Settings)
│   └── main.py          # App entry point
├── tests/               # Test suite (pytest)
│   ├── test_agents/
│   └── test_api/
├── docs/                # Documentation & Guidebooks
├── eval/                # Agent evaluation dataset & scripts
├── scripts/             # AI logging hooks & utilities
├── presentation/        # Demo materials, slides & scripts
├── Dockerfile           # Multi-stage build
├── docker-compose.yml   # Full stack configuration
└── .github/workflows/   # CI/CD pipelines
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check status |
| GET | /api/v1/vehicles | Lấy danh sách phương tiện cá nhân |
| POST | /api/v1/vehicles | Đăng ký xe mới (Tự động chuyển BQL duyệt nếu vượt định mức) |
| GET | /api/v1/parking/areas/{area_id}/availability | Kiểm tra trạng thái chỗ trống bãi xe |
| POST | /api/v1/reservations | Tạo lượt đặt chỗ đỗ xe |
| POST | /api/v1/guest-registrations | Đăng ký thông tin xe khách |
| POST | /api/v1/admin/approval-requests/{id}/approve | Admin duyệt yêu cầu vượt định mức |
| POST | /api/v1/agent/chat | Trò chuyện tương tác trực tiếp với ParkSmart AI Agent |

## Deliverables Checklist

- [x] Source Code (GitHub)
- [x] README.md
- [x] Architecture Diagram (`docs/architecture_diagram.md`)
- [x] AI Logs (auto-collected)
- [ ] Live URL / Deploy
- [ ] Video Demo
- [ ] Pitch Deck (`presentation/`)
- [x] Weekly Journal (`JOURNAL.md`)
- [x] Worklog (`WORKLOG.md`)
- [ ] Evaluation Evidence (`eval/results/`)

## Team

| Member | Role | Student ID |
|--------|------|-----------|
| Trần Anh Quân | Leader (Architecture, Integration, CI/CD) | 2A202601997 |
| Nguyễn Ngọc Đoàn | Backend & Database (Auth, Business Logic, Rule Engine) | 2A202601593 |
| Trần Quang Thành | Frontend Lead (Next.js, UI/UX, Map 2D, Realtime) | 2A202601133 |
| Chu Phú Thành | AI Agent Lead (LangGraph, Agent Tools, RAG, Eval) | 2A202601289 |

## License

MIT