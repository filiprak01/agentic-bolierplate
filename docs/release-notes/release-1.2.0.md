# Release 1.2.0 Notes

Release 1.2 focuses on hardening the agentic boilerplate for local project
operation before fully autonomous detached Codex execution.

Release status: accepted for publication on 2026-10-17 after Sprint 8
regression, bounded live runtime proof, and Product Owner release approval.

## Delivered Themes

1. Operator API/UI and PO inbox visibility.
2. Multi-project durable boundaries and message export policies.
3. Docker worker readiness, assignment polling, locks, checkpoints, and
   host-side Codex job handoff.
4. GitHub token/SSH setup and PR visibility diagnostics.
5. GitHub Pages documentation and report publication as the default
   documentation surface.
6. Story generation, context pack generation, and PO approval workflow.
7. Release Manager regression, branch/tag checklist, migration, and closure
   workflows.
8. Shared Codex quota guard skill for preflight, checkpoint, and completion
   evidence across session-mode and host-side work.
9. Deterministic role-specific Jira pickup profiles, dependency-aware work
   eligibility, retry/rework routes, and isolated context/workspace policies.
10. Dockerized operator API/UI with project-scoped PO inbox, runtime status,
    quota visibility, and durable local data boundaries.

## Validation Summary

1. Full automated suite: 1,272 passed.
2. Bounded live runtime: two Docker-queued Codex stages completed through the
   host-side ChatGPT-subscription runner.
3. Recovery validation: seven scenarios covering four required recovery kinds.
4. Operator validation: API and UI images built; health, inbox, status, quota,
   and UI HTTP smoke checks passed.
5. No unresolved blocking Release 1.2 bugs remained at closure.

The detailed evidence is in
[Release 1.2 Sprint 8 Runtime Proof And Regression](../reports/index.md)
and the
[Release 1.2 Closure Record](../reports/index.md).

## Sprint 6 Hardening

Sprint 6 added:

1. Documentation repo slimming and archive policy.
2. Regression-gated release branch/tag checklist automation.
3. Detached worker pilot evidence on a sample project.
4. Review Agent approval publication fallback diagnostics.
5. Release 1.2 operator guide, migration guide, release notes, and closure
   package.

## Known Boundaries

1. Codex-backed execution remains host-side/session delegated.
2. Docker workers can create durable Codex job requests but do not run hidden
   Codex subscription sessions inside containers.
3. Confluence is optional; GitHub Pages is the default publication target.
4. Fully autonomous detached agents remain later release scope.
5. The quota guard skill cannot reserve quota, interrupt every internal model
   request, or schedule background wakeups; runtime enforcement stays in the
   scheduler and host-side runner.
6. AgileTest publication was unavailable at closure. Jira Test definitions,
   durable manifests, and Jira comments remain the truthful evidence fallback;
   no plugin execution success is claimed.

## Upgrade Path

Use [Release 1.2 Migration Guide](../release-1.2-migration-guide.md) and
[Release 1.2 Operator Guide](../release-1.2-operator-guide.md).
