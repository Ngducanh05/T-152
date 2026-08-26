import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE_PATH = REPOSITORY_ROOT / "Dockerfile"
DOCKERIGNORE_PATH = REPOSITORY_ROOT / ".dockerignore"
DEPLOYMENT_PATH = REPOSITORY_ROOT / "docs" / "DEPLOYMENT.md"


def _meaningful_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_dockerfile_uses_frozen_uv_builder_and_minimal_runtime() -> None:
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    normalized = dockerfile.lower()

    assert "copy . ." not in normalized
    assert "add . ." not in normalized
    assert re.search(r"(?im)^from\s+\S+\s+as\s+builder\s*$", dockerfile)
    assert re.search(r"(?im)^from\s+\S+\s+as\s+runtime\s*$", dockerfile)
    assert "COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /usr/local/bin/uv" in dockerfile
    assert "COPY pyproject.toml uv.lock ./" in dockerfile
    assert "COPY src ./src" in dockerfile
    assert "uv sync --frozen --no-dev --no-editable --no-cache" in dockerfile
    assert "pip install" not in normalized
    assert "pip wheel" not in normalized

    runtime = normalized.split("from python:3.11-slim as runtime", maxsplit=1)[1]
    assert "copy --from=builder /opt/venv /opt/venv" in runtime
    assert "copy src" not in runtime
    assert "copy pyproject.toml" not in runtime
    assert "uv.lock" not in runtime
    assert "/usr/local/bin/uv" not in runtime


def test_dockerfile_runs_non_root_and_uses_render_port_contract() -> None:
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    user_instructions = re.findall(r"(?im)^USER\s+(.+)$", dockerfile)

    assert user_instructions
    assert user_instructions[-1].strip().lower() not in {"root", "0", "0:0"}
    assert "src.main:app" in dockerfile
    assert "--host 0.0.0.0" in dockerfile
    assert "--port ${PORT:-8000}" in dockerfile
    assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile
    assert "PYTHONUNBUFFERED=1" in dockerfile
    assert "alembic upgrade" not in dockerfile.lower()
    assert "healthcheck" not in dockerfile.lower()


def test_dockerignore_is_a_strict_backend_build_context_allowlist() -> None:
    patterns = _meaningful_lines(DOCKERIGNORE_PATH)
    allowed_negations = {
        "!Dockerfile",
        "!.dockerignore",
        "!pyproject.toml",
        "!uv.lock",
        "!src/",
        "!src/**",
    }

    assert patterns[0] == "**"
    assert {pattern for pattern in patterns if pattern.startswith("!")} == allowed_negations
    generated_file_exclusions = {
        "**/.env*",
        "**/__pycache__/",
        "**/.cache/",
        "**/*.pyc",
        "**/*.pyo",
        "**/*.log",
        "**/*.bak",
        "**/*.backup",
        "**/*~",
    }
    assert generated_file_exclusions <= set(patterns)
    assert all(patterns.index(pattern) > patterns.index("!src/**") for pattern in generated_file_exclusions)

    forbidden_context_roots = {
        ".env",
        ".git",
        ".github",
        ".agents",
        ".codex",
        ".claude",
        ".cursor",
        ".gemini",
        ".ai-log",
        "tests",
        "frontend",
        "docs",
        "scripts",
        "alembic",
    }
    assert all(
        not any(pattern.removeprefix("!").startswith(root) for root in forbidden_context_roots)
        for pattern in allowed_negations
    )


def test_render_runbook_uses_database_readiness_health_check() -> None:
    deployment = DEPLOYMENT_PATH.read_text(encoding="utf-8")
    private_image_runbook = deployment.split("## Private Backend Image: Local Build to Render", maxsplit=1)[1].split(
        "## Frontend Required Build/Runtime Environment", maxsplit=1
    )[0]

    assert "Health Check Path" in private_image_runbook
    assert "/api/v1/health/database" in private_image_runbook
    assert "/health` is only the process liveness endpoint" in private_image_runbook
