# Parallel Agent Workspace Design

Status: Release 1.2 implementation baseline for `AGENT-634`.

This document defines how session-mode agents and future Docker workers can
work in parallel on different non-blocking stories without sharing one mutable
checkout. Release 1.1 documents and validates the model. Release 1.1 does not
implement detached live Codex execution inside Docker workers.

## Principle

Each active implementation, review, testing, or specialist assignment receives
one isolated project workspace. Shared state is limited to:

1. The boilerplate instruction bundle and workflow documentation.
2. Durable platform coordination folders.
3. External system records in Jira, GitHub, Confluence, AgileTest, and the PO
   inbox.

Parallel agents must not share one editable target-project checkout for
concurrent implementation work.

## Multi-Project Agent Pooling

Default recommendation for Product Owners: use pooled role capacity with
isolated assignments. One Developer pool, Tester pool, Orchestrator pool, or
specialist pool may serve multiple projects, but each worker handles exactly
one project-scoped assignment at a time.

Each pooled assignment must carry:

1. `project_id`
2. `project_name`
3. `project_root`
4. `repository`
5. `jira_project_key`
6. Jira issue key.
7. Context pack path.
8. Durable PO inbox namespace.
9. Isolated workspace path.

The worker may reuse shared role instructions, boilerplate process docs, and
platform coordination services. It must not reuse target-project assumptions,
credentials, unresolved PO answers, local paths, conversation memory, or repo
state from a previous project.

Before a pooled worker accepts a different project assignment, the scheduler
must verify that the previous assignment reached a durable stop point and that
project-specific context was released or reset. If reset cannot be proven, the
worker is not eligible for a different project.

Use dedicated per-project agents when:

1. The project is sensitive or has stricter confidentiality needs.
2. The architecture, credentials, compliance model, or deployment environment
   is unusual.
3. The work needs long-running Product Owner collaboration that would make
   frequent context reset expensive.
4. The client or partner requires strict operational separation.
5. The scheduler cannot prove that pooled-worker project context was reset.

## Workspace Allocation

The scheduler allocates a workspace after these gates pass:

1. Jira issue is in the approved sprint scope.
2. Product Owner moved the issue to `READY TO START`.
3. Dependency eligibility passed.
4. No unresolved linked Bug blocks the issue.
5. Assignment lock acquisition is allowed.
6. Codex limit availability allows the planned role/model route.
7. Predicted file-scope conflict risk is acceptable.

Recommended workspace root:

```text
{AGENTIC_WORKSPACES_ROOT}/{project_key}/{jira_issue_key}/{role}/
```

Example:

```text
data/agent-workspaces/AP/AP-42/developer/
```

The assignment record stores the workspace path, branch name, context pack
path, evidence path, output path, failed request path, and cleanup policy.

The executable planning contract is implemented in
`agentic_boilerplate.domain.assignment_workspace`. Scheduler and worker code
must use that planner before creating a workspace. The planner:

1. Allocates a deterministic isolated workspace path when the assignment does
   not already provide one.
2. Validates that mutating assignments have a matching
   `feature/{JIRA_KEY}-{short-slug}` branch.
3. Validates that required shared durable folders are present and stay outside
   the assignment workspace.
4. Fails safely with machine-readable blockers when the target repository,
   Git metadata, branch name, repository, or credentials are missing.
5. Produces a non-destructive command plan for Git worktree, fresh clone, or
   copied snapshot provisioning.

## Shared Durable Coordination Folders

Parallel workers may share these durable coordination folders:

1. `data/po-inbox`
2. `data/agent-logs`
3. `data/agent-state`
4. `data/codex-limits`
5. `data/codex-jobs`
6. `data/codex-results`
7. `data/context-packs`
8. `data/po-decisions`
9. `data/sprints`
10. `data/confluence-mirror`

These folders are coordination state. They are not mutable target-project
source code.

## Isolated Per-Worker Folders

Each active assignment owns:

1. Target project workspace, Git worktree, fresh clone, or copied snapshot.
2. Temporary tool output.
3. Assignment output path.
4. Assignment evidence path.
5. Failed request path.
6. Local dependency installs and build outputs for that workspace.

An agent writes source changes only inside its assigned workspace. It writes
durable evidence only to the assignment evidence path or role-approved durable
log path.

## Workspace Archive And Cleanup

Completed assignment workspaces must be archived before they are deleted,
parked, or reported as clean for sprint/release closure. The executable cleanup
contract is implemented in `agentic_boilerplate.domain.worktree_cleanup`.

Archive metadata records preserve:

1. Jira issue key and assignment id.
2. Agent role and workspace path.
3. Branch name, PR URL, Jira URL, and merge commit SHA.
4. Evidence paths and status paths.
5. Cleanup policy and archive timestamp.

Cleanup refuses unsafe workspaces by default:

1. Dirty workspaces with uncommitted changes are blocked.
2. Clean but unpushed branches are blocked.
3. Unmerged branches are kept.
4. Completed workspaces that have not been archived block sprint or release
   closure.
5. Active workspaces older than the stale threshold block closure until the
   operator or scheduler resolves them.

Release Manager uses the workspace closure readiness report before sprint or
release closure. The report renders Markdown and JSON with `can_close`,
workspace candidates, and blockers so the operator UI, Jira comment, or
Confluence summary can show stale workspace status without reimplementing the
rules.

## Workspace Creation Options

### Option A - Git Worktree

Git worktrees are the default recommendation for local session-mode work.

Use when:

1. The target repository is local and Git-backed.
2. Work is expected to be short-lived.
3. The operator can clean up stale worktrees safely.
4. Branch names are managed by the scheduler.

Required behavior:

1. Create one worktree per Jira issue and role.
2. Use `feature/{JIRA_KEY}-{short-slug}` for implementation work.
3. Never reuse another active assignment's worktree.
4. Verify no uncommitted changes remain before releasing the workspace.

### Option B - Fresh Clone

Fresh clones are preferred for long-running Docker workers or when worktree
cleanup is unreliable.

Use when:

1. The worker may run for a long time.
2. The host Git worktree registry should not be shared with containers.
3. Isolation is more important than local speed.
4. The worker needs independent dependency caches.

Required behavior:

1. Clone only the approved repository.
2. Checkout the approved base branch or release branch.
3. Create the feature branch inside the clone.
4. Push only the assignment branch.

### Option C - Copied Snapshot

Copied snapshots are for read-only analysis, documentation review, or
non-mutating validation work that does not create source changes.

Use when:

1. The assignment is non-mutating.
2. The source does not need Git operations.
3. The worker needs a stable input view for validation.

Copied snapshots must be treated as disposable and must not become the source
of a pull request.

## Scheduler Parallel Assignment Checks

Before assigning work in parallel, the scheduler checks:

1. `READY TO START` status.
2. Current sprint membership and approved sprint ring.
3. Dependency gate and linked-bug status.
4. Assignment lock state for the same Jira key and role.
5. Codex limit gate for the route model and reasoning.
6. Workspace availability and cleanup safety.
7. Predicted file-scope conflict risk.

Conflict risk is acceptable when predicted changed files do not overlap with an
active implementation assignment. If changed file sets overlap or cannot be
estimated, the scheduler either runs the later story sequentially or marks it
conflict-prone and requires rebase after the earlier PR merges.

## Blocked Story Fallback

A blocked story must not stop the sprint when another approved sprint story is
eligible.

When the preferred story is blocked, the scheduler:

1. Records the blocker keys and reason.
2. Leaves the blocked story visible in Jira.
3. Scans the same active sprint for another `READY TO START` issue.
4. Re-runs dependency, lock, limit, and conflict checks.
5. Assigns the next eligible issue.
6. Creates a PO inbox item only when Product Owner action is required.

The scheduler must not pull work from a different sprint without Product Owner
override or Release Manager sprint lifecycle synchronization.

## Docker Mount Requirements

Future Docker workers mount:

1. Assigned isolated workspace at `/workspace/project`.
2. Shared durable coordination root at `/workspace/data`.
3. Read-only boilerplate instruction bundle at `/workspace/instructions` when
   the worker does not run directly from the boilerplate image.
4. Optional dependency cache volumes that are scoped per project or role.

Docker workers must not mount one shared mutable target-project checkout for
parallel implementation workers.

Release 1.1 Docker workers remain dry-run/runtime validation workers. They can
register, poll assignments, check limit state, write logs, and validate mount
contracts. Live Codex-backed execution remains delegated to the host-side
runner boundary until a later approved release implements detached execution.

## Future Implementation Notes

Create later implementation stories for:

1. Workspace allocation command that executes the validated plan.
2. Workspace cleanup command that executes the validated archive/cleanup plan.
3. Scheduler predicted file-scope conflict classifier.
4. Cleanup policy fields for assignment records.
5. Docker worker mount validation for isolated workspaces.
6. Operator UI status view for active workspace allocations.

These stories may be grouped under Release 1.2 or later if Release 1.1 remains
session-mode validation focused.
