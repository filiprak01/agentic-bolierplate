# Review Agent Queue Report

Status: implemented for `AP-35`

The Review Agent queue report gives reviewers a single readiness view before
starting a pull request review. It is a pre-review triage artifact, not a
replacement for diff-first review.

## Purpose

The report reduces manual assembly across Jira and GitHub by listing:

1. Open pull requests that reference Jira stories, bugs, or tasks.
2. Jira status and issue type for each referenced issue.
3. Pull request draft, mergeability, base branch, head branch, and checks.
4. Dependency blockers and downstream blocked work.
5. Development subtask completion state.
6. Durable evidence and implementation-map links.
7. Blockers that must be resolved before review starts.
8. Recommended next owner when the Review Agent should not continue.

## Review-Ready Criteria

A target-project pull request is review-ready when:

1. The PR is open and not draft.
2. The PR title, branch, body, or linked Jira issue clearly references the Jira
   key.
3. The Jira issue is a Story, Bug, or Task in `IN PROGRESS` or
   `DEV COMPLETED`.
4. Dependency links do not show unresolved prerequisite blockers.
5. Development subtasks are completed, have implementation handoff notes, or
   the parent Jira handoff names an approved no-subtask exception.
6. Required remote GitHub checks are successful for the current PR head and
   tested merge ref/base. Local validation evidence is supplemental only and
   never clears missing, unreadable, stale, pending, cancelled, or failing
   remote CI/CD checks.
7. Durable evidence paths or implementation maps are visible.

The Review Agent still reviews the diff first after the queue report marks an
item as eligible.

## Process Repository Boundary

The target product repository and the boilerplate process repository have
separate ownership.

For target-project PRs, Review Agent may perform the normal review and merge
flow when the PR is clean.

For boilerplate/process repository PRs, this Review Agent only verifies that
the process PR exists, is non-draft, and is traceable. The report should mark
the next owner as the process-review or merge owner. This avoids self-merging
process changes that came from the same role's retro input.

## Retro Follow-Up Visibility

Retro follow-up stories that change process docs, code, automation, tests, or
configuration are not complete merely because a retro item exists. The report
flags them until:

1. The story is in executable Jira status.
2. Development subtasks exist and are completed or include handoff notes, unless
   the parent Jira handoff names an approved no-subtask exception.
3. A branch and pull request reference the Jira key.
4. Validation evidence is recorded.
5. The owning review or process-review agent completes the PR flow.

This keeps retro improvements visible as normal development work instead of
letting them drift as unreviewed process notes.

## Remote CI/CD Gate

The queue report must read GitHub checks or workflow runs for the exact PR head
SHA and base context being reviewed. A PR with no workflow runs and no combined
status is `checks-missing`, even when local validation evidence exists. A
provider, connector, token, or permission failure that prevents reading checks
is also blocking and must be reported as a credential/provider diagnostic.

The report must not approve or mark ready when:

1. GitHub Actions did not trigger for the PR.
2. The commit has no combined status and no workflow run for the reviewed SHA.
3. Checks are pending, queued, skipped without an explicit not-applicable rule,
   cancelled, timed out, failed, or stale.
4. The PR branch is behind the base and needs a refresh.
5. GitHub reports a merge conflict or cannot compute a clean merge state.

Local validation output can explain what the Developer Agent already ran, but
it is not remote CI proof. Review Agent may use it to route the next owner or
failure recovery, not to clear the CI/CD gate.

## Blocker Types

The report highlights these blockers before review starts:

1. `missing-jira-key` - the PR cannot be traced to a Jira issue.
2. `missing-jira-link` - the Jira issue does not visibly reference the PR.
3. `draft-pr` - the PR is still a draft.
4. `wrong-jira-status` - the Jira issue is not in a review-shaped status.
5. `unsupported-issue-type` - the issue is a subtask, Epic, Test, or another
   type the Review Agent should not pick directly.
6. `dependency-blocked` - Jira links show unresolved prerequisite blockers.
7. `subtasks-incomplete` - development subtasks are incomplete and lack handoff
   notes.
8. `checks-failed` - at least one required remote GitHub check failed.
9. `checks-pending` - checks are still running or queued.
10. `checks-missing` - remote GitHub checks or workflow runs are absent,
    unreadable, stale, or not triggered for the reviewed revision.
11. `stale-base` - the PR branch is behind or was reviewed against an old base
    and must be updated before CI/review can be trusted.
12. `merge-conflict` - GitHub reports the PR is not mergeable cleanly.
13. `process-repo-handoff` - the PR belongs to the process repo and should be
    routed to the process-review or merge owner.

## Recommended Output

The queue report should render a concise Markdown table for scanning and a
blocker section for action:

```text
| Jira | Status | PR | Repo | Branch | Checks | Blockers | Next owner |
```

Each blocker entry should be actionable and should name whether the Developer,
Tester, Release Manager, Product Owner, or process-review owner should act next.

## Evidence

When the queue report changes review routing, save the report or a summary
under:

```text
data/agent-logs/<JIRA_KEY>/review/
```

For queue-wide scans, use the current sprint or support task key when a single
story key is not enough.
