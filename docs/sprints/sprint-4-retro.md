# Sprint 4 Retro

Sprint: MVP Sprint 4 - Integration Adapter Foundation

Status: completed through PO acceptance and regression

Regression evidence: `data/agent-logs/REGRESSION-S4/regression-evidence-20260619T111005Z.md`

## Delivered

1. GitHub adapter contract, REST boundary, mock adapter, tests, and docs.
2. Jira project/issue adapter configurability, workflow transitions, dependency
   links, tests, and docs.
3. Confluence documentation adapter, local mirror support, mock adapter, tests,
   and docs.
4. Shared integration mock layer covering GitHub, Jira, and Confluence.
5. Sprint 4 regression scope covering reusable Test Cases from Sprints 1-4.

## What Worked

1. Small story slices kept adapter implementation and testing manageable inside
   the Codex Plus working window.
2. Subtask-by-subtask commits gave clear Jira visibility and recovery points.
3. Testing from detached `origin/main` worktrees protected regression results
   from unrelated local workspace changes.
4. AgileTest-style Test Case issues and a board-visible regression overview made
   regression scope easier to audit.
5. The integration mock layer should reduce future live-token usage during
   worker and scheduler development.

## Adjustments Accepted

1. Regression executions should explicitly list all reusable Test Cases from all
   previous completed sprints, even when the full pytest suite covers them.
2. Detached regression worktrees need access to expected local runtime files
   such as `.env` when validating Docker Compose configuration.
3. Adapter stories should continue to document dogfooding values as examples
   only, with project/repository/space values remaining configurable.
4. Test Cases should include PO-readable scenarios, preconditions, steps,
   expected results, automated coverage, commands, and evidence links. Coverage
   bullets alone are not enough for Product Owner validation or future manual
   regression planning.
5. Retro, post-mortem, sprint closure, and process documentation changes should
   be pushed through a branch and PR before the next sprint starts. The working
   tree should not carry uncommitted process artifacts into a new sprint unless
   they are explicitly parked as out-of-scope user notes.
6. Every sprint should have a sprint-specific Jira Task for retro and closure
   publication. The task covers retro notes, closure notes, sprint performance
   updates, accepted process-doc updates, PR publication, and verification.
   Boilerplate behavior changes discovered during retro still require separate
   backlog stories before implementation.

## Follow-Up Candidates

1. Add a regression manifest builder so reusable Test Cases, test files, and
   sprint execution scope can be generated instead of assembled manually.
2. Add Jira/AgileTest evidence helpers to reduce repeated API scripting during
   test evidence, regression execution, and link creation.
3. Add CI quality gates so PR checks exist in GitHub instead of relying only on
   local validation before review/merge.
4. Add automated coverage mapping so each Test Case can declare the exact test
   file or command that covers it.
5. Add a Test Case template/helper so new AgileTest Test Cases are created with
   scenario details from the start.
6. Add a retro/post-mortem publication workflow so process learnings become
   reviewed repo artifacts instead of uncommitted local notes.
7. Automate creation of the sprint retro/closure publication Task as part of
   the Release Manager sprint close workflow.

## Conclusion

No blocking process change is required before Sprint 5. The strongest
improvements are already represented by backlog candidates for regression
manifest, evidence helpers, CI quality gates, and coverage mapping.
