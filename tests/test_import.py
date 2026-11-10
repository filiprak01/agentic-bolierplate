from importlib.metadata import version

import agentic_boilerplate


def test_package_imports() -> None:
    assert agentic_boilerplate.__version__ == version("agentic-boilerplate")
