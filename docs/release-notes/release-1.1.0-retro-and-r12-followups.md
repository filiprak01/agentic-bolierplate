# Release 1.1.0 Retro And Release 1.2 Follow-Ups

Status: Confluence-ready retro package for `AGENT-455`

## What Worked

1. Story-backed development kept requirements, PRs, evidence, and Jira status
   visible.
2. Isolated worktrees made parallel review/test/development safer.
3. Full-suite regression stayed fast enough for frequent validation.
4. PO inbox durability gave a clear path for blocking decisions without losing
   context.
5. Session-mode validation clarified agent behavior before detached Docker
   automation.

## Process Improvements Captured

1. Retro implementation follow-ups remain in `FUNNEL` until Product Owner
   approves them.
2. Sprint closure can proceed when implementation and regression are done; PO
   release approval is the next larger gate.
3. Supporting regression/retro tasks must be visible but should not block
   implementation stories unless they are approved into the sprint.
4. Agents must record limit checks and stop before starting new work when limit
   records say `wait`, `downgrade_model`, or `ask_product_owner`.
5. Secret-like free-text values in operator status must be redacted, not only
   fields named token or secret.

## Release 1.2 Docker Automation Candidates

Create or review `FUNNEL` backlog stories for:

1. Detached worker trigger handoff between Developer, Review, Tester, Release
   Manager, and Scheduler roles.
2. Automatic wait/resume scheduling when Codex short-window or broad quota is
   unavailable.
3. Assignment lock implementation and stale lock release commands.
4. Multi-project operator inbox and status views.
5. Worker-safe Git workspace preparation using worktrees or fresh clones.
6. Stronger Confluence publication automation for regression, retro, and
   client-facing evidence packages.

## No Blocking Bugs

No release-blocking regression bugs are known at the time of this closure
package. Deferred work is listed in `docs/release-notes/release-1.1.0.md`.
