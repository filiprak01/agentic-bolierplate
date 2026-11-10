# Session Mode And Docker Automation Threat Model

Status: Release 1.1 threat model for `AGENT-451`.

This threat model covers current Codex session-mode operation and future
detached Docker automation. It uses the Release 1.1 Docker worker requirements
and credential/volume safety matrix as input.

## Assets

Protected assets:

1. Jira project, board, statuses, links, sprints, and comments.
2. GitHub repositories, branches, pull requests, reviews, checks, and merges.
3. Confluence spaces, pages, reports, and mirrored local docs.
4. AgileTest test cases, executions, cycles, sessions, and regression links.
5. Codex subscription/session access and operator-entered limit records.
6. Local target project source files and generated artifacts.
7. Durable platform state: PO inbox, logs, assignments, locks, context packs,
   Codex jobs/results, failed requests, and evidence.
8. Credentials, tokens, authorization headers, cookies, and account secrets.

## Trust Boundaries

Current Release 1.1 boundaries:

1. Product Owner-supervised Codex sessions execute live reasoning and code
   changes.
2. Docker workers are dry-run/runtime foundations and do not perform live
   autonomous Codex execution.
3. Host-side Codex runner artifacts provide the extension point between worker
   assignments and Codex-backed execution.
4. Jira, GitHub, Confluence, and AgileTest writes require configured adapters
   and story-backed workflow.
5. Durable local files are trusted for recovery but not for silent business
   decisions.

Future Release 1.2+ boundaries:

1. Detached Docker workers may execute more work without an active Codex chat.
2. Workers may need role-specific service identities.
3. Workers may need event triggers and isolated workspaces.
4. Workers may need automatic wake-up after Codex limit reset.

## Threats And Controls

| Threat | Impact | Release 1.1 control | Release 1.2+ gap |
| --- | --- | --- | --- |
| Token leaked through logs | Account or project compromise | Redaction rules, setup validation, no-secret evidence | Central secret scanning and adapter-level redaction tests |
| Worker writes to wrong Jira project | Board/process corruption | Configurable Jira project/board validation | Per-project allowlist and worker identity separation |
| Worker merges wrong GitHub branch | Code loss or unintended release | Feature branch naming, PR review, local validation | Branch protection and machine-enforced merge policy |
| Codex limit exhausted mid-story | Lost work or partial state | Durable limit records, pause artifacts, failed request storage | Automatic wake-up and retry policy after reset |
| PO question ignored | Silent business decision | Durable PO inbox stop rule | Event-driven worker pause on PO inbox creation |
| Context pack stale or mismatched | Wrong implementation | Context pack validation requirement | Signed or versioned context packs |
| Parallel workers edit same checkout | Conflicts and lost work | Assignment locks and session policy | Isolated workspace allocator and cleanup commands |
| Docker mounts host secrets | Credential exposure | Credential/volume safety matrix | Runtime mount policy enforcement |
| Confluence publishes draft report | Client-facing misinformation | Confluence-ready artifacts, PO approval expectation | Publication approval workflow and page diff review |
| AgileTest regression links wrong issue | Bad test traceability | Test evidence artifacts and Jira links | Consistency validator before release closure |
| Review agent resolves conflicts directly | Ownership confusion | Review reports conflicts to Developer | Triggered handoff to developer conflict assignment |
| Detached worker runs beyond scope | Unauthorized changes | Release 1.1 excludes live detached execution | Assignment-scoped adapter permissions and audit trails |

## Release 1.1 Required Controls

Release 1.1 must keep these controls active:

1. Check durable Codex limit records before quota-spending work.
2. Use PO inbox for blockers, approvals, assumptions, and missing decisions.
3. Require `READY TO START` before implementation begins.
4. Check Jira dependency links before assignment.
5. Use one feature branch per Jira issue.
6. Use PR review before merge.
7. Test only after merge to `main`.
8. Store evidence under durable local paths.
9. Redact tokens and secret-like values from logs and comments.
10. Treat Docker workers as dry-run or host-runner delegated until later
    Product Owner approval.

## Release 1.2+ Required Work

Before live detached Docker automation, create or complete stories for:

1. Event-driven worker trigger and handoff queue.
2. Parallel isolated workspace allocation and cleanup.
3. Adapter-level no-secret logging tests.
4. Per-project allowlist and identity policy.
5. Automatic limit reset wake-up with Product Owner controls.
6. Context pack freshness/version validation.
7. Confluence publication approval workflow.
8. Release-level AgileTest traceability validator.

## Product Owner Decisions

Open decisions:

1. Should live Docker workers use one integration identity or role-specific
   Jira/GitHub identities?
2. Should Codex execution remain subscription/session-backed or move to API
   execution for detached automation?
3. Should workers auto-resume after limit reset, or only notify the Product
   Owner?
4. Should Confluence publication require explicit approval for every sprint or
   only for client-facing releases?
5. Should fresh clones or Git worktrees be the default isolated workspace
   model?

These decisions do not block Release 1.1 session-mode validation, but they do
block Release 1.2 live detached worker implementation.
