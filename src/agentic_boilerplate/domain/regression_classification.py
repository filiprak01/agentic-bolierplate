"""Regression classification and AgileTest mapping planning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentic_boilerplate.domain.tester_manual_test_workflow import RegressionClassification


DEFAULT_REGRESSION_CLASSIFICATION_LABELS: dict[RegressionClassification, str] = {
    RegressionClassification.ONE_TIME_VALIDATION: "one-time-validation",
    RegressionClassification.REGRESSION_CANDIDATE: "regression-candidate",
    RegressionClassification.SMOKE_REGRESSION: "smoke-regression",
    RegressionClassification.RELEASE_REGRESSION: "release-regression",
    RegressionClassification.AUTOMATED_CANDIDATE: "automated-candidate",
    RegressionClassification.AUTOMATED_COVERED: "automated-covered",
    RegressionClassification.MANUAL_ONLY: "manual-only",
}


class AgileTestArtifactType(str, Enum):
    """AgileTest artifact types that can be planned without live API access."""

    TEST_CASE = "test-case"
    TEST_CYCLE = "test-cycle"
    TEST_EXECUTION = "test-execution"


@dataclass(frozen=True)
class RegressionClassificationConfig:
    """Project-specific label mapping for regression classifications."""

    label_by_classification: dict[RegressionClassification, str]
    agiletest_enabled: bool = False


@dataclass(frozen=True)
class ClassifiedTestIssue:
    """Classified Jira Test issue used for release regression planning."""

    test_issue_key: str
    summary: str
    covered_issue_key: str
    classifications: tuple[RegressionClassification, ...]
    labels: tuple[str, ...]
    agiletest_case_key: str = ""


@dataclass(frozen=True)
class ReleaseRegressionScopeQuery:
    """Query input for finding Test issues relevant to a sprint or release."""

    project_key: str
    release_label: str
    sprint_label: str = ""
    classification_filters: tuple[RegressionClassification, ...] = ()
    include_one_time_validations: bool = False


@dataclass(frozen=True)
class AgileTestMappingConfig:
    """Optional AgileTest mapping settings."""

    enabled: bool
    test_case_issue_type: str = "Test"
    test_cycle_issue_type: str = "Test cycle"
    test_execution_issue_type: str = "Test execution"
    link_type: str = "AgileTest"
    outward_relationship: str = "tests"


@dataclass(frozen=True)
class AgileTestArtifactMapping:
    """Planned AgileTest artifact mapping for one Test issue."""

    artifact_type: AgileTestArtifactType
    source_test_issue_key: str
    target_issue_type: str
    covered_issue_key: str
    link_type: str
    outward_relationship: str


@dataclass(frozen=True)
class AgileTestMappingPlan:
    """AgileTest mapping plan that can be executed by an integration layer."""

    enabled: bool
    mappings: tuple[AgileTestArtifactMapping, ...]
    warnings: tuple[str, ...] = ()


class RegressionClassificationError(ValueError):
    """Raised when regression classification input is invalid."""


def default_regression_classification_config(
    *,
    agiletest_enabled: bool = False,
) -> RegressionClassificationConfig:
    """Return default label mapping for all supported classifications."""

    return RegressionClassificationConfig(
        label_by_classification=dict(DEFAULT_REGRESSION_CLASSIFICATION_LABELS),
        agiletest_enabled=agiletest_enabled,
    )


def labels_for_regression_classifications(
    classifications: tuple[RegressionClassification, ...],
    config: RegressionClassificationConfig | None = None,
) -> tuple[str, ...]:
    """Return configured Jira labels for regression classifications."""

    config = config or default_regression_classification_config()
    _validate_config(config)
    _validate_classifications(classifications)
    return tuple(sorted({config.label_by_classification[classification] for classification in classifications}))


def classification_labels_for_regression_classifications(
    classifications: tuple[RegressionClassification, ...],
    config: RegressionClassificationConfig | None = None,
) -> tuple[str, ...]:
    """Return configured Jira labels for regression classifications."""

    return labels_for_regression_classifications(classifications, config)


def classify_test_issue(
    *,
    test_issue_key: str,
    summary: str,
    covered_issue_key: str,
    classifications: tuple[RegressionClassification, ...],
    existing_labels: tuple[str, ...] = (),
    config: RegressionClassificationConfig | None = None,
    agiletest_case_key: str = "",
) -> ClassifiedTestIssue:
    """Build a classified Test issue record with configured labels."""

    _require_text("test_issue_key", test_issue_key)
    _require_text("summary", summary)
    _require_text("covered_issue_key", covered_issue_key)
    labels = set(existing_labels)
    labels.update(labels_for_regression_classifications(classifications, config))
    return ClassifiedTestIssue(
        test_issue_key=test_issue_key.strip(),
        summary=summary.strip(),
        covered_issue_key=covered_issue_key.strip(),
        classifications=classifications,
        labels=tuple(sorted(label for label in labels if label.strip())),
        agiletest_case_key=agiletest_case_key.strip(),
    )


def build_release_regression_scope_query(
    *,
    project_key: str,
    release_label: str,
    sprint_label: str = "",
    classification_filters: tuple[RegressionClassification, ...] = (
        RegressionClassification.REGRESSION_CANDIDATE,
        RegressionClassification.SMOKE_REGRESSION,
        RegressionClassification.RELEASE_REGRESSION,
    ),
    include_one_time_validations: bool = False,
) -> ReleaseRegressionScopeQuery:
    """Build query input for Release Manager regression scope lookup."""

    _require_text("project_key", project_key)
    _require_text("release_label", release_label)
    _validate_classifications(classification_filters)
    if (
        RegressionClassification.ONE_TIME_VALIDATION in classification_filters
        and not include_one_time_validations
    ):
        raise RegressionClassificationError(
            "include_one_time_validations must be true when filtering one-time validations"
        )
    return ReleaseRegressionScopeQuery(
        project_key=project_key.strip(),
        release_label=release_label.strip(),
        sprint_label=sprint_label.strip(),
        classification_filters=classification_filters,
        include_one_time_validations=include_one_time_validations,
    )


def regression_scope_query_to_jql(
    query: ReleaseRegressionScopeQuery,
    config: RegressionClassificationConfig | None = None,
) -> str:
    """Render a Jira JQL fragment for classified Test issue lookup."""

    config = config or default_regression_classification_config()
    _validate_config(config)
    _require_text("query.project_key", query.project_key)
    _require_text("query.release_label", query.release_label)
    labels = [query.release_label]
    if query.sprint_label:
        labels.append(query.sprint_label)
    labels.extend(labels_for_regression_classifications(query.classification_filters, config))
    if not query.include_one_time_validations:
        labels = [label for label in labels if label != config.label_by_classification[RegressionClassification.ONE_TIME_VALIDATION]]
    label_clause = ", ".join(f'"{label}"' for label in sorted(set(labels)))
    return f'project = {query.project_key} AND issuetype = Test AND labels in ({label_clause}) ORDER BY key ASC'


def build_agiletest_mapping_plan(
    *,
    classified_tests: tuple[ClassifiedTestIssue, ...],
    config: AgileTestMappingConfig,
) -> AgileTestMappingPlan:
    """Plan AgileTest mapping operations without requiring live AgileTest access."""

    if not config.enabled:
        return AgileTestMappingPlan(
            enabled=False,
            mappings=(),
            warnings=("AgileTest mapping is disabled for this project.",),
        )
    mappings: list[AgileTestArtifactMapping] = []
    warnings: list[str] = []
    for test in classified_tests:
        _validate_classified_test_issue(test)
        if RegressionClassification.ONE_TIME_VALIDATION in test.classifications:
            warnings.append(f"{test.test_issue_key} is one-time validation and is not mapped by default.")
            continue
        mappings.append(
            AgileTestArtifactMapping(
                artifact_type=AgileTestArtifactType.TEST_CASE,
                source_test_issue_key=test.test_issue_key,
                target_issue_type=config.test_case_issue_type,
                covered_issue_key=test.covered_issue_key,
                link_type=config.link_type,
                outward_relationship=config.outward_relationship,
            )
        )
    return AgileTestMappingPlan(enabled=True, mappings=tuple(mappings), warnings=tuple(warnings))


def regression_classification_config_to_dict(config: RegressionClassificationConfig) -> dict[str, Any]:
    """Convert classification config to JSON-compatible data."""

    _validate_config(config)
    return {
        "label_by_classification": {
            classification.value: label for classification, label in config.label_by_classification.items()
        },
        "agiletest_enabled": config.agiletest_enabled,
    }


def regression_classification_config_from_dict(data: dict[str, Any]) -> RegressionClassificationConfig:
    """Build classification config from JSON-compatible data."""

    raw_mapping = data.get("label_by_classification")
    if not isinstance(raw_mapping, dict):
        raise RegressionClassificationError("label_by_classification is required")
    config = RegressionClassificationConfig(
        label_by_classification={
            RegressionClassification(str(key)): _optional_text(value) for key, value in raw_mapping.items()
        },
        agiletest_enabled=bool(data.get("agiletest_enabled")),
    )
    _validate_config(config)
    return config


def _validate_config(config: RegressionClassificationConfig) -> None:
    missing = set(RegressionClassification) - set(config.label_by_classification)
    if missing:
        names = ", ".join(sorted(classification.value for classification in missing))
        raise RegressionClassificationError(f"label mapping missing classifications: {names}")
    for classification, label in config.label_by_classification.items():
        if not isinstance(classification, RegressionClassification):
            raise RegressionClassificationError("label_by_classification keys must be RegressionClassification")
        _require_text(f"label_by_classification[{classification.value}]", label)


def _validate_classifications(classifications: tuple[RegressionClassification, ...]) -> None:
    if not classifications:
        raise RegressionClassificationError("at least one regression classification is required")
    for classification in classifications:
        if not isinstance(classification, RegressionClassification):
            raise RegressionClassificationError("classifications must be RegressionClassification values")


def _validate_classified_test_issue(test: ClassifiedTestIssue) -> None:
    _require_text("test_issue_key", test.test_issue_key)
    _require_text("summary", test.summary)
    _require_text("covered_issue_key", test.covered_issue_key)
    _validate_classifications(test.classifications)


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegressionClassificationError(f"{name} is required")
    return value.strip()
