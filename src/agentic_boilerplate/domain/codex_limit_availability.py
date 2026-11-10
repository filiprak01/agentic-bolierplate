"""Durable Codex limit availability state for pause and resume workflows."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

DEFAULT_SHORT_WINDOW_STOP_THRESHOLD_PERCENT = 10
DEFAULT_BROAD_QUOTA_DOWNGRADE_THRESHOLD_PERCENT = 10
DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID = "default"
_SAFE_ACCOUNT_SCOPE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


class CodexLimitWindowStatus(str, Enum):
    """Availability state for one Codex quota window."""

    AVAILABLE = "available"
    LIMITED = "limited"
    UNKNOWN = "unknown"


class CodexLimitObservationSource(str, Enum):
    """How one Codex limit observation was captured."""

    OPERATOR = "operator"
    CODEX_CLI = "codex_cli"
    CODEX_APP_SERVER = "codex_app_server"
    OFFLINE_FIXTURE = "offline_fixture"
    PARSED_SESSION_OUTPUT = "parsed_session_output"
    EXPLICIT_FAILURE = "explicit_failure"
    BROWSER_CHECK = "browser_check"
    UNKNOWN = "unknown"


class CodexLimitPlanMode(str, Enum):
    """How visible Codex quota windows should be interpreted."""

    DUAL_WINDOW = "dual_window"
    SINGLE_POOL = "single_pool"
    DYNAMIC = "dynamic"


class CodexLimitRecommendedAction(str, Enum):
    """Recommended next action for the scheduler."""

    RESUME = "resume"
    WAIT = "wait"
    DOWNGRADE_MODEL = "downgrade_model"
    ASK_PRODUCT_OWNER = "ask_product_owner"


@dataclass(frozen=True)
class CodexLimitWindowAvailability:
    """One short or broad Codex quota observation."""

    status: CodexLimitWindowStatus
    remaining_percent: int | None
    reset_at: str
    observation_source: CodexLimitObservationSource
    observed_at: str
    window_id: str = ""
    label: str = ""
    authoritative: bool = True
    bucket_id: str = ""
    window_name: str = ""
    window_duration_minutes: int | None = None


@dataclass(frozen=True)
class CodexLimitAvailabilityRecord:
    """Durable Codex quota snapshot used by the scheduler."""

    id: str
    short_window: CodexLimitWindowAvailability
    broad_quota: CodexLimitWindowAvailability
    recommended_action: CodexLimitRecommendedAction
    note: str = ""
    plan_mode: CodexLimitPlanMode = CodexLimitPlanMode.DUAL_WINDOW
    windows: tuple[CodexLimitWindowAvailability, ...] = ()
    account_scope_id: str = DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID


@dataclass(frozen=True)
class CodexLimitAvailabilityIssue:
    """Validation issue for availability records."""

    field: str
    message: str


@dataclass(frozen=True)
class CodexLimitGateDecision:
    """Pre-request decision used before a worker spends Codex quota."""

    allowed: bool
    action: CodexLimitRecommendedAction
    reason: str
    resume_after: str = ""


class CodexLimitAvailabilityError(ValueError):
    """Raised when a limit availability record violates the contract."""

    def __init__(self, issues: list[CodexLimitAvailabilityIssue]) -> None:
        self.issues = issues
        super().__init__(format_codex_limit_availability_issues(issues))


def recommend_codex_limit_action(
    *,
    short_window: CodexLimitWindowAvailability,
    broad_quota: CodexLimitWindowAvailability,
    plan_mode: CodexLimitPlanMode | str = CodexLimitPlanMode.DUAL_WINDOW,
    windows: Sequence[CodexLimitWindowAvailability] | None = None,
    short_window_stop_threshold_percent: int = DEFAULT_SHORT_WINDOW_STOP_THRESHOLD_PERCENT,
    broad_quota_downgrade_threshold_percent: int = DEFAULT_BROAD_QUOTA_DOWNGRADE_THRESHOLD_PERCENT,
) -> CodexLimitRecommendedAction:
    """Choose the safest next scheduler action from visible quota windows."""

    mode = _coerce_plan_mode(plan_mode)
    if mode is CodexLimitPlanMode.SINGLE_POOL:
        pool = _primary_authoritative_window(windows, fallback=short_window)
        return _recommend_single_pool_action(
            pool,
            stop_threshold_percent=short_window_stop_threshold_percent,
        )
    if mode is CodexLimitPlanMode.DYNAMIC:
        return _recommend_dynamic_action(
            tuple(windows or (short_window, broad_quota)),
            stop_threshold_percent=short_window_stop_threshold_percent,
        )
    statuses = {short_window.status, broad_quota.status}
    if CodexLimitWindowStatus.UNKNOWN in statuses:
        return CodexLimitRecommendedAction.ASK_PRODUCT_OWNER
    if short_window.status == CodexLimitWindowStatus.LIMITED and broad_quota.status == CodexLimitWindowStatus.AVAILABLE:
        return CodexLimitRecommendedAction.WAIT
    if _remaining_at_or_below(short_window, short_window_stop_threshold_percent):
        return CodexLimitRecommendedAction.WAIT
    if short_window.status == CodexLimitWindowStatus.AVAILABLE and broad_quota.status == CodexLimitWindowStatus.LIMITED:
        return CodexLimitRecommendedAction.DOWNGRADE_MODEL
    if _remaining_at_or_below(broad_quota, broad_quota_downgrade_threshold_percent):
        return CodexLimitRecommendedAction.DOWNGRADE_MODEL
    if short_window.status == CodexLimitWindowStatus.AVAILABLE and broad_quota.status == CodexLimitWindowStatus.AVAILABLE:
        return CodexLimitRecommendedAction.RESUME
    return CodexLimitRecommendedAction.WAIT


def decide_codex_limit_gate(
    record: CodexLimitAvailabilityRecord | None,
    *,
    require_record: bool = True,
    now: str = "",
    stale_after_seconds: int | None = None,
    future_tolerance_seconds: int = 30,
) -> CodexLimitGateDecision:
    """Decide whether a worker may make a new Codex-backed request."""

    if record is None:
        action = (
            CodexLimitRecommendedAction.ASK_PRODUCT_OWNER
            if require_record
            else CodexLimitRecommendedAction.RESUME
        )
        return CodexLimitGateDecision(
            allowed=not require_record,
            action=action,
            reason="No Codex limit availability record is available.",
        )

    timestamp_decision = _record_timestamp_gate_decision(
        record,
        now=now or _utc_now(),
        stale_after_seconds=stale_after_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )
    if timestamp_decision is not None:
        return timestamp_decision

    if record.recommended_action is CodexLimitRecommendedAction.RESUME:
        return CodexLimitGateDecision(
            allowed=True,
            action=record.recommended_action,
            reason="Codex limit availability allows new work.",
        )

    if record.recommended_action is CodexLimitRecommendedAction.WAIT:
        waiting_windows = _waiting_windows(record)
        return CodexLimitGateDecision(
            allowed=False,
            action=record.recommended_action,
            reason=(
                "One or more selected Codex quota windows are limited or too close to exhaustion."
                if record.plan_mode is CodexLimitPlanMode.DYNAMIC
                else f"Codex {_primary_window_label(record)} is limited or too close to exhaustion."
            ),
            resume_after=_first_reset_at(*(waiting_windows or (record.short_window, record.broad_quota))),
        )

    if record.recommended_action is CodexLimitRecommendedAction.DOWNGRADE_MODEL:
        return CodexLimitGateDecision(
            allowed=False,
            action=record.recommended_action,
            reason=(
                f"Codex {_secondary_window_label(record)} is limited or close to exhaustion; "
                "downgrade model before starting new work."
            ),
            resume_after=_first_reset_at(record.broad_quota, record.short_window),
        )

    return CodexLimitGateDecision(
        allowed=False,
        action=record.recommended_action,
        reason="Codex limit availability is unknown and needs Product Owner confirmation.",
        resume_after=_first_reset_at(record.short_window, record.broad_quota),
    )


def build_codex_limit_availability_record(
    *,
    record_id: str,
    short_window: CodexLimitWindowAvailability,
    broad_quota: CodexLimitWindowAvailability,
    plan_mode: CodexLimitPlanMode | str = CodexLimitPlanMode.DUAL_WINDOW,
    windows: Sequence[CodexLimitWindowAvailability] | None = None,
    note: str = "",
    account_scope_id: str = DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID,
) -> CodexLimitAvailabilityRecord:
    """Build and validate a durable limit availability record."""

    mode = _coerce_plan_mode(plan_mode)
    normalized_windows = _normalize_windows(
        mode,
        windows=windows,
        short_window=short_window,
        broad_quota=broad_quota,
    )
    record = CodexLimitAvailabilityRecord(
        id=record_id.strip(),
        short_window=short_window,
        broad_quota=broad_quota,
        recommended_action=recommend_codex_limit_action(
            short_window=short_window,
            broad_quota=broad_quota,
            plan_mode=mode,
            windows=normalized_windows,
        ),
        note=note.strip(),
        plan_mode=mode,
        windows=normalized_windows,
        account_scope_id=account_scope_id.strip() or DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID,
    )
    return require_valid_codex_limit_availability_record(record)


def build_single_pool_codex_limit_availability_record(
    *,
    record_id: str,
    pool: CodexLimitWindowAvailability,
    note: str = "",
    account_scope_id: str = DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID,
) -> CodexLimitAvailabilityRecord:
    """Build a one-window record for plans with one visible agentic usage pool."""

    return build_codex_limit_availability_record(
        record_id=record_id,
        short_window=pool,
        broad_quota=pool,
        plan_mode=CodexLimitPlanMode.SINGLE_POOL,
        windows=(pool,),
        note=note,
        account_scope_id=account_scope_id,
    )


def validate_codex_limit_availability_record(
    record: CodexLimitAvailabilityRecord,
) -> list[CodexLimitAvailabilityIssue]:
    """Return validation issues without mutating the record."""

    issues: list[CodexLimitAvailabilityIssue] = []
    _require_text(issues, "id", record.id)
    if not _SAFE_ACCOUNT_SCOPE_ID.fullmatch(record.account_scope_id):
        issues.append(
            CodexLimitAvailabilityIssue(
                field="account_scope_id",
                message=(
                    "Account scope must be a non-secret identifier containing only "
                    "letters, numbers, dots, underscores, and hyphens."
                ),
            )
        )
    _validate_window(issues, "short_window", record.short_window)
    _validate_window(issues, "broad_quota", record.broad_quota)
    _validate_windows(issues, record)
    expected = recommend_codex_limit_action(
        short_window=record.short_window,
        broad_quota=record.broad_quota,
        plan_mode=record.plan_mode,
        windows=record.windows,
    )
    if record.recommended_action != expected:
        issues.append(
            CodexLimitAvailabilityIssue(
                field="recommended_action",
                message=f"Recommended action should be {expected.value} for the current window states.",
            )
        )
    return issues


def require_valid_codex_limit_availability_record(
    record: CodexLimitAvailabilityRecord,
) -> CodexLimitAvailabilityRecord:
    """Raise when a Codex limit availability record is invalid."""

    issues = validate_codex_limit_availability_record(record)
    if issues:
        raise CodexLimitAvailabilityError(issues)
    return record


def codex_limit_availability_record_to_dict(record: CodexLimitAvailabilityRecord) -> dict[str, Any]:
    """Convert a record into JSON-compatible data."""

    return {
        "id": record.id,
        "short_window": _window_to_dict(record.short_window),
        "broad_quota": _window_to_dict(record.broad_quota),
        "recommended_action": record.recommended_action.value,
        "note": record.note,
        "plan_mode": record.plan_mode.value,
        "windows": [_window_to_dict(window) for window in record.windows],
        "account_scope_id": record.account_scope_id,
    }


def codex_limit_availability_record_from_dict(
    data: Mapping[str, Any],
) -> CodexLimitAvailabilityRecord:
    """Build a record from JSON-compatible data."""

    plan_mode = _coerce_plan_mode(data.get("plan_mode", CodexLimitPlanMode.DUAL_WINDOW.value))
    windows_data = data.get("windows", [])
    if windows_data is None:
        windows_data = []
    if not isinstance(windows_data, list):
        raise CodexLimitAvailabilityError(
            [CodexLimitAvailabilityIssue(field="windows", message="Windows must be a list.")]
        )
    windows = tuple(_window_from_dict(window) for window in windows_data if isinstance(window, Mapping))
    if len(windows) != len(windows_data):
        raise CodexLimitAvailabilityError(
            [CodexLimitAvailabilityIssue(field="windows", message="Each window must be an object.")]
        )
    short_window_data = data.get("short_window", {})
    broad_quota_data = data.get("broad_quota", {})
    if plan_mode is CodexLimitPlanMode.SINGLE_POOL and windows and "short_window" not in data:
        short_window_data = _window_to_dict(_primary_authoritative_window(windows, fallback=windows[0]))
    if plan_mode is CodexLimitPlanMode.SINGLE_POOL and windows and "broad_quota" not in data:
        broad_quota_data = _window_to_dict(_primary_authoritative_window(windows, fallback=windows[0]))
    if not isinstance(short_window_data, Mapping):
        raise CodexLimitAvailabilityError(
            [CodexLimitAvailabilityIssue(field="short_window", message="Window must be an object.")]
        )
    if not isinstance(broad_quota_data, Mapping):
        raise CodexLimitAvailabilityError(
            [CodexLimitAvailabilityIssue(field="broad_quota", message="Window must be an object.")]
        )
    record = CodexLimitAvailabilityRecord(
        id=_optional_text(data.get("id")),
        short_window=_window_from_dict(short_window_data),
        broad_quota=_window_from_dict(broad_quota_data),
        recommended_action=_enum_from_value(
            CodexLimitRecommendedAction,
            data.get("recommended_action", ""),
        ),
        note=_optional_text(data.get("note")),
        plan_mode=plan_mode,
        windows=windows,
        account_scope_id=(
            _optional_text(data.get("account_scope_id"))
            or DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID
        ),
    )
    return require_valid_codex_limit_availability_record(record)


def codex_limit_windows_for_display(
    record: CodexLimitAvailabilityRecord,
) -> tuple[tuple[str, CodexLimitWindowAvailability], ...]:
    """Return stable labels and windows for CLI/operator display."""

    windows = record.windows or _normalize_windows(
        record.plan_mode,
        windows=(),
        short_window=record.short_window,
        broad_quota=record.broad_quota,
    )
    if record.plan_mode is CodexLimitPlanMode.SINGLE_POOL:
        window = _primary_authoritative_window(windows, fallback=record.short_window)
        return ((_window_label(window, "Agentic usage pool"), window),)
    return tuple(
        (_window_label(window, _default_window_label(index)), window)
        for index, window in enumerate(windows)
    )


def format_codex_limit_availability_issues(issues: list[CodexLimitAvailabilityIssue]) -> str:
    """Format validation failures for tests and operator feedback."""

    if not issues:
        return "Codex limit availability record is valid."
    lines = ["Codex limit availability validation failed:"]
    lines.extend(f"- {issue.field}: {issue.message}" for issue in issues)
    return "\n".join(lines)


def _validate_window(
    issues: list[CodexLimitAvailabilityIssue],
    prefix: str,
    window: CodexLimitWindowAvailability,
) -> None:
    _require_text(issues, f"{prefix}.observed_at", window.observed_at)
    if window.window_duration_minutes is not None and window.window_duration_minutes <= 0:
        issues.append(
            CodexLimitAvailabilityIssue(
                field=f"{prefix}.window_duration_minutes",
                message="Window duration must be a positive integer when provided.",
            )
        )
    if window.status == CodexLimitWindowStatus.UNKNOWN:
        if window.remaining_percent is not None:
            issues.append(
                CodexLimitAvailabilityIssue(
                    field=f"{prefix}.remaining_percent",
                    message="Unknown window should not report remaining_percent.",
                )
            )
        return
    if window.remaining_percent is None:
        issues.append(
            CodexLimitAvailabilityIssue(
                field=f"{prefix}.remaining_percent",
                message="Known window status requires remaining_percent.",
            )
        )
    elif window.remaining_percent < 0 or window.remaining_percent > 100:
        issues.append(
            CodexLimitAvailabilityIssue(
                field=f"{prefix}.remaining_percent",
                message="remaining_percent must stay within 0..100.",
            )
        )
    _require_text(issues, f"{prefix}.reset_at", window.reset_at)


def _validate_windows(
    issues: list[CodexLimitAvailabilityIssue],
    record: CodexLimitAvailabilityRecord,
) -> None:
    if record.plan_mode is CodexLimitPlanMode.SINGLE_POOL:
        if not record.windows:
            issues.append(
                CodexLimitAvailabilityIssue(
                    field="windows",
                    message="Single-pool records must include the visible authoritative pool window.",
                )
            )
        authoritative = [window for window in record.windows if window.authoritative]
        if len(authoritative) != 1:
            issues.append(
                CodexLimitAvailabilityIssue(
                    field="windows.authoritative",
                    message="Single-pool records must have exactly one authoritative window.",
                )
            )
    for index, window in enumerate(record.windows):
        _validate_window(issues, f"windows[{index}]", window)


def _remaining_at_or_below(window: CodexLimitWindowAvailability, threshold_percent: int) -> bool:
    return (
        window.status == CodexLimitWindowStatus.AVAILABLE
        and window.remaining_percent is not None
        and window.remaining_percent <= threshold_percent
    )


def _first_reset_at(*windows: CodexLimitWindowAvailability) -> str:
    for window in windows:
        if window.reset_at.strip():
            return window.reset_at
    return ""


def _record_timestamp_gate_decision(
    record: CodexLimitAvailabilityRecord,
    *,
    now: str,
    stale_after_seconds: int | None,
    future_tolerance_seconds: int,
) -> CodexLimitGateDecision | None:
    parsed_now = _parse_strict_utc_datetime(now)
    if parsed_now is None or future_tolerance_seconds < 0:
        return CodexLimitGateDecision(
            allowed=False,
            action=CodexLimitRecommendedAction.ASK_PRODUCT_OWNER,
            reason="Codex limit timestamp validation configuration is invalid; refresh before new work.",
        )
    for label, window in codex_limit_windows_for_display(record):
        parsed_observed_at = _parse_strict_utc_datetime(window.observed_at)
        if parsed_observed_at is None:
            return CodexLimitGateDecision(
                allowed=False,
                action=CodexLimitRecommendedAction.ASK_PRODUCT_OWNER,
                reason=f"Codex limit window {label!r} has an invalid timestamp; refresh before new work.",
            )
        age_seconds = (parsed_now - parsed_observed_at).total_seconds()
        if age_seconds < -future_tolerance_seconds:
            return CodexLimitGateDecision(
                allowed=False,
                action=CodexLimitRecommendedAction.ASK_PRODUCT_OWNER,
                reason=(
                    f"Codex limit window {label!r} is materially future-dated; "
                    f"refresh or correct clock skew before new work "
                    f"(future_seconds={int(-age_seconds)}, tolerance_seconds={future_tolerance_seconds})."
                ),
            )
        if (
            stale_after_seconds is not None
            and stale_after_seconds > 0
            and age_seconds > stale_after_seconds
        ):
            return CodexLimitGateDecision(
                allowed=False,
                action=CodexLimitRecommendedAction.ASK_PRODUCT_OWNER,
                reason=(
                    f"Codex limit window {label!r} is stale; refresh before new work "
                    f"(age_seconds={int(age_seconds)}, stale_after_seconds={stale_after_seconds})."
                ),
            )
    return None


def _parse_strict_utc_datetime(value: str) -> datetime | None:
    if not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _recommend_single_pool_action(
    window: CodexLimitWindowAvailability,
    *,
    stop_threshold_percent: int,
) -> CodexLimitRecommendedAction:
    if window.status is CodexLimitWindowStatus.UNKNOWN:
        return CodexLimitRecommendedAction.ASK_PRODUCT_OWNER
    if window.status is CodexLimitWindowStatus.LIMITED:
        return CodexLimitRecommendedAction.WAIT
    if _remaining_at_or_below(window, stop_threshold_percent):
        return CodexLimitRecommendedAction.WAIT
    return CodexLimitRecommendedAction.RESUME


def _recommend_dynamic_action(
    windows: Sequence[CodexLimitWindowAvailability],
    *,
    stop_threshold_percent: int,
) -> CodexLimitRecommendedAction:
    if not windows or any(window.status is CodexLimitWindowStatus.UNKNOWN for window in windows):
        return CodexLimitRecommendedAction.ASK_PRODUCT_OWNER
    if any(window.status is CodexLimitWindowStatus.LIMITED for window in windows):
        return CodexLimitRecommendedAction.WAIT
    if any(_remaining_at_or_below(window, stop_threshold_percent) for window in windows):
        return CodexLimitRecommendedAction.WAIT
    return CodexLimitRecommendedAction.RESUME


def _waiting_windows(
    record: CodexLimitAvailabilityRecord,
) -> tuple[CodexLimitWindowAvailability, ...]:
    if record.plan_mode is not CodexLimitPlanMode.DYNAMIC:
        return ()
    return tuple(
        window
        for window in record.windows
        if window.status is not CodexLimitWindowStatus.AVAILABLE
        or _remaining_at_or_below(window, DEFAULT_SHORT_WINDOW_STOP_THRESHOLD_PERCENT)
    )


def _normalize_windows(
    plan_mode: CodexLimitPlanMode,
    *,
    windows: Sequence[CodexLimitWindowAvailability] | None,
    short_window: CodexLimitWindowAvailability,
    broad_quota: CodexLimitWindowAvailability,
) -> tuple[CodexLimitWindowAvailability, ...]:
    normalized = tuple(windows or ())
    if normalized:
        return normalized
    if plan_mode is CodexLimitPlanMode.SINGLE_POOL:
        return (_with_window_defaults(short_window, window_id="agentic_pool", label="Agentic usage pool"),)
    return (
        _with_window_defaults(short_window, window_id="primary", label="Primary window"),
        _with_window_defaults(broad_quota, window_id="secondary", label="Secondary quota"),
    )


def _primary_authoritative_window(
    windows: Sequence[CodexLimitWindowAvailability] | None,
    *,
    fallback: CodexLimitWindowAvailability,
) -> CodexLimitWindowAvailability:
    for window in windows or ():
        if window.authoritative:
            return window
    return fallback


def _coerce_plan_mode(value: CodexLimitPlanMode | str) -> CodexLimitPlanMode:
    if isinstance(value, CodexLimitPlanMode):
        return value
    return CodexLimitPlanMode(str(value).strip())


def _primary_window_label(record: CodexLimitAvailabilityRecord) -> str:
    if record.plan_mode is CodexLimitPlanMode.SINGLE_POOL:
        return _window_label(_primary_authoritative_window(record.windows, fallback=record.short_window), "Agentic usage pool")
    return _window_label(record.short_window, "primary window")


def _secondary_window_label(record: CodexLimitAvailabilityRecord) -> str:
    return _window_label(record.broad_quota, "secondary quota")


def _default_window_label(index: int) -> str:
    return "Primary window" if index == 0 else "Secondary quota"


def _window_label(window: CodexLimitWindowAvailability, default: str) -> str:
    return window.label.strip() or default


def _with_window_defaults(
    window: CodexLimitWindowAvailability,
    *,
    window_id: str,
    label: str,
) -> CodexLimitWindowAvailability:
    if window.window_id and window.label:
        return window
    return CodexLimitWindowAvailability(
        status=window.status,
        remaining_percent=window.remaining_percent,
        reset_at=window.reset_at,
        observation_source=window.observation_source,
        observed_at=window.observed_at,
        window_id=window.window_id or window_id,
        label=window.label or label,
        authoritative=window.authoritative,
        bucket_id=window.bucket_id,
        window_name=window.window_name,
        window_duration_minutes=window.window_duration_minutes,
    )


def _window_to_dict(window: CodexLimitWindowAvailability) -> dict[str, Any]:
    return {
        "status": window.status.value,
        "remaining_percent": window.remaining_percent,
        "reset_at": window.reset_at,
        "observation_source": window.observation_source.value,
        "observed_at": window.observed_at,
        "window_id": window.window_id,
        "label": window.label,
        "authoritative": window.authoritative,
        "bucket_id": window.bucket_id,
        "window_name": window.window_name,
        "window_duration_minutes": window.window_duration_minutes,
    }


def _window_from_dict(data: Mapping[str, Any]) -> CodexLimitWindowAvailability:
    remaining_percent = data.get("remaining_percent")
    if remaining_percent is not None:
        remaining_percent = _int_from_value("remaining_percent", remaining_percent)
    duration = data.get("window_duration_minutes")
    if duration is not None:
        duration = _int_from_value("window_duration_minutes", duration)
    return CodexLimitWindowAvailability(
        status=_enum_from_value(CodexLimitWindowStatus, data.get("status", "")),
        remaining_percent=remaining_percent,
        reset_at=_optional_text(data.get("reset_at")),
        observation_source=_enum_from_value(
            CodexLimitObservationSource,
            data.get("observation_source", ""),
        ),
        observed_at=_optional_text(data.get("observed_at")),
        window_id=_optional_text(data.get("window_id")),
        label=_optional_text(data.get("label")),
        authoritative=_bool_from_value(data.get("authoritative", True)),
        bucket_id=_optional_text(data.get("bucket_id")),
        window_name=_optional_text(data.get("window_name")),
        window_duration_minutes=duration,
    )


def _enum_from_value(enum_type: type[Enum], value: Any) -> Any:
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise CodexLimitAvailabilityError(
            [
                CodexLimitAvailabilityIssue(
                    field=enum_type.__name__,
                    message=f"Unsupported value {str(value)!r}.",
                )
            ]
        ) from exc


def _int_from_value(field_name: str, value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CodexLimitAvailabilityError(
            [CodexLimitAvailabilityIssue(field=field_name, message="Value must be an integer.")]
        ) from exc


def _bool_from_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if str(value).strip().casefold() in {"1", "true", "yes"}:
        return True
    if str(value).strip().casefold() in {"0", "false", "no"}:
        return False
    raise CodexLimitAvailabilityError(
        [CodexLimitAvailabilityIssue(field="authoritative", message="Value must be boolean.")]
    )


def _require_text(issues: list[CodexLimitAvailabilityIssue], field_name: str, value: str) -> None:
    if not value.strip():
        issues.append(CodexLimitAvailabilityIssue(field=field_name, message="Required value is missing."))


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
