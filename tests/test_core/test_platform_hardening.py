from pathlib import Path


def test_daily_usage_tables_are_locked_down_by_platform_hardening_sql() -> None:
    sql_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "database"
        / "P152_SUPABASE_PLATFORM_HARDENING.sql"
    )
    sql = sql_path.read_text(encoding="utf-8").lower()

    assert "alembic revision 20260824_0012 is already applied" in sql
    for table_name in ("agent_daily_usage", "report_daily_usage"):
        assert (
            f"revoke all on table public.{table_name} from anon, authenticated;"
            in sql
        )
        assert f"alter table public.{table_name} enable row level security;" in sql
