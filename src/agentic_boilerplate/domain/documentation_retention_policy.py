"""Documentation retention and archive policy decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DocumentationArtifactKind(str, Enum):
    """Documentation artifact classes used for repo slimming decisions."""

    SHARED_SOURCE = "shared_source"
    ROLE_NOTE = "role_note"
    REPORT_ARTIFACT = "report_artifact"
    RAW_LOG = "raw_log"
    GENERATED_SITE = "generated_site"
    CONTEXT_PACK = "context_pack"
    RELEASE_PACKAGE = "release_package"
    CREDENTIAL_OR_SECRET = "credential_or_secret"


class DocumentationRetentionDisposition(str, Enum):
    """Allowed retention outcomes for documentation-like files."""

    KEEP_IN_REPO = "keep_in_repo"
    PUBLISH_TO_GITHUB_PAGES = "publish_to_github_pages"
    ARCHIVE_TO_OPTIONAL_PROVIDER = "archive_to_optional_provider"
    LOCAL_DURABLE_ONLY = "local_durable_only"
    REDACT_OR_GITIGNORE = "redact_or_gitignore"


@dataclass(frozen=True)
class DocumentationRetentionInput:
    """Input facts for one documentation retention decision."""

    path: str
    artifact_kind: DocumentationArtifactKind
    approved: bool
    contains_secret: bool = False
    partner_visible: bool = False
    release_relevant: bool = False
    optional_archive_enabled: bool = False


@dataclass(frozen=True)
class DocumentationRetentionDecision:
    """A deterministic decision for where a documentation artifact belongs."""

    path: str
    disposition: DocumentationRetentionDisposition
    repo_allowed: bool
    publish_allowed: bool
    optional_archive_allowed: bool
    recommended_target: str
    reason: str


def decide_documentation_retention(
    item: DocumentationRetentionInput,
) -> DocumentationRetentionDecision:
    """Return the repo, publication, and archive decision for one artifact."""

    _require_path(item.path)
    if item.contains_secret or item.artifact_kind is DocumentationArtifactKind.CREDENTIAL_OR_SECRET:
        return DocumentationRetentionDecision(
            path=item.path,
            disposition=DocumentationRetentionDisposition.REDACT_OR_GITIGNORE,
            repo_allowed=False,
            publish_allowed=False,
            optional_archive_allowed=False,
            recommended_target="secure local secret store or redacted summary",
            reason="secrets and credentials must not be committed or published",
        )

    if item.artifact_kind is DocumentationArtifactKind.RAW_LOG:
        return DocumentationRetentionDecision(
            path=item.path,
            disposition=DocumentationRetentionDisposition.LOCAL_DURABLE_ONLY,
            repo_allowed=False,
            publish_allowed=False,
            optional_archive_allowed=False,
            recommended_target="durable local log storage",
            reason="raw command output is noisy evidence and stays local unless summarized",
        )

    if item.artifact_kind is DocumentationArtifactKind.ROLE_NOTE:
        return DocumentationRetentionDecision(
            path=item.path,
            disposition=DocumentationRetentionDisposition.LOCAL_DURABLE_ONLY,
            repo_allowed=False,
            publish_allowed=False,
            optional_archive_allowed=False,
            recommended_target="project-scoped durable role notes",
            reason="role-specific notes are not approved shared truth",
        )

    if item.artifact_kind is DocumentationArtifactKind.GENERATED_SITE:
        return DocumentationRetentionDecision(
            path=item.path,
            disposition=DocumentationRetentionDisposition.REDACT_OR_GITIGNORE,
            repo_allowed=False,
            publish_allowed=False,
            optional_archive_allowed=False,
            recommended_target="generated site output ignored by Git",
            reason="generated site output is rebuildable from approved Markdown",
        )

    if item.artifact_kind is DocumentationArtifactKind.REPORT_ARTIFACT:
        if item.approved and (item.partner_visible or item.release_relevant):
            return DocumentationRetentionDecision(
                path=item.path,
                disposition=DocumentationRetentionDisposition.PUBLISH_TO_GITHUB_PAGES,
                repo_allowed=True,
                publish_allowed=True,
                optional_archive_allowed=item.optional_archive_enabled,
                recommended_target="docs/reports/",
                reason="approved report artifacts are PO-reviewable release evidence",
            )
        return DocumentationRetentionDecision(
            path=item.path,
            disposition=DocumentationRetentionDisposition.LOCAL_DURABLE_ONLY,
            repo_allowed=False,
            publish_allowed=False,
            optional_archive_allowed=False,
            recommended_target="durable local evidence storage",
            reason="draft reports stay local until approved for release or partner visibility",
        )

    if item.artifact_kind is DocumentationArtifactKind.CONTEXT_PACK:
        if item.release_relevant and item.approved:
            return DocumentationRetentionDecision(
                path=item.path,
                disposition=DocumentationRetentionDisposition.KEEP_IN_REPO,
                repo_allowed=True,
                publish_allowed=False,
                optional_archive_allowed=item.optional_archive_enabled,
                recommended_target="docs/context-packs/ or configured context-pack mirror",
                reason="approved release context packs can stay as durable AI worker inputs",
            )
        return DocumentationRetentionDecision(
            path=item.path,
            disposition=DocumentationRetentionDisposition.LOCAL_DURABLE_ONLY,
            repo_allowed=False,
            publish_allowed=False,
            optional_archive_allowed=False,
            recommended_target="durable local context-pack storage",
            reason="working context packs are generated data and should not bloat the repo",
        )

    if item.artifact_kind is DocumentationArtifactKind.RELEASE_PACKAGE:
        return DocumentationRetentionDecision(
            path=item.path,
            disposition=DocumentationRetentionDisposition.PUBLISH_TO_GITHUB_PAGES,
            repo_allowed=True,
            publish_allowed=item.approved,
            optional_archive_allowed=item.optional_archive_enabled,
            recommended_target="docs/release-notes/ and docs/reports/",
            reason="release packages are traceability artifacts once approved",
        )

    if item.artifact_kind is DocumentationArtifactKind.SHARED_SOURCE:
        return DocumentationRetentionDecision(
            path=item.path,
            disposition=DocumentationRetentionDisposition.KEEP_IN_REPO,
            repo_allowed=True,
            publish_allowed=item.approved,
            optional_archive_allowed=item.optional_archive_enabled,
            recommended_target="docs/",
            reason="approved shared Markdown remains the editable documentation source",
        )

    raise ValueError(f"Unsupported documentation artifact kind: {item.artifact_kind}")


def _require_path(path: str) -> None:
    if not path or not path.strip():
        raise ValueError("path is required")
