import configparser
import tomllib
from pathlib import Path


def test_migration_dependencies_are_declared(project_root: Path) -> None:
    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    dependencies = pyproject["project"]["dependencies"]

    assert "alembic>=1.13" in dependencies
    assert "psycopg[binary]>=3.1" in dependencies


def test_alembic_config_points_to_local_migrations(project_root: Path) -> None:
    parser = configparser.RawConfigParser()
    parser.read(project_root / "alembic.ini", encoding="utf-8")

    assert parser["alembic"]["script_location"] == "%(here)s/migrations"
    assert parser["alembic"]["prepend_sys_path"] == "."
    assert parser["alembic"]["sqlalchemy.url"] == "postgresql://agentic:agentic@localhost:5432/agentic"


def test_alembic_environment_reads_database_url_from_settings(project_root: Path) -> None:
    env_script = (project_root / "migrations" / "env.py").read_text(encoding="utf-8")

    assert "from agentic_boilerplate.config import load_settings" in env_script
    assert "settings.database.url" in env_script
    assert 'configuration["sqlalchemy.url"] = _database_url()' in env_script
    assert "target_metadata = None" in env_script


def test_migration_versions_include_detached_worker_checkpoint_schema(project_root: Path) -> None:
    versions = project_root / "migrations" / "versions"
    migration_files = sorted(path for path in versions.glob("*.py") if path.name != "__init__.py")
    migration_text = (versions / "20260809_0001_detached_worker_checkpoints.py").read_text(encoding="utf-8")

    assert (versions / ".gitkeep").exists()
    assert [path.name for path in migration_files] == ["20260809_0001_detached_worker_checkpoints.py"]
    assert 'op.create_table(' in migration_text
    assert '"detached_worker_checkpoints"' in migration_text
    for column_name in [
        "assignment_id",
        "worker_id",
        "role",
        "project_id",
        "sprint",
        "jira_issue_key",
        "branch_name",
        "worktree_path",
        "stage",
        "last_command",
        "failed_request_path",
        "resume_recommendation",
    ]:
        assert f'"{column_name}"' in migration_text


def test_alembic_revision_template_is_bootstrap_only(project_root: Path) -> None:
    template = (project_root / "migrations" / "script.py.mako").read_text(encoding="utf-8")

    assert "def upgrade() -> None:" in template
    assert "def downgrade() -> None:" in template
    assert "pass" in template
