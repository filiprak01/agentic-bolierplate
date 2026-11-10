from concurrent.futures import ThreadPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from threading import Barrier

import pytest

from agentic_boilerplate.domain import (
    CodexLimitObservationSource,
    CodexLimitRecommendedAction,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    build_codex_limit_availability_record,
    build_single_pool_codex_limit_availability_record,
)
from agentic_boilerplate.storage import (
    CODEX_LIMIT_AVAILABILITY_FILE_SUFFIX,
    CODEX_LIMIT_AVAILABILITY_FOLDER,
    CodexLimitAvailabilityNotFoundError,
    CodexLimitAvailabilitySelectionError,
    ConflictingCodexLimitAvailabilityRecordError,
    FileCodexLimitAvailabilityStore,
    InvalidCodexLimitAvailabilityIdError,
    resolve_codex_limit_write_bucket_id,
    select_latest_codex_limit_record,
)


def test_store_writes_reads_and_lists_records(tmp_path: Path) -> None:
    store = FileCodexLimitAvailabilityStore(tmp_path)
    record = _record("availability-20260706T100000Z")

    location = store.write_record(record)
    restored = store.read_record(record.id)
    listed = store.list_records()

    assert location.path == tmp_path / CODEX_LIMIT_AVAILABILITY_FOLDER / f"{record.id}{CODEX_LIMIT_AVAILABILITY_FILE_SUFFIX}"
    assert restored == record
    assert listed == (record,)


def test_identical_retry_is_idempotent_but_conflicting_content_is_rejected(tmp_path: Path) -> None:
    store = FileCodexLimitAvailabilityStore(tmp_path)
    original = _record("current", note="first")
    conflicting = _record("current", note="different")

    first = store.write_record(original)
    retry = store.write_record(original)

    assert retry == first
    with pytest.raises(ConflictingCodexLimitAvailabilityRecordError):
        store.write_record(conflicting)
    assert store.read_record("current") == original


def test_same_second_observations_keep_distinct_ids_and_choose_conservatively(tmp_path: Path) -> None:
    store = FileCodexLimitAvailabilityStore(tmp_path)
    available = _record(
        "availability-b",
        status=CodexLimitWindowStatus.AVAILABLE,
        observed_at="2026-09-02T12:00:00Z",
    )
    limited = _record(
        "availability-a",
        status=CodexLimitWindowStatus.LIMITED,
        remaining_percent=0,
        observed_at="2026-09-02T12:00:00Z",
    )

    store.write_record(available)
    store.write_record(limited)

    assert len(store.list_records()) == 2
    assert store.latest_record() == limited


def test_latest_selection_uses_observation_time_not_filename_or_write_order(tmp_path: Path) -> None:
    store = FileCodexLimitAvailabilityStore(tmp_path)
    newest = _record("a-old-looking-name", observed_at="2026-09-02T12:05:00Z")
    older = _record("z-new-looking-name", observed_at="2026-09-02T12:00:00Z")

    store.write_record(newest)
    store.write_record(older)
    restarted = FileCodexLimitAvailabilityStore(tmp_path)

    assert restarted.latest_record() == newest


def test_manual_available_cannot_clear_provider_block_until_newer_provider_recovery() -> None:
    provider_block = _record(
        "provider-block",
        status=CodexLimitWindowStatus.LIMITED,
        remaining_percent=0,
        observed_at="2026-09-02T12:00:00Z",
        source=CodexLimitObservationSource.CODEX_APP_SERVER,
    )
    manual_available = _record(
        "manual-available",
        observed_at="2026-09-02T12:01:00Z",
        source=CodexLimitObservationSource.OPERATOR,
    )
    provider_recovery = _record(
        "provider-recovery",
        observed_at="2026-09-02T12:02:00Z",
        source=CodexLimitObservationSource.CODEX_APP_SERVER,
    )

    assert select_latest_codex_limit_record((provider_block, manual_available)) == provider_block
    assert (
        select_latest_codex_limit_record(
            (provider_block, manual_available, provider_recovery)
        )
        == provider_recovery
    )


def test_failed_authoritative_refresh_blocks_reuse_of_older_available_state() -> None:
    available = _record(
        "provider-available",
        observed_at="2026-09-02T12:00:00Z",
        source=CodexLimitObservationSource.CODEX_APP_SERVER,
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )
    failed_refresh = _record(
        "provider-refresh-failed",
        status=CodexLimitWindowStatus.UNKNOWN,
        remaining_percent=None,
        observed_at="2026-09-02T12:01:00Z",
        source=CodexLimitObservationSource.EXPLICIT_FAILURE,
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )

    selected = select_latest_codex_limit_record(
        (available, failed_refresh),
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )

    assert selected == failed_refresh
    assert selected.recommended_action is CodexLimitRecommendedAction.ASK_PRODUCT_OWNER


def test_write_bucket_resolution_uses_provider_scope_and_fails_closed_when_ambiguous() -> None:
    provider = _record(
        "provider",
        source=CodexLimitObservationSource.CODEX_APP_SERVER,
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )
    other_account = _record(
        "other-account",
        source=CodexLimitObservationSource.CODEX_APP_SERVER,
        account_scope_id="chatgpt-secondary",
        bucket_id="credits",
    )

    assert (
        resolve_codex_limit_write_bucket_id(
            (provider, other_account),
            account_scope_id="chatgpt-primary",
        )
        == "codex"
    )
    assert (
        resolve_codex_limit_write_bucket_id(
            (),
            account_scope_id="chatgpt-primary",
        )
        == ""
    )

    ambiguous = (
        provider,
        _record(
            "provider-credits",
            source=CodexLimitObservationSource.CODEX_CLI,
            account_scope_id="chatgpt-primary",
            bucket_id="credits",
        ),
    )
    with pytest.raises(CodexLimitAvailabilitySelectionError):
        resolve_codex_limit_write_bucket_id(
            ambiguous,
            account_scope_id="chatgpt-primary",
        )
    assert (
        resolve_codex_limit_write_bucket_id(
            ambiguous,
            account_scope_id="chatgpt-primary",
            configured_bucket_id="configured",
        )
        == "configured"
    )


def test_unscoped_operator_stop_applies_to_first_named_provider_bucket() -> None:
    provider = _record(
        "provider-available",
        observed_at="2026-09-02T12:00:00Z",
        source=CodexLimitObservationSource.CODEX_APP_SERVER,
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )
    operator_stop = _record(
        "operator-stop",
        status=CodexLimitWindowStatus.LIMITED,
        remaining_percent=0,
        observed_at="2026-09-02T12:01:00Z",
        source=CodexLimitObservationSource.OPERATOR,
        account_scope_id="chatgpt-primary",
    )

    selected = select_latest_codex_limit_record(
        (provider, operator_stop),
        account_scope_id="chatgpt-primary",
    )

    assert selected == operator_stop
    assert operator_stop.short_window.bucket_id == ""


def test_unscoped_failed_refresh_survives_first_provider_bucket_write(tmp_path: Path) -> None:
    store = FileCodexLimitAvailabilityStore(tmp_path)
    failed_refresh = _record(
        "failed-unscoped-refresh",
        status=CodexLimitWindowStatus.UNKNOWN,
        remaining_percent=None,
        observed_at="2026-09-02T12:01:00Z",
        source=CodexLimitObservationSource.EXPLICIT_FAILURE,
        account_scope_id="chatgpt-primary",
    )
    older_provider_available = _record(
        "provider-available-codex",
        observed_at="2026-09-02T12:00:00Z",
        source=CodexLimitObservationSource.CODEX_APP_SERVER,
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )
    other_account_failed = _record(
        "other-account-failed-refresh",
        status=CodexLimitWindowStatus.UNKNOWN,
        remaining_percent=None,
        observed_at="2026-09-02T12:02:00Z",
        source=CodexLimitObservationSource.EXPLICIT_FAILURE,
        account_scope_id="chatgpt-secondary",
    )

    store.write_record(failed_refresh)
    store.write_record(other_account_failed)
    selected = store.write_record_and_select_latest(
        older_provider_available,
        account_scope_id="chatgpt-primary",
    )
    follow_up = store.latest_record(account_scope_id="chatgpt-primary")

    assert selected == failed_refresh
    assert follow_up == failed_refresh
    assert failed_refresh.short_window.bucket_id == ""
    assert store.latest_record(account_scope_id="chatgpt-secondary") == other_account_failed


def test_unscoped_provider_available_is_not_carried_into_named_bucket() -> None:
    named_provider_block = _record(
        "provider-block-codex",
        status=CodexLimitWindowStatus.LIMITED,
        remaining_percent=0,
        observed_at="2026-09-02T12:00:00Z",
        source=CodexLimitObservationSource.CODEX_APP_SERVER,
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )
    unscoped_provider_available = _record(
        "unscoped-provider-available",
        observed_at="2026-09-02T12:01:00Z",
        source=CodexLimitObservationSource.CODEX_APP_SERVER,
        account_scope_id="chatgpt-primary",
    )

    selected = select_latest_codex_limit_record(
        (named_provider_block, unscoped_provider_available),
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )

    assert selected == named_provider_block
    assert unscoped_provider_available.short_window.bucket_id == ""


def test_account_and_bucket_scopes_are_separated_and_ambiguity_fails_closed() -> None:
    account_a = _record(
        "account-a",
        account_scope_id="chatgpt-a",
        bucket_id="codex",
    )
    account_b = _record(
        "account-b",
        account_scope_id="chatgpt-b",
        bucket_id="codex",
    )
    bucket_b = _record(
        "bucket-b",
        account_scope_id="chatgpt-a",
        bucket_id="credits",
    )
    records = (account_a, account_b, bucket_b)

    assert (
        select_latest_codex_limit_record(
            records,
            account_scope_id="chatgpt-a",
            bucket_id="codex",
        )
        == account_a
    )
    with pytest.raises(CodexLimitAvailabilitySelectionError):
        select_latest_codex_limit_record(records)
    with pytest.raises(CodexLimitAvailabilitySelectionError):
        select_latest_codex_limit_record(
            records,
            account_scope_id="chatgpt-a",
        )


def test_concurrent_writers_cannot_silently_replace_one_observation(tmp_path: Path) -> None:
    store = FileCodexLimitAvailabilityStore(tmp_path)
    first = _record("collision", note="first")
    second = _record("collision", note="second")
    barrier = Barrier(2)

    def write(record):
        barrier.wait()
        return store.write_record(record)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(write, first), executor.submit(write, second))

    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result())
        except ConflictingCodexLimitAvailabilityRecordError as error:
            outcomes.append(error)

    assert sum(isinstance(outcome, ConflictingCodexLimitAvailabilityRecordError) for outcome in outcomes) == 1
    assert store.read_record("collision") in {first, second}


def test_concurrent_thread_readers_observe_the_same_safe_latest_record(tmp_path: Path) -> None:
    store = FileCodexLimitAvailabilityStore(tmp_path)
    store.write_record(_record("z-older", observed_at="2026-09-02T12:00:00Z"))
    newest = _record(
        "a-newer",
        status=CodexLimitWindowStatus.LIMITED,
        remaining_percent=0,
        observed_at="2026-09-02T12:01:00Z",
    )
    store.write_record(newest)

    with ThreadPoolExecutor(max_workers=2) as executor:
        selected = tuple(executor.map(lambda _: store.latest_record(), range(20)))

    assert selected == (newest,) * 20


def test_multiprocess_shared_store_preserves_immutable_writes_and_conservative_restart_selection(
    tmp_path: Path,
) -> None:
    context = get_context("spawn")
    start_event = context.Event()
    ready_queue = context.Queue()
    outcome_queue = context.Queue()
    collision_first = _record(
        "shared-collision",
        note="first",
        account_scope_id="collision-scope",
        bucket_id="collision-bucket",
    )
    collision_second = _record(
        "shared-collision",
        note="second",
        account_scope_id="collision-scope",
        bucket_id="collision-bucket",
    )
    provider_block = _record(
        "provider-block",
        status=CodexLimitWindowStatus.LIMITED,
        remaining_percent=0,
        observed_at="2026-09-02T12:00:00Z",
        source=CodexLimitObservationSource.CODEX_APP_SERVER,
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )
    newer_manual_available = _record(
        "newer-manual-available",
        observed_at="2026-09-02T12:01:00Z",
        source=CodexLimitObservationSource.OPERATOR,
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )
    records = (collision_first, collision_second, provider_block, newer_manual_available)
    processes = [
        context.Process(
            target=_write_record_in_process,
            args=(str(tmp_path), record, start_event, ready_queue, outcome_queue),
        )
        for record in records
    ]

    try:
        for process in processes:
            process.start()
        ready = {ready_queue.get(timeout=10) for _ in processes}
        assert ready == {record.id for record in records}
        start_event.set()
        for process in processes:
            process.join(timeout=10)
        assert all(not process.is_alive() for process in processes)
        assert all(process.exitcode == 0 for process in processes)
        outcomes = [outcome_queue.get(timeout=5) for _ in processes]
    finally:
        start_event.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        ready_queue.close()
        outcome_queue.close()

    assert sum(outcome[1] == "written" for outcome in outcomes) == 3
    assert sum(outcome[1] == "conflict" for outcome in outcomes) == 1
    assert {outcome[0] for outcome in outcomes} == {record.id for record in records}

    first_reader = FileCodexLimitAvailabilityStore(tmp_path)
    second_reader = FileCodexLimitAvailabilityStore(tmp_path)
    stored_records = first_reader.list_records()
    assert len(stored_records) == 3
    assert first_reader.read_record("shared-collision") in {collision_first, collision_second}
    assert first_reader.read_record("provider-block") == provider_block
    assert first_reader.read_record("newer-manual-available") == newer_manual_available

    selections = tuple(
        reader.latest_record(account_scope_id="chatgpt-primary", bucket_id="codex")
        for reader in (first_reader, second_reader)
    )
    assert selections == (provider_block, provider_block)


def test_selection_failure_returns_unknown_record_for_runtime_consumers(tmp_path: Path) -> None:
    store = FileCodexLimitAvailabilityStore(tmp_path)
    store.write_record(_record("a", account_scope_id="account-a"))
    store.write_record(_record("b", account_scope_id="account-b"))

    selected = store.latest_record()

    assert selected is not None
    assert selected.id == "selection-failure"
    assert selected.recommended_action is CodexLimitRecommendedAction.ASK_PRODUCT_OWNER
    assert "ambiguous" in selected.note


def test_write_record_and_select_latest_fails_closed_after_persisting_ambiguous_record(
    tmp_path: Path,
) -> None:
    store = FileCodexLimitAvailabilityStore(tmp_path)
    older_available = _record(
        "older-available",
        observed_at="2026-09-02T12:00:00Z",
        account_scope_id="chatgpt-primary",
    )
    codex_window = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=95,
        reset_at="2026-09-03T10:00:00Z",
        observation_source=CodexLimitObservationSource.OPERATOR,
        observed_at="2026-09-02T12:01:00Z",
        window_id="codex-window",
        label="Codex quota",
        bucket_id="codex",
    )
    credits_window = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=88,
        reset_at="2026-09-04T10:00:00Z",
        observation_source=CodexLimitObservationSource.OPERATOR,
        observed_at="2026-09-02T12:01:00Z",
        window_id="credits-window",
        label="Credit quota",
        bucket_id="credits",
    )
    ambiguous = build_codex_limit_availability_record(
        record_id="explicit-multi-bucket",
        short_window=codex_window,
        broad_quota=credits_window,
        windows=(codex_window, credits_window),
        account_scope_id="chatgpt-primary",
    )

    store.write_record(older_available)
    selected = store.write_record_and_select_latest(
        ambiguous,
        account_scope_id="chatgpt-primary",
    )
    follow_up = store.latest_record(account_scope_id="chatgpt-primary")

    assert store.read_record("explicit-multi-bucket") == ambiguous
    assert selected is not None
    assert selected.id == "selection-failure"
    assert selected.recommended_action is CodexLimitRecommendedAction.ASK_PRODUCT_OWNER
    assert "multiple quota bucket identities" in selected.note
    assert follow_up is not None
    assert follow_up.id == "selection-failure"
    assert follow_up.recommended_action is CodexLimitRecommendedAction.ASK_PRODUCT_OWNER


def test_missing_and_invalid_ids_are_rejected(tmp_path: Path) -> None:
    store = FileCodexLimitAvailabilityStore(tmp_path)

    with pytest.raises(CodexLimitAvailabilityNotFoundError):
        store.read_record("missing")
    with pytest.raises(InvalidCodexLimitAvailabilityIdError):
        store.record_path("../escape")


def _record(
    record_id: str,
    *,
    status: CodexLimitWindowStatus = CodexLimitWindowStatus.AVAILABLE,
    remaining_percent: int | None = 75,
    observed_at: str = "2026-09-02T12:00:00Z",
    source: CodexLimitObservationSource = CodexLimitObservationSource.OPERATOR,
    account_scope_id: str = "default",
    bucket_id: str = "",
    note: str = "",
):
    window = CodexLimitWindowAvailability(
        status=status,
        remaining_percent=remaining_percent,
        reset_at="2026-09-07T10:00:00Z",
        observation_source=source,
        observed_at=observed_at,
        window_id="primary",
        label="Codex quota",
        bucket_id=bucket_id,
    )
    return build_single_pool_codex_limit_availability_record(
        record_id=record_id,
        pool=window,
        note=note,
        account_scope_id=account_scope_id,
    )


def _write_record_in_process(root: str, record, start_event, ready_queue, outcome_queue) -> None:
    store = FileCodexLimitAvailabilityStore(Path(root))
    ready_queue.put(record.id)
    if not start_event.wait(timeout=10):
        outcome_queue.put((record.id, "start-timeout"))
        return
    try:
        store.write_record(record)
    except ConflictingCodexLimitAvailabilityRecordError:
        outcome_queue.put((record.id, "conflict"))
    else:
        outcome_queue.put((record.id, "written"))
