# Review Agent PR Workflow

The Review Agent PR workflow decides whether a developer pull request is ready
to merge when merge ownership belongs to Review Agent.

Queue triage before selecting a pull request is documented in
`docs/review-agent-queue-report.md`.

## Default Scope

Review starts as `diff-first`.
Session-mode validation for the Developer, Review, Tester, and Release Manager
chain is documented in `docs/session-mode-delivery-flow-validation.md`.

The Review Agent inspects:

1. Pull request diff summary.
2. Changed files.
3. Related tests.
4. Directly touched contracts.
5. Story acceptance criteria.
6. Developer-created subtasks and completion notes, or the approved no-subtask
   exception named in the Jira handoff.

Developer Agent pull requests are expected to be non-draft by default. A draft
pull request is reviewable only when the Jira handoff names an explicit
Product Owner, Jira, or documented-process draft exception and describes the
condition that will make the pull request ready.

## CI Quality Gate

Before approval and merge, follow [CI Quality Gate](ci-quality-gate.md).
Verify the `CI` workflow's `Pytest` and `Docker Compose` checks for the current
reviewed revision and base, together with other applicable required checks.
Missing, incomplete, failing, cancelled, unreadable, skipped-without-reason, or
stale CI evidence blocks merge.

A pull request with no GitHub workflow runs and no combined commit status for
the reviewed head SHA is `checks-missing`. Local validation evidence can support
failure recovery, but it cannot clear this blocker or authorize approval,
approval-comment fallback, or merge. If GitHub or the connector cannot read CI
because of token, permission, provider, or Actions approval state, record a
provider diagnostic and block review.

Link or summarize observed CI output in the durable review record's testing
finding, including the CI run URL, run attempt, reviewed head SHA, tested
ref/SHA, base branch/SHA, and check conclusions. Keep unverified evidence open
and blocking; local validation is not proof of remote CI success. The linked
guide covers Compose not-applicable results, artifacts, offline commands, and
recovery.

## Expanded Context

Expanded context requires at least one explicit reason:

1. `architecture`
2. `security`
3. `data-model`
4. `shared-contract`
5. `dependency-direction`
6. `repeated-finding`

The review record stores the inspected context paths and the reason.

## Findings

Open findings block merge readiness.

Blocking conflict findings are review findings, not product bugs. The Review
Agent sends them back to the Developer Agent through the review record and Jira
comment.

## Jira Visibility

Before merge, the Review Agent verifies that the Jira story has a visible pull
request link or records a finding.

Before review starts, the Review Agent should use the queue report guidance to
check Jira status, dependencies, subtask completion or approved no-subtask
exception, checks, evidence links, and process-repository handoff boundaries.

The Review Agent also verifies that the pull request scope does not contain
unrelated staged or pushed files. If unrelated files are detected, review must
request changes instead of silently merging the PR.

After merge, the Review Agent prepares a Jira comment with:

1. Pull request URL.
2. Merge SHA.
3. Merge result.
4. Next Jira status: `DEV COMPLETED`.
5. Handoff message: `test_requested`.

Review Agent does not move the story to `IN TESTING`. The canonical route in
`docs/story-processing-path-matrix.md` keeps the story in `DEV COMPLETED` after
merge and makes Tester Agent responsible for moving it to `IN TESTING` when
validation starts.

## Approval Publication Fallback

When GitHub accepts a formal approval review, Review Agent records the approval
publication mode as `formal-review`.

If GitHub rejects formal approval publication, for example with HTTP `422`,
Review Agent may publish the approval summary as a pull request comment
fallback only after CI, findings, dependencies, Jira visibility, and merge
ownership gates are all clean. The fallback is not silent: Review Agent records
and publishes a diagnostic status with:

1. Jira issue key.
2. Pull request URL.
3. Review record id.
4. Publication mode: `formal-review`, `comment-fallback`, or `failed`.
5. Provider status code and message when available.
6. Whether the approval was visibly published.

If both formal approval and comment fallback fail, Review Agent must not pretend
the PR was approved. It records `failed`, reports the credential/provider
diagnostic, and blocks merge until the publication path is visible.

## Stacked Pull Requests

When a pull request includes stacked PR metadata from the context pack or
developer handoff, Review Agent must review the layer diff-first against the
configured base branch for that layer.

Before approval, Review Agent verifies:

1. Stack id, lane id, layer number, trunk, context pack path, reviewed base SHA,
   and reviewed head SHA are present.
2. The Jira story has a visible pull request link.
3. The pull request base branch matches the stack resolver output.
4. Required checks are complete and passing.
5. For upper layers, the required lower-layer approval exists.
6. No merge conflicts or stale lower-layer SHA changes require Developer Agent
   rebase work.

Approval readiness and merge readiness are separate decisions. Upper layers may
receive early review comments after their lower layer is approved, but they are
not merge-ready until lower layers merge unless the repository has a configured
merge queue and branch protection supports safe queued stack merge.

Review comments must distinguish:

1. `layer-local` findings that belong to the current PR layer.
2. `lower-layer-change` findings caused by a changed lower layer.

When a lower-layer reviewed SHA no longer matches the current lower-layer SHA,
Review Agent marks the upper layer `stale-rebase-required` and reports the work
back to the owning Developer Agent. Review Agent does not resolve stacked merge
conflicts directly.

## Process Repository Ownership

Target-project implementation pull requests use the default Review Agent review
and merge lane after checks and findings pass.

Process-repository pull requests that change boilerplate workflow, role
instructions, CI, helper scripts, or release process may require a
process-review or release-manager merge owner. When the Jira story, handoff
comment, branch, or repository scope identifies that lane, Review Agent verifies
the diff-first review result and records the handoff, but does not silently
merge or close the pull request unless merge ownership is explicitly assigned to
Review Agent.

If ownership is ambiguous, Review Agent records a blocking finding and asks for
the owner to be documented in Jira before merge.

## Merge

When no open findings remain, the workflow prepares GitHub merge fields and the
Review Agent may merge through the configured GitHub adapter only when merge
ownership belongs to Review Agent.
