"""Policy helpers for story-backed and process-documentation changes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StoryBackedChangeSurface(str, Enum):
    """Supported change surfaces for Jira-backed and process-doc work."""

    PRODUCT_BEHAVIOR = "product-behavior"
    CODE_CHANGE = "code-change"
    CONFIGURATION_CHANGE = "configuration-change"
    DOCUMENTATION_ONLY = "documentation-only"
    PROCESS_DOCUMENTATION = "process-documentation"


@dataclass(frozen=True)
class StoryBackedChangePolicyDecision:
    """Policy decision describing required ceremony for one change surface."""

    change_surface: StoryBackedChangeSurface
    jira_story_required: bool
    dedicated_branch_required: bool
    review_required: bool
    affects_boilerplate_behavior: bool
    validation_steps: tuple[str, ...]


@dataclass(frozen=True)
class GitHubValidationFallbackDecision:
    """Decision for Jira-visible PR traceability when GitHub validation is weak."""

    jira_issue_key: str
    pull_request_url: str
    fallback_required: bool
    validation_visible: bool
    reasons: tuple[str, ...] = ()
    jira_comment: str = ""


DEFAULT_DOCUMENTATION_VALIDATION_STEPS = (
    "Verify referenced markdown paths exist.",
    "Inspect updated markdown for sprint, Jira, and PR references.",
)

DEFAULT_PROCESS_DOCUMENTATION_VALIDATION_STEPS = (
    "Verify referenced markdown paths exist.",
    "Inspect updated markdown for sprint, retro, closure, and related Jira references.",
)


def build_story_backed_change_policy_decision(
    change_surface: StoryBackedChangeSurface,
) -> StoryBackedChangePolicyDecision:
    """Return the default policy contract for one change surface."""

    if change_surface == StoryBackedChangeSurface.DOCUMENTATION_ONLY:
        return StoryBackedChangePolicyDecision(
            change_surface=change_surface,
            jira_story_required=False,
            dedicated_branch_required=True,
            review_required=True,
            affects_boilerplate_behavior=False,
            validation_steps=DEFAULT_DOCUMENTATION_VALIDATION_STEPS,
        )
    if change_surface == StoryBackedChangeSurface.PROCESS_DOCUMENTATION:
        return StoryBackedChangePolicyDecision(
            change_surface=change_surface,
            jira_story_required=False,
            dedicated_branch_required=True,
            review_required=True,
            affects_boilerplate_behavior=False,
            validation_steps=DEFAULT_PROCESS_DOCUMENTATION_VALIDATION_STEPS,
        )
    if change_surface == StoryBackedChangeSurface.CONFIGURATION_CHANGE:
        validation_steps = (
            "Run targeted configuration validation or startup checks.",
            "Attach durable validation evidence before PR creation.",
        )
    else:
        validation_steps = (
            "Run targeted developer validation for the changed behavior.",
            "Attach durable validation evidence before PR creation.",
        )
    return StoryBackedChangePolicyDecision(
        change_surface=change_surface,
        jira_story_required=True,
        dedicated_branch_required=True,
        review_required=True,
        affects_boilerplate_behavior=True,
        validation_steps=validation_steps,
    )


def build_process_change_branch_name(
    *,
    jira_issue_key: str = "",
    sprint_name: str = "",
    slug: str = "process-closure",
) -> str:
    """Build a deterministic branch name for docs/process-only updates."""

    normalized_slug = _normalize_branch_segment(slug)
    if jira_issue_key.strip():
        return f"process/{jira_issue_key.strip()}-{normalized_slug}"
    if sprint_name.strip():
        return f"docs/{_normalize_branch_segment(sprint_name)}-{normalized_slug}"
    raise ValueError("jira_issue_key or sprint_name is required for a process/documentation branch.")


def render_manual_jira_pr_visibility_fallback(
    *,
    jira_issue_key: str,
    pull_request_url: str,
    branch_name: str,
    commit_shas: tuple[str, ...],
    validation_paths: tuple[str, ...],
    related_jira_issue_keys: tuple[str, ...] = (),
    sprint_name: str = "",
    sprint_publication_task_key: str = "",
    change_surface: StoryBackedChangeSurface = StoryBackedChangeSurface.CODE_CHANGE,
    affects_boilerplate_behavior: bool = True,
    review_result: str = "pending review",
    merge_commit_sha: str = "",
) -> str:
    """Render a Jira-safe fallback comment when smart links are unavailable."""

    lines = [
        f"PR visibility fallback for {jira_issue_key}.",
        "",
        f"PR: {pull_request_url}",
        f"Branch: {branch_name}",
        f"Change surface: {change_surface.value}",
        f"Affects boilerplate behavior: {'yes' if affects_boilerplate_behavior else 'no'}",
    ]
    if sprint_name.strip():
        lines.append(f"Sprint: {sprint_name.strip()}")
    if sprint_publication_task_key.strip():
        lines.append(f"Sprint publication task: {sprint_publication_task_key.strip()}")
    if related_jira_issue_keys:
        lines.append(f"Related Jira: {', '.join(related_jira_issue_keys)}")
    lines.extend(["", "Commits:"])
    for commit_sha in commit_shas:
        lines.append(f"- {commit_sha}")
    lines.extend(["", "Validation evidence:"])
    for path in validation_paths:
        lines.append(f"- {path}")
    lines.extend(["", f"Review result: {review_result}"])
    if merge_commit_sha.strip():
        lines.append(f"Merge commit: {merge_commit_sha.strip()}")
    return "\n".join(lines).strip()


def plan_github_validation_fallback(
    *,
    jira_issue_key: str,
    pull_request_url: str,
    branch_name: str,
    commit_shas: tuple[str, ...],
    validation_paths: tuple[str, ...],
    github_validation_available: bool,
    jira_pr_link_visible: bool,
    manual_fallback_present: bool = False,
    related_jira_issue_keys: tuple[str, ...] = (),
    sprint_name: str = "",
    sprint_publication_task_key: str = "",
    change_surface: StoryBackedChangeSurface = StoryBackedChangeSurface.CODE_CHANGE,
    affects_boilerplate_behavior: bool = True,
    review_result: str = "pending review",
    merge_commit_sha: str = "",
) -> GitHubValidationFallbackDecision:
    """Plan the manual Jira fallback when GitHub/Jira validation cannot be trusted.

    The helper is intentionally transport-free. GitHub, Jira, or plugin callers
    provide the observed booleans, and this function returns the durable Jira
    comment only when a new manual fallback is still needed.
    """

    _require_non_blank("jira_issue_key", jira_issue_key)
    _require_non_blank("pull_request_url", pull_request_url)
    _require_non_blank("branch_name", branch_name)
    _require_non_blank_sequence("commit_shas", commit_shas)
    _require_non_blank_sequence("validation_paths", validation_paths)

    reasons: list[str] = []
    if not github_validation_available:
        reasons.append("github-validation-unavailable")
    if not jira_pr_link_visible:
        reasons.append("jira-pr-link-not-visible")
    if manual_fallback_present and reasons:
        reasons.append("manual-fallback-already-present")

    fallback_required = bool(reasons) and not manual_fallback_present
    validation_visible = (github_validation_available and jira_pr_link_visible) or manual_fallback_present
    jira_comment = ""
    if fallback_required:
        jira_comment = render_manual_jira_pr_visibility_fallback(
            jira_issue_key=jira_issue_key,
            pull_request_url=pull_request_url,
            branch_name=branch_name,
            commit_shas=commit_shas,
            validation_paths=validation_paths,
            related_jira_issue_keys=related_jira_issue_keys,
            sprint_name=sprint_name,
            sprint_publication_task_key=sprint_publication_task_key,
            change_surface=change_surface,
            affects_boilerplate_behavior=affects_boilerplate_behavior,
            review_result=review_result,
            merge_commit_sha=merge_commit_sha,
        )
    return GitHubValidationFallbackDecision(
        jira_issue_key=jira_issue_key.strip(),
        pull_request_url=pull_request_url.strip(),
        fallback_required=fallback_required,
        validation_visible=validation_visible,
        reasons=tuple(reasons),
        jira_comment=jira_comment,
    )


def _normalize_branch_segment(value: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in value.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")


def _require_non_blank(field: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field} is required for GitHub validation fallback planning.")


def _require_non_blank_sequence(field: str, values: tuple[str, ...]) -> None:
    if not values or any(not value.strip() for value in values):
        raise ValueError(f"{field} must include non-blank values for GitHub validation fallback planning.")
