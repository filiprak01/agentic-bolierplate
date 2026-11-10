# Sprint Closure Publication Workflow

Release Manager uses this workflow to capture Sprint 11 retro, closure, and
sprint-performance artifacts in a visible Jira-backed publication task.

The workflow keeps closure notes and follow-up routing visible without hiding
process changes inside the repo.
Session-mode validation for the delivery chain that feeds sprint closure is
documented in `docs/session-mode-delivery-flow-validation.md`.
Active-sprint retro intake is defined in
`docs/active-sprint-retro-intake-workflow.md`.

Evidence channel and redaction rules are governed by
`docs/shared-evidence-publication-policy.md`.

## Inputs

The closure plan uses:

1. Sprint name.
2. Publication task key.
3. Retro note path.
4. Closure note path.
5. Sprint performance path.
6. Regression result summary.
7. PO acceptance summary.
8. Sprint fit summary.
9. Follow-up backlog story keys.
10. Changed repo files for closure artifacts.
11. Workspace closure readiness report path when parallel assignment
    workspaces were used.

## Outputs

The workflow produces:

1. A publication branch name.
2. A durable Markdown summary for Jira comments or local evidence.
3. A Jira-ready closure comment.
4. File decisions that distinguish publish-under-task changes from changes
   that require a separate Jira story.
5. Warnings when important closure inputs are missing.
6. Workspace cleanup readiness references for Release Manager verification.

## Closure Rules

1. Retro notes must exist even when no process changes are needed.
   When an active-sprint retro intake item exists, retro notes must be built
   from Product Owner-approved retro comments on that item.
2. Closure notes must record delivered scope, regression result, PO acceptance,
   and sprint fit.
3. Follow-up implementation items must become Jira backlog candidates instead
   of silent repo changes.
   Post-retro follow-up stories start in `FUNNEL` with `po-review-required`
   labels even when the Release Manager recommends a later sprint for
   visibility.
4. Repo changes for closure artifacts must stay linked to the closure task and
   be verified before sprint closure.
5. Code, automation, script, test, and configuration changes require a Jira
   story before branch creation.
6. When parallel assignment workspaces were used, Release Manager must publish
   or reference a workspace closure readiness report before closing the sprint
   or release. The report must show `can_close=true` or list stale/dirty/
   unpushed/unarchived workspace blockers that require recovery.

## Ready State

The closure publication is ready when the retrospective note, closure note,
sprint performance record, regression result, PO acceptance summary, sprint fit
summary, and any required workspace closure readiness report are all present.

If any of those inputs are missing, the workflow still renders a useful dry
run, but it stays in a warning state so the missing piece is visible.

Approved closure publication should produce a partner-safe GitHub Pages report
summary and a Jira comment with the Pages URL or dry-run artifact reference.
Raw logs, internal notes, source documents, and unredacted sensitive content
stay local-only unless the Product Owner approves otherwise.

Confluence publication is optional when the project documentation provider
selects Confluence or `both`. Optional Confluence output must link back to the
same Jira closure task and must not replace the GitHub Pages report record by
default.
