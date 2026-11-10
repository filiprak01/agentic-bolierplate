"""File-backed store for durable Codex limit availability records."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from agentic_boilerplate.domain import (
    DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID,
    CodexLimitAvailabilityRecord,
    CodexLimitObservationSource,
    CodexLimitRecommendedAction,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    build_single_pool_codex_limit_availability_record,
    codex_limit_availability_record_from_dict,
    codex_limit_availability_record_to_dict,
    require_valid_codex_limit_availability_record,
)


CODEX_LIMIT_AVAILABILITY_FILE_SUFFIX = ".json"
CODEX_LIMIT_AVAILABILITY_FOLDER = "limit-availability"
_SAFE_LIMIT_RECORD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class CodexLimitAvailabilityStoreError(RuntimeError):
    """Base error for Codex limit availability persistence."""


class CodexLimitAvailabilityNotFoundError(CodexLimitAvailabilityStoreError):
    """Raised when a stored availability record cannot be found."""


class InvalidCodexLimitAvailabilityIdError(CodexLimitAvailabilityStoreError):
    """Raised when a record id is unsafe for filesystem paths."""


class ConflictingCodexLimitAvailabilityRecordError(CodexLimitAvailabilityStoreError):
    """Raised when immutable observation identity is reused with different content."""


class CodexLimitAvailabilitySelectionError(CodexLimitAvailabilityStoreError):
    """Raised when records cannot be selected safely for one quota scope."""


@dataclass(frozen=True)
class CodexLimitAvailabilityLocation:
    record_id: str
    path: Path


class FileCodexLimitAvailabilityStore:
    """Persist Codex limit availability records as durable JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @property
    def availability_directory(self) -> Path:
        return self.root / CODEX_LIMIT_AVAILABILITY_FOLDER

    def ensure_directory(self) -> Path:
        self.availability_directory.mkdir(parents=True, exist_ok=True)
        return self.availability_directory

    def record_path(self, record_id: str) -> Path:
        _validate_record_id(record_id)
        return self.availability_directory / f"{record_id}{CODEX_LIMIT_AVAILABILITY_FILE_SUFFIX}"

    def write_record(self, record: CodexLimitAvailabilityRecord) -> CodexLimitAvailabilityLocation:
        record = require_valid_codex_limit_availability_record(record)
        self.ensure_directory()
        path = self.record_path(record.id)
        data = codex_limit_availability_record_to_dict(record)
        try:
            _atomic_create_json(path, data)
        except FileExistsError:
            existing = self.read_record(record.id)
            if codex_limit_availability_record_to_dict(existing) != data:
                raise ConflictingCodexLimitAvailabilityRecordError(
                    f"Codex limit availability record {record.id!r} already exists "
                    "with different immutable content."
                )
        return CodexLimitAvailabilityLocation(record_id=record.id, path=path)

    def read_record(self, record_id: str) -> CodexLimitAvailabilityRecord:
        path = self.record_path(record_id)
        if not path.is_file():
            raise CodexLimitAvailabilityNotFoundError(f"Codex limit availability record {record_id!r} was not found.")
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return codex_limit_availability_record_from_dict(data)

    def list_records(self) -> tuple[CodexLimitAvailabilityRecord, ...]:
        self.ensure_directory()
        return tuple(
            self.read_record(path.stem)
            for path in sorted(self.availability_directory.glob(f"*{CODEX_LIMIT_AVAILABILITY_FILE_SUFFIX}"))
        )

    def latest_record(
        self,
        *,
        account_scope_id: str = "",
        bucket_id: str = "",
    ) -> CodexLimitAvailabilityRecord | None:
        """Return the newest safe observation for one applicable quota scope."""

        try:
            records = self.list_records()
            return select_latest_codex_limit_record(
                records,
                account_scope_id=account_scope_id,
                bucket_id=bucket_id,
            )
        except (CodexLimitAvailabilitySelectionError, ValueError) as error:
            return _selection_failure_record(
                account_scope_id=account_scope_id,
                reason=str(error),
            )

    def write_record_and_select_latest(
        self,
        record: CodexLimitAvailabilityRecord,
        *,
        account_scope_id: str = "",
        bucket_id: str = "",
        write: Callable[[CodexLimitAvailabilityRecord], CodexLimitAvailabilityRecord] | None = None,
    ) -> CodexLimitAvailabilityRecord | None:
        """Persist a record and select from the stored record scope."""

        writer = write or self._write_and_return_record
        stored = writer(record)
        try:
            effective_bucket_id = bucket_id.strip() or _record_scope(stored)[1]
        except (CodexLimitAvailabilitySelectionError, ValueError) as error:
            return _selection_failure_record(
                account_scope_id=account_scope_id or stored.account_scope_id,
                reason=str(error),
            )
        return self.latest_record(
            account_scope_id=account_scope_id or stored.account_scope_id,
            bucket_id=effective_bucket_id,
        )

    def _write_and_return_record(
        self,
        record: CodexLimitAvailabilityRecord,
    ) -> CodexLimitAvailabilityRecord:
        self.write_record(record)
        return record


def resolve_codex_limit_write_bucket_id(
    records: Iterable[CodexLimitAvailabilityRecord],
    *,
    account_scope_id: str = "",
    configured_bucket_id: str = "",
) -> str:
    """Resolve an unscoped write to the sole durable provider bucket."""

    configured = configured_bucket_id.strip()
    if configured:
        return configured

    selected_account = account_scope_id.strip() or DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID
    named_buckets: set[str] = set()
    for record in records:
        record_account = record.account_scope_id or DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID
        if record_account != selected_account:
            continue
        windows = record.windows or (record.short_window, record.broad_quota)
        authoritative = tuple(window for window in windows if window.authoritative) or windows
        named_buckets.update(
            window.bucket_id.strip()
            for window in authoritative
            if window.observation_source in _PROVIDER_OBSERVATION_SOURCES
            and window.bucket_id.strip()
        )

    if len(named_buckets) > 1:
        raise CodexLimitAvailabilitySelectionError(
            "Codex quota bucket is ambiguous; configure CODEX_LIMIT_BUCKET_ID."
        )
    return next(iter(named_buckets), "")


def select_latest_codex_limit_record(
    records: Iterable[CodexLimitAvailabilityRecord],
    *,
    account_scope_id: str = "",
    bucket_id: str = "",
) -> CodexLimitAvailabilityRecord | None:
    """Select chronologically with conservative conflict and authority rules."""

    scoped = tuple((_record_scope(record), record) for record in records)
    if not scoped:
        return None
    account_records = _select_account_scope(scoped, account_scope_id=account_scope_id)
    if not account_records:
        return None
    applicable = _select_bucket_scope(account_records, bucket_id=bucket_id)
    if not applicable:
        return None

    ordered = sorted(
        applicable,
        key=_record_order_key,
        reverse=True,
    )
    latest = ordered[0]
    if latest.recommended_action is not CodexLimitRecommendedAction.RESUME:
        return latest
    if _is_authoritative_provider_record(latest):
        return latest

    provider_blocks = tuple(
        record
        for record in ordered
        if _is_authoritative_provider_record(record)
        and record.recommended_action is not CodexLimitRecommendedAction.RESUME
    )
    if not provider_blocks:
        return latest
    newest_block = max(provider_blocks, key=_record_order_key)
    provider_recoveries = tuple(
        record
        for record in ordered
        if _is_authoritative_provider_record(record)
        and record.recommended_action is CodexLimitRecommendedAction.RESUME
    )
    if not provider_recoveries:
        return newest_block
    newest_recovery = max(provider_recoveries, key=_record_order_key)
    if _record_observation_time(newest_recovery) <= _record_observation_time(newest_block):
        return newest_block
    return latest


def _validate_record_id(record_id: str) -> None:
    if not _SAFE_LIMIT_RECORD_ID.fullmatch(record_id):
        raise InvalidCodexLimitAvailabilityIdError(
            "Codex limit availability ids may contain letters, numbers, dots, underscores, and hyphens."
        )


def _atomic_create_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.link(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _record_scope(record: CodexLimitAvailabilityRecord) -> tuple[str, str]:
    windows = record.windows or (record.short_window, record.broad_quota)
    bucket_ids = {window.bucket_id.strip() for window in windows if window.bucket_id.strip()}
    if len(bucket_ids) > 1:
        raise CodexLimitAvailabilitySelectionError(
            f"Record {record.id!r} contains multiple quota bucket identities."
        )
    return (
        record.account_scope_id or DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID,
        next(iter(bucket_ids), "default"),
    )


def _select_account_scope(
    scoped: tuple[tuple[tuple[str, str], CodexLimitAvailabilityRecord], ...],
    *,
    account_scope_id: str,
) -> tuple[tuple[tuple[str, str], CodexLimitAvailabilityRecord], ...]:
    requested = account_scope_id.strip()
    if requested:
        return tuple(item for item in scoped if item[0][0] == requested)
    named = sorted({scope[0] for scope, _ in scoped if scope[0] != DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID})
    if len(named) > 1:
        raise CodexLimitAvailabilitySelectionError(
            "Codex account scope is ambiguous; configure CODEX_LIMIT_ACCOUNT_SCOPE_ID."
        )
    selected = named[0] if named else DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID
    return tuple(item for item in scoped if item[0][0] == selected)


def _select_bucket_scope(
    scoped: tuple[tuple[tuple[str, str], CodexLimitAvailabilityRecord], ...],
    *,
    bucket_id: str,
) -> tuple[CodexLimitAvailabilityRecord, ...]:
    requested = bucket_id.strip()
    if requested:
        selected_records = tuple(record for scope, record in scoped if scope[1] == requested)
        if requested == "default":
            return selected_records
        return selected_records + _unscoped_fail_closed_carry_forward_records(scoped)
    named = sorted({scope[1] for scope, _ in scoped if scope[1] != "default"})
    if len(named) > 1:
        raise CodexLimitAvailabilitySelectionError(
            "Codex quota bucket is ambiguous; configure CODEX_LIMIT_BUCKET_ID."
        )
    selected = named[0] if named else "default"
    selected_records = tuple(record for scope, record in scoped if scope[1] == selected)
    if selected == "default":
        return selected_records
    return selected_records + _unscoped_fail_closed_carry_forward_records(scoped)


def _unscoped_fail_closed_carry_forward_records(
    scoped: tuple[tuple[tuple[str, str], CodexLimitAvailabilityRecord], ...],
) -> tuple[CodexLimitAvailabilityRecord, ...]:
    return tuple(
        record
        for scope, record in scoped
        if scope[1] == "default" and _is_unscoped_fail_closed_carry_forward(record)
    )


def _record_order_key(record: CodexLimitAvailabilityRecord) -> tuple[datetime, int, int, str]:
    action_rank = {
        CodexLimitRecommendedAction.RESUME: 0,
        CodexLimitRecommendedAction.DOWNGRADE_MODEL: 1,
        CodexLimitRecommendedAction.WAIT: 2,
        CodexLimitRecommendedAction.ASK_PRODUCT_OWNER: 3,
    }[record.recommended_action]
    return (
        _record_observation_time(record),
        action_rank,
        1 if _is_authoritative_provider_record(record) else 0,
        record.id,
    )


def _record_observation_time(record: CodexLimitAvailabilityRecord) -> datetime:
    windows = record.windows or (record.short_window, record.broad_quota)
    parsed = tuple(_strict_utc_datetime(window.observed_at, record_id=record.id) for window in windows)
    authoritative = tuple(
        timestamp
        for window, timestamp in zip(windows, parsed, strict=True)
        if window.authoritative
    )
    return min(authoritative or parsed)


def _strict_utc_datetime(value: str, *, record_id: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise CodexLimitAvailabilitySelectionError(
            f"Record {record_id!r} has an invalid observation timestamp."
        ) from error
    if parsed.tzinfo is None:
        raise CodexLimitAvailabilitySelectionError(
            f"Record {record_id!r} observation timestamp must include a timezone."
        )
    return parsed.astimezone(timezone.utc)


_PROVIDER_OBSERVATION_SOURCES = frozenset(
    {
        CodexLimitObservationSource.CODEX_APP_SERVER,
        CodexLimitObservationSource.CODEX_CLI,
        CodexLimitObservationSource.EXPLICIT_FAILURE,
    }
)


def _is_authoritative_provider_record(record: CodexLimitAvailabilityRecord) -> bool:
    windows = record.windows or (record.short_window, record.broad_quota)
    authoritative = tuple(window for window in windows if window.authoritative) or windows
    return any(
        window.observation_source in _PROVIDER_OBSERVATION_SOURCES
        for window in authoritative
    )


def _is_unscoped_fail_closed_carry_forward(record: CodexLimitAvailabilityRecord) -> bool:
    if record.recommended_action is CodexLimitRecommendedAction.RESUME:
        return False
    windows = record.windows or (record.short_window, record.broad_quota)
    authoritative = tuple(window for window in windows if window.authoritative) or windows
    return any(
        window.observation_source is CodexLimitObservationSource.OPERATOR
        or window.observation_source in _PROVIDER_OBSERVATION_SOURCES
        for window in authoritative
    )


def _selection_failure_record(
    *,
    account_scope_id: str,
    reason: str,
) -> CodexLimitAvailabilityRecord:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    window = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.UNKNOWN,
        remaining_percent=None,
        reset_at="",
        observation_source=CodexLimitObservationSource.UNKNOWN,
        observed_at=now,
        window_id="selection_failure",
        label="Codex quota selection failed",
    )
    return build_single_pool_codex_limit_availability_record(
        record_id="selection-failure",
        pool=window,
        note=reason,
        account_scope_id=account_scope_id or DEFAULT_CODEX_LIMIT_ACCOUNT_SCOPE_ID,
    )
