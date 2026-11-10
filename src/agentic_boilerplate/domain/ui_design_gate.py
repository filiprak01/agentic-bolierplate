"""Machine-checkable UI design gate policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


ACCEPTED_DESIGN_STATUSES = ("TEST COMPLETED", "ACCEPTED/DONE")


class UIDesignGateBlockerKind(str, Enum):
    """Reasons a UI implementation story cannot start."""

    MISSING_DESIGN_STORY = "missing_design_story"
    MISSING_ARTIFACT = "missing_artifact"
    MISSING_PO_ACCEPTANCE = "missing_po_acceptance"
    MISSING_BLOCKS_DEPENDENCY = "missing_blocks_dependency"
    DESIGN_NOT_ACCEPTED = "design_not_accepted"
    INCOMPLETE_PO_OVERRIDE = "incomplete_po_override"


@dataclass(frozen=True)
class UIDesignReference:
    """Design reference fields required by a UI implementation story."""

    implementation_issue_key: str
    design_issue_key: str = ""
    artifact_reference: str = ""
    po_acceptance_reference: str = ""
    constraints: str = ""
    design_status: str = ""
    blocks_dependency_linked: bool = False
    po_override_reference: str = ""
    po_override_reason: str = ""

    @property
    def has_po_override(self) -> bool:
        return bool(self.po_override_reference.strip() or self.po_override_reason.strip())


@dataclass(frozen=True)
class UIDesignGateBlocker:
    """One machine-readable design gate blocker."""

    kind: UIDesignGateBlockerKind
    field: str
    message: str


@dataclass(frozen=True)
class UIDesignGateDecision:
    """UI design gate pass/fail result."""

    implementation_issue_key: str
    passed: bool
    blockers: tuple[UIDesignGateBlocker, ...]
    reasons: tuple[str, ...]


def evaluate_ui_design_gate(reference: UIDesignReference) -> UIDesignGateDecision:
    """Evaluate whether a frontend implementation story can start."""

    blockers: list[UIDesignGateBlocker] = []
    if reference.has_po_override:
        if not reference.po_override_reference.strip() or not reference.po_override_reason.strip():
            blockers.append(
                _blocker(
                    UIDesignGateBlockerKind.INCOMPLETE_PO_OVERRIDE,
                    "po_override",
                    "PO override requires both reference and reason.",
                )
            )
        return _decision(reference, blockers, override=True)

    if not reference.design_issue_key.strip():
        blockers.append(
            _blocker(
                UIDesignGateBlockerKind.MISSING_DESIGN_STORY,
                "design_issue_key",
                "UI implementation requires a paired design story.",
            )
        )
    if not reference.artifact_reference.strip():
        blockers.append(
            _blocker(
                UIDesignGateBlockerKind.MISSING_ARTIFACT,
                "artifact_reference",
                "UI implementation requires a design artifact link or path.",
            )
        )
    if not reference.po_acceptance_reference.strip():
        blockers.append(
            _blocker(
                UIDesignGateBlockerKind.MISSING_PO_ACCEPTANCE,
                "po_acceptance_reference",
                "UI implementation requires Product Owner design acceptance.",
            )
        )
    if not reference.blocks_dependency_linked:
        blockers.append(
            _blocker(
                UIDesignGateBlockerKind.MISSING_BLOCKS_DEPENDENCY,
                "blocks_dependency_linked",
                "Design story must block the UI implementation story in Jira.",
            )
        )
    if not _accepted_status(reference.design_status):
        blockers.append(
            _blocker(
                UIDesignGateBlockerKind.DESIGN_NOT_ACCEPTED,
                "design_status",
                "Design story must be TEST COMPLETED or ACCEPTED/DONE before frontend starts.",
            )
        )
    return _decision(reference, blockers, override=False)


def render_design_reference_section(reference: UIDesignReference) -> str:
    """Render the Jira description section for a UI implementation story."""

    return "\n".join(
        (
            "Design Reference:",
            f"- Design story: {reference.design_issue_key or 'TBD'}",
            f"- Artifact: {reference.artifact_reference or 'TBD'}",
            f"- Product Owner acceptance: {reference.po_acceptance_reference or 'TBD'}",
            f"- Constraints: {reference.constraints or 'TBD'}",
            f"- PO override: {reference.po_override_reference or 'none'}",
            f"- PO override reason: {reference.po_override_reason or 'none'}",
        )
    )


def render_ui_design_gate_decision(decision: UIDesignGateDecision) -> str:
    """Render a PO-visible design gate decision."""

    lines = [
        f"# UI Design Gate - {decision.implementation_issue_key}",
        "",
        f"- Passed: {'yes' if decision.passed else 'no'}",
        "",
        "## Reasons",
    ]
    lines.extend(f"- {reason}" for reason in decision.reasons)
    lines.extend(["", "## Blockers"])
    if decision.blockers:
        lines.extend(f"- {blocker.kind.value}: {blocker.message}" for blocker in decision.blockers)
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _decision(
    reference: UIDesignReference,
    blockers: list[UIDesignGateBlocker],
    *,
    override: bool,
) -> UIDesignGateDecision:
    passed = not blockers
    if passed and override:
        reasons = (f"{reference.implementation_issue_key} can start from explicit PO design override.",)
    elif passed:
        reasons = (f"{reference.implementation_issue_key} has an accepted design reference.",)
    else:
        reasons = tuple(blocker.message for blocker in blockers)
    return UIDesignGateDecision(
        implementation_issue_key=reference.implementation_issue_key,
        passed=passed,
        blockers=tuple(blockers),
        reasons=reasons,
    )


def _blocker(kind: UIDesignGateBlockerKind, field: str, message: str) -> UIDesignGateBlocker:
    return UIDesignGateBlocker(kind=kind, field=field, message=message)


def _accepted_status(status: str) -> bool:
    normalized = _normalize_status(status)
    return normalized in {_normalize_status(item) for item in ACCEPTED_DESIGN_STATUSES}


def _normalize_status(status: str) -> str:
    return " ".join(status.replace("/", " / ").split()).casefold()
