# Parallel Session Safety Policy

Status: Release 1.1 policy

This policy defines when multiple Codex-session agents may work in parallel
before fully detached Docker execution exists.

## Safe Parallel Development

Parallel development is allowed when all conditions are true:

1. Each session owns a different Jira issue.
2. Each Jira issue is `READY TO START`.
3. Dependency gates and sprint co-scheduling checks passed.
4. Each session has an active assignment lock for its Jira key and role.
5. Each session works on its own feature branch.
6. Context packs, output paths, evidence paths, and PO inbox references are
   issue-specific.
7. Quota guard evidence records the current project identity, durable store,
   account scope, bucket/window, Jira issue, role, and stage for each session.

Parallel sessions must not edit the same file set unless the Release Manager
or scheduler has explicitly ordered the work and the later session rebases
after the earlier PR merges.

Workspace allocation, shared durable folders, isolated per-worker folders, Git
worktree/fresh clone/snapshot options, and Docker mount requirements are
defined in `docs/parallel-agent-workspaces.md`.

## Sequential Work

Review, testing, and release work are sequential for a given Jira issue:

1. Developer finishes subtasks and opens a PR.
2. Review Agent checks the diff, repository context, conflicts, and quality
   gates.
3. Review Agent merges only after checks pass.
4. Tester Agent validates after merge to `main`.
5. Release Manager or Story Agent moves tested, bug-free work to
   `ACCEPTED/DONE`.

Regression and sprint closure are sequential for a sprint. They start only
after all included implementation stories, bugs, and support tasks are
`ACCEPTED/DONE`, regression scope is available, and retro/closure work is
ready.

## Branch And Jira Assignment Rules

Every implementation session uses:

```text
feature/{JIRA_KEY}-{short-slug}
```

The assignment lock is the source of truth for who owns a Jira key at a given
time. Jira status and comments provide Product Owner visibility, but they do
not replace the lock.

Rules:

1. One active lock per Jira key.
2. One feature branch per Jira key unless a stale lock replacement is recorded.
3. A session may resume its own lock.
4. Another session may replace a stale lock only after the stale decision is
   logged.
5. A session releases its lock when work completes, pauses for Codex limits,
   fails with handoff state, is cancelled, or is replaced as stale.

Worker claim enforcement follows the same policy:

1. Dry-run worker checks detect conflicting active locks but do not create a new
   lock.
2. Live worker execution creates or reuses one active lock before creating a
   host-side Codex job.
3. Lock records include Jira issue key, role, worker session id, workspace path,
   acquired and updated timestamps, expiry timestamp, release reason, and audit
   note.
4. Active stale locks are not replaced silently by runtime workers. They must be
   marked stale and released through `agentic worker locks` with a durable audit
   note before another worker claims the issue.
5. Lock decisions are visible through worker JSON output, worker logs,
   assignment evidence, detached worker checkpoints, and
   `agentic worker locks list`.

Every parallel implementation session must receive a separate workspace before
source files are changed. The default local option is a Git worktree per Jira
issue. Fresh clones are preferred for long-running Docker workers, and copied
snapshots are allowed only for non-mutating validation work.

When multiple projects share one authenticated Codex account, workers may use
the same configured account scope and durable quota root, but they must not
copy host Codex login folders, target-project secrets, unresolved assumptions,
or conversation memory across assignments. Each session reloads the shared
codex-quota-guard skill from the platform repository and evaluates the gate
for its own project, issue, role, and stage.

## Product Owner Sprint Acceptance

The Product Owner gates work by moving stories into `READY TO START`.

After that gate, agents continue through implementation, review, merge, testing,
and story acceptance without waiting for story-by-story Product Owner approval.
The Product Owner reviews at sprint or release readiness, unless:

1. A blocking PO inbox question is open.
2. Codex limits are unavailable or too close to exhaustion.
3. A dependency, conflict, security concern, or regression failure blocks safe
   continuation.
