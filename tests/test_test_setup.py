from importlib.metadata import version
from pathlib import Path

import agentic_boilerplate

from agentic_boilerplate.config import require_valid_settings, settings_from_mapping


def test_test_setup_imports_package_and_uses_local_fixtures(
    project_root: Path,
    src_root: Path,
    minimal_required_env: dict[str, str],
) -> None:
    assert agentic_boilerplate.__version__ == version("agentic-boilerplate")
    assert (project_root / "pyproject.toml").exists()
    assert (src_root / "agentic_boilerplate").exists()

    settings = settings_from_mapping(minimal_required_env)

    require_valid_settings(settings)
    assert settings.github.token == "test-github-token"
