from dataclasses import replace

from agentic_boilerplate.domain import (
    AutomatedCoverageReference,
    AgileTestTestExecutionConfig,
    AgileTestTestExecutionUpsertRequest,
    EvidencePublicationMode,
    PublicationReadinessWarningType,
    RegressionClassification,
    RegressionExecutionMode,
    RegressionExecutionResult,
    RegressionManifestReferences,
    build_agiletest_test_execution_upsert_plan,
    build_regression_artifact_publication_bundle,
    build_regression_manifest,
    build_regression_manifest_record,
    classify_test_issue,
    render_regression_artifact_publication_bundle,
)


def test_bundle_maps_manifest_into_publication_request() -> None:
    manifest = _manifest()

    bundle = build_regression_artifact_publication_bundle(
        _request(manifest=manifest)
    )

    assert bundle.manifest_key == "REGRESSION-S10"
    assert bundle.overview_task_key == "AGENT-239"
    assert bundle.test_execution_key == "AGENT-335"
    assert bundle.included_test_case_keys == ("AGENT-401", "AGENT-402")
    assert bundle.publication_request is not None
    assert [comment.issue_key for comment in bundle.publication_request.comments] == [
        "AGENT-239",
        "AGENT-335",
    ]
    assert [attachment.issue_key for attachment in bundle.publication_request.attachments] == [
        "AGENT-239",
        "AGENT-335",
    ]
    assert [(link.source_issue_key, link.target_issue_key) for link in bundle.publication_request.links] == [
        ("AGENT-239", "AGENT-335"),
        ("AGENT-335", "AGENT-401"),
        ("AGENT-335", "AGENT-402"),
    ]


def test_bundle_reuses_upsert_plan_links_when_present() -> None:
    manifest = _manifest(execution_key="")
    upsert_plan = build_agiletest_test_execution_upsert_plan(
        request=AgileTestTestExecutionUpsertRequest(
            release_key="release-mvp",
            sprint_label="mvp-sprint-10",
            regression_overview_key="AGENT-239",
            evidence_path="data/agent-logs/REGRESSION-S10/regression-evidence.md",
            test_case_keys=("AGENT-401", "AGENT-402"),
        ),
        config=AgileTestTestExecutionConfig(
            project_key="AGENT",
            overview_execution_link_type="Relates",
            execution_test_case_link_type="AgileTest",
        ),
    )

    bundle = build_regression_artifact_publication_bundle(
        _request(manifest=manifest, upsert_plan=upsert_plan)
    )

    assert bundle.test_execution_key == upsert_plan.execution_issue_key
    assert bundle.publication_request is not None
    assert bundle.publication_request.links == upsert_plan.publication_request.links


def test_bundle_emits_readiness_warnings_for_missing_inputs() -> None:
    manifest = _manifest()
    manifest = replace(
        manifest,
        references=replace(
            manifest.references,
            overview_task_key="",
            agiletest_execution_key="",
        ),
    )
    bundle = build_regression_artifact_publication_bundle(
        _request(
            manifest=manifest,
            evidence_path="",
            focused_result_summary="",
            full_result_summary="",
        )
    )

    assert {warning.warning_type for warning in bundle.warnings} == {
        PublicationReadinessWarningType.MISSING_OVERVIEW_TASK,
        PublicationReadinessWarningType.MISSING_TEST_EXECUTION_REFERENCE,
        PublicationReadinessWarningType.MISSING_EVIDENCE_PATH,
        PublicationReadinessWarningType.MISSING_FOCUSED_RESULT_SUMMARY,
        PublicationReadinessWarningType.MISSING_FULL_RESULT_SUMMARY,
    }
    assert bundle.publication_request is None
    assert not bundle.ready_for_publication


def test_bundle_is_not_ready_when_warning_state_still_has_link_actions() -> None:
    manifest = _manifest()

    bundle = build_regression_artifact_publication_bundle(
        _request(
            manifest=manifest,
            evidence_path="",
            focused_result_summary="Focused regression passed: 12 passed.",
            full_result_summary="Full suite passed: 410 passed.",
        )
    )

    assert bundle.publication_request is not None
    assert PublicationReadinessWarningType.MISSING_EVIDENCE_PATH in {
        warning.warning_type for warning in bundle.warnings
    }
    assert not bundle.ready_for_publication


def test_bundle_renders_dry_run_output() -> None:
    manifest = _manifest()
    bundle = build_regression_artifact_publication_bundle(
        _request(manifest=manifest)
    )

    markdown = render_regression_artifact_publication_bundle(bundle)

    assert "# Regression Artifact Publication - REGRESSION-S10" in markdown
    assert "- Overview Task: AGENT-239" in markdown
    assert "- Test Execution: AGENT-335" in markdown
    assert "- Link -> AGENT-239 -> AGENT-335 (AgileTest)" in markdown
    assert "- None" in markdown.split("## Warnings", 1)[1]


def _manifest(*, overview_key: str = "AGENT-239", execution_key: str = "AGENT-335"):
    return build_regression_manifest(
        manifest_key="REGRESSION-S10",
        release_key="release-mvp",
        source_sprint="mvp-sprint-10",
        generated_at="2026-07-06T14:00:00Z",
        references=RegressionManifestReferences(
            overview_task_key=overview_key,
            agiletest_execution_key=execution_key,
        ),
        records=(
            build_regression_manifest_record(
                test_issue=classify_test_issue(
                    test_issue_key="AGENT-401",
                    summary="Regression overview publication",
                    covered_issue_key="AGENT-133",
                    classifications=(RegressionClassification.RELEASE_REGRESSION,),
                    existing_labels=("release-regression",),
                ),
                source_sprint="mvp-sprint-10",
                execution_mode=RegressionExecutionMode.MANUAL,
                result=RegressionExecutionResult.PASSED,
                evidence_path="data/agent-logs/REGRESSION-S10/story-1.md",
            ),
            build_regression_manifest_record(
                test_issue=classify_test_issue(
                    test_issue_key="AGENT-402",
                    summary="Evidence helper publication",
                    covered_issue_key="AGENT-134",
                    classifications=(RegressionClassification.AUTOMATED_COVERED,),
                    existing_labels=("automated-covered",),
                ),
                source_sprint="mvp-sprint-10",
                execution_mode=RegressionExecutionMode.AUTOMATED,
                result=RegressionExecutionResult.PASSED,
                evidence_path="data/agent-logs/REGRESSION-S10/story-2.md",
                automated_reference=AutomatedCoverageReference(
                    command="PYTHONPATH=src python -m pytest tests/test_evidence_publication.py",
                    test_file="tests/test_evidence_publication.py",
                    test_function="test_publication_request_accepts_comments_attachments_and_links",
                ),
            ),
        ),
        include_one_time_validations=False,
    )


def _request(
    *,
    manifest,
    evidence_path: str = "data/agent-logs/REGRESSION-S10/regression-evidence.md",
    focused_result_summary: str = "Focused regression passed: 12 passed.",
    full_result_summary: str = "Full suite passed: 410 passed.",
    upsert_plan=None,
):
    from agentic_boilerplate.domain import RegressionArtifactPublicationRequest

    return RegressionArtifactPublicationRequest(
        manifest=manifest,
        evidence_path=evidence_path,
        focused_result_summary=focused_result_summary,
        full_result_summary=full_result_summary,
        mode=EvidencePublicationMode.DRY_RUN,
        test_execution_upsert_plan=upsert_plan,
    )
