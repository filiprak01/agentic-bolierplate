"""PO inbox path ownership checks and external item import helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_boilerplate.domain.po_inbox import POInboxItem, inbox_item_from_dict


MISPLACED_PO_INBOX_RELATIVE_PATHS: tuple[Path, ...] = (
    Path("data/po-inbox"),
    Path(".agentic/po-inbox"),
    Path("po-inbox"),
)


@dataclass(frozen=True)
class POInboxPathGuardResult:
    """Result of validating platform-owned PO inbox storage boundaries."""

    platform_inbox_root: Path
    target_project_root: Path
    misplaced_paths: tuple[Path, ...] = ()
    platform_inbox_inside_target: bool = False

    @property
    def passed(self) -> bool:
        return not self.misplaced_paths and not self.platform_inbox_inside_target

    @property
    def messages(self) -> tuple[str, ...]:
        messages: list[str] = []
        if self.platform_inbox_inside_target:
            messages.append("Configured platform PO inbox path resolves inside TARGET_PROJECT_PATH.")
        for path in self.misplaced_paths:
            messages.append(f"Target project contains misplaced PO inbox path: {path}")
        if not messages:
            messages.append("PO inbox paths keep platform durable state out of the target project.")
        return tuple(messages)


def validate_po_inbox_paths(
    *,
    platform_inbox_root: Path | str,
    target_project_root: Path | str,
    misplaced_relative_paths: tuple[Path, ...] = MISPLACED_PO_INBOX_RELATIVE_PATHS,
) -> POInboxPathGuardResult:
    """Detect target-project PO inbox writes before agents start work."""

    platform_root = Path(platform_inbox_root).expanduser().resolve()
    target_root = Path(target_project_root).expanduser().resolve()
    misplaced = tuple(
        path
        for path in (target_root / relative_path for relative_path in misplaced_relative_paths)
        if path.exists()
    )
    return POInboxPathGuardResult(
        platform_inbox_root=platform_root,
        target_project_root=target_root,
        misplaced_paths=misplaced,
        platform_inbox_inside_target=_is_relative_to(platform_root, target_root),
    )


def load_external_po_inbox_item(path: Path | str) -> POInboxItem:
    """Load and normalize an external PO inbox item through the schema."""

    source = Path(path)
    with source.open("r", encoding="utf-8-sig") as file:
        data: Any = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("External PO inbox import must be a JSON object.")
    return inbox_item_from_dict(data)


def format_po_inbox_path_guard_result(result: POInboxPathGuardResult) -> str:
    """Format guard output without including secrets or item content."""

    lines = ["PO inbox path validation:"]
    marker = "PASS" if result.passed else "FAIL"
    lines.append(f"- [{marker}] platform_inbox_boundary: {' '.join(result.messages)}")
    return "\n".join(lines)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
