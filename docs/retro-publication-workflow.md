# Retro And Post-Mortem Publication Workflow

This workflow turns sprint retro, post-mortem, closure, performance, and
process-note outputs into a visible publication plan before the next sprint
starts.

The Product Owner remains the final process owner. If retro output changes
boilerplate behavior, code, automation, scripts, tests, or configuration, it is
not hidden inside the sprint publication task. It is routed to a separate Jira
story and waits for Product Owner approval.

Evidence channel and redaction rules are governed by
`docs/shared-evidence-publication-policy.md`.

## Publication Task

Each sprint should have one board-visible publication task, such as the sprint
retro and closure task. The publication plan either detects the existing task or
blocks publication until a task is created.

The publication task is used for current-project process artifacts:

1. Sprint retro notes.
2. Post-mortem notes.
3. Sprint closure notes.
4. Sprint performance tracking.
5. Process notes that do not change boilerplate behavior.

## Sprint Setup Gate

Before delivery stories begin, sprint setup validation should confirm:

1. A board-visible retro intake support task exists for the active sprint.
2. The retro intake template path is known and ready for role comments.
3. Support-task `Blocks` links are used only for closure sequencing and do not
   turn delivery stories into dependency-blocked work.

If the retro intake task or template is missing, setup is blocked until Release
Manager, Orchestrator, or Product Owner creates the missing sprint support
artifact. Delivery dependency checks should record support-task link warnings
instead of treating those support tasks as delivery prerequisites.

## Changed File Routing

Every repo file changed after retro is classified before branch creation.

Process documentation can be published under the sprint publication task when
the changed file is included as a publication artifact.

Product behavior, code, automation, scripts, tests, and configuration changes
require a Jira story. Those changes are implemented under their own branch and
pull request after Product Owner approval.

Product Owner can park local notes explicitly. Parked notes do not block the
next sprint, but they are not treated as published sprint artifacts.

## Branch And PR Visibility

Publication changes use a dedicated branch that references the publication
task, for example:

```text
process/AGENT-245-retro-publication
```

The publication task should receive the publication branch, pull request links,
evidence paths, and any follow-up story keys.

Retro, post-mortem, and process-note summaries that are approved for sharing
should be published to Confluence and mirrored locally. Raw role notes,
debugging logs, credentials, source documents, and unredacted sensitive content
remain local-only.

## Next Sprint Gate

The next sprint is blocked when:

1. The sprint publication task does not exist.
2. A code, automation, script, test, product behavior, or configuration change
   is missing a Jira story.
3. A process documentation file changed after retro is not included as a
   publication artifact and was not parked by the Product Owner.

This gate prevents silent process drift and keeps retro follow-ups visible in
Jira, GitHub, and durable local evidence.
