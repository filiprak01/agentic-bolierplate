# Live Integration Readiness

Status: Release 1.2 implementation baseline for `AGENT-677`.

Workers must not start detached or session-backed implementation work when the
configured local project, Jira, GitHub, documentation, testing, or optional
design integrations are not ready.

Use:

```bash
agentic setup live-diagnostic --project-root .
```

For local/offline checks that should not call external services:

```bash
agentic setup live-diagnostic --project-root . --skip-network --json
```

## Diagnostic Scope

The diagnostic is non-mutating. It may read integration metadata, but it must
not create Jira issues, transition issues, create GitHub branches, create pull
requests, write Confluence pages, or alter AgileTest or Figma data.

It reports:

1. Target project path, Git metadata, and durable data boundary.
2. GitHub repository readability, default branch visibility, non-mutating
   write-permission proof from GitHub repository metadata, and local Git
   read/dry-run push access from the configured target checkout.
3. Jira project and board access.
4. Jira workflow statuses, issue types, dependency link types, sprint access,
   and optional sample issue transition visibility.
5. Confluence space and parent page readability.
6. AgileTest credential configuration and Jira Test issue workflow contract.
7. Optional Figma configuration and read access when configured.

## Status Semantics

1. `pass`: check succeeded.
2. `warning`: check is not ideal but does not block assignment by itself.
3. `skipped`: optional integration was intentionally not configured.
4. `fail`: worker assignment must stop until the issue is corrected.

The CLI exits with `0` when no `fail` check exists. It exits with `1` when
assignment is blocked.

## Assignment Gate Usage

Release Manager or Scheduler must run setup validation and live integration
readiness before assigning a story to a worker.

If readiness fails:

1. Do not create a worker assignment.
2. Write a PO-visible diagnostic summary to the related Jira issue or PO inbox.
3. Keep the story in `READY TO START` or move it back to `FUNNEL` only when the
   Product Owner decides the setup issue changes scope.
4. Re-run readiness after credentials, paths, workflow statuses, or permissions
   are corrected.

## Redaction

Diagnostic output must never print GitHub tokens, Jira tokens, Confluence
tokens, AgileTest tokens, Figma tokens, Basic auth values, or Bearer auth
values.

Use JSON output for automation and readable output for manual operator checks.

## GitHub Remediation

GitHub readiness must fail closed when the repository is unreadable, when the
authenticated token/user can read the repository but GitHub metadata does not
report branch write permission, or when the local target checkout cannot read
origin HEAD or dry-run push a preflight branch. This catches private organization repositories
where a PAT is valid but has not been granted organization or repository access.

When GitHub readiness fails:

1. Confirm <code>GITHUB_REPOSITORY</code> uses <code>owner/name</code> for the target repository.
2. Refresh <code>GITHUB_TOKEN</code> or <code>GH_TOKEN</code> with repository metadata, contents, branch,
   pull request, checks, and merge permissions required by the worker role.
3. Approve organization access for the token or GitHub App connection.
4. Run <code>gh auth setup-git</code> when the local checkout should use GitHub CLI
   credentials, or run the agentic token-auth helper for env-backed HTTPS auth.
5. Rerun <code>agentic setup live-diagnostic --project-root .</code> before starting a
   Developer, Review, or Release Manager worker.

Diagnostics must mention only the failed capability and remediation. They must
not print token values, credential-helper payloads, or authorization headers.
