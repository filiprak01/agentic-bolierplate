"""Console entrypoint with live operator API support."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentic_boilerplate import cli as legacy_cli
from agentic_boilerplate.api.live_local import serve_live_local_api
from agentic_boilerplate.config import load_settings


def main(argv: list[str] | None = None) -> int:
    """Route API serving through the live API and delegate all other CLI commands."""

    args = list(sys.argv[1:] if argv is None else argv)
    env_file, inbox_root, remaining = _split_global_args(args)
    if remaining[:2] == ["api", "serve"]:
        _serve_live_api(env_file=env_file, inbox_root=inbox_root, args=remaining[2:])
        return 0
    return legacy_cli.main(argv)


def _split_global_args(args: list[str]) -> tuple[str, str, list[str]]:
    env_file = ".env"
    inbox_root = ""
    index = 0
    while index < len(args):
        current = args[index]
        if current == "--env-file" and index + 1 < len(args):
            env_file = args[index + 1]
            index += 2
            continue
        if current.startswith("--env-file="):
            env_file = current.split("=", 1)[1]
            index += 1
            continue
        if current == "--inbox-root" and index + 1 < len(args):
            inbox_root = args[index + 1]
            index += 2
            continue
        if current.startswith("--inbox-root="):
            inbox_root = current.split("=", 1)[1]
            index += 1
            continue
        break
    return env_file, inbox_root, args[index:]


def _serve_live_api(*, env_file: str, inbox_root: str, args: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="agentic api serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-root", default="")
    parsed = parser.parse_args(args)

    settings = load_settings(env_file)
    resolved_inbox_root = Path(inbox_root) if inbox_root else settings.paths.po_inbox
    resolved_data_root = Path(parsed.data_root) if parsed.data_root else resolved_inbox_root.parent
    stale_after_seconds = settings.codex_limit_sentinel.stale_after_seconds or None

    serve_live_local_api(
        inbox_root=resolved_inbox_root,
        data_root=resolved_data_root,
        host=parsed.host,
        port=parsed.port,
        codex_live_app_server_command=settings.codex_limit_sentinel.app_server_command,
        codex_live_timeout_seconds=15,
        codex_limit_cutoff_percent=settings.codex_limit_sentinel.guard_cutoff_percent,
        limit_account_scope_id=settings.codex_limit_sentinel.account_scope_id,
        limit_bucket_id=settings.codex_limit_sentinel.bucket_id,
        limit_stale_after_seconds=stale_after_seconds,
        limit_future_tolerance_seconds=settings.codex_limit_sentinel.future_tolerance_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
