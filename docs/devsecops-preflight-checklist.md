# DevSecOps Preflight Checklist

Status: shared process baseline for `AP-161`.

This checklist keeps security and platform guardrails visible before
implementation starts on stories that can expose sensitive data, credentials,
runtime boundaries, or operational cost.

It is a pre-implementation checkpoint. It does not approve residual risk,
production access, paid infrastructure, real personal data usage, or compliance
posture on behalf of the Product Owner.

## When To Run

Run this checklist before implementation when a story touches any of these
areas:

1. Authentication, authorization, account linking, or session ownership.
2. Uploads, PDF parsing, file-processing, scratch files, or temporary storage.
3. Persistence, backups, exports, retention, deletion, or recovery behavior.
4. Secrets, credentials, provider integration, deployment, exposed ports, or
   runtime environment configuration.
5. Logs, evidence artifacts, diagnostics, support bundles, or user-visible
   error output.

Run it during planning as well when the story is C3 or higher and the missing
answer can change architecture, data handling, cost, or release scope.

## Routing

Use DevOps/Platform routing for routine environment, storage, logging,
deployment-boundary, and runbook checks.

Use Security routing when the work requires threat modeling, authorization
design, credential architecture, production access, compliance interpretation,
or residual-risk analysis. If the active session is not using the required
Security route, create a manual Product Owner switch checkpoint before
continuing.

Create a PO inbox item and stop when any of these are unclear:

1. Real or customer-like data may be used.
2. Identity provider, auth mode, or session-transfer behavior is undecided.
3. Retention, deletion, backup, export, or diagnostic policy is missing.
4. Production deployment, public access, exposed port, provider, or paid
   infrastructure is involved.
5. Product Owner risk acceptance or compliance constraint is required.

## Required Inputs

Before changing files, confirm:

1. Jira issue is `READY TO START` and dependency links are eligible.
2. Durable Codex limit record allows work.
3. Context pack or approved documentation references exist.
4. Acceptance criteria identify validation commands or evidence expectations.
5. The story states whether synthetic/redacted data only is required.
6. Open PO inbox items do not block the story.

## Checklist

### Data Scope

1. Confirm whether inputs are synthetic, redacted, or real.
2. Keep synthetic/redacted-data-only constraints visible until Product Owner
   approval changes them.
3. Do not store original personal documents permanently unless explicitly
   approved.
4. Record any data-sensitivity ambiguity in the PO inbox.

### Session And Ownership Controls

1. Enforce exactly one owner for user data: registered user id or guest session
   id, not both.
2. Use cryptographically random guest identifiers.
3. Store guest identifiers only in secure HTTP-only SameSite cookies when
   browser sessions are involved.
4. Do not introduce a shared guest user in persistence.
5. Treat account transfer, delegation, and account linking as Product
   Owner-approved behavior, not implied behavior.

### Upload And File Processing

1. Validate extension, MIME type, content signature, size, page count, and
   protected or unsupported documents.
2. Keep temporary files private, randomly named, and scoped to the import or
   worker session.
3. Exclude scratch and temporary original documents from long-term backups.
4. Make cleanup idempotent and safe to retry.
5. Hosted environments must disable local-path parsing unless Product Owner
   approval explicitly says otherwise.

### Persistence, Retention, Backups, And Exports

1. State which parsed, verified, exported, and discarded states persist.
2. State deletion triggers and retention limits.
3. Confirm backup policy for database records, generated exports, temporary
   files, and durable evidence.
4. Keep exports scoped to the owning user or guest session.
5. Ensure recovery behavior does not restore deleted originals unexpectedly.

### Secrets, Providers, And Deployment

1. Keep secrets in `.env`, local secret storage, Docker secrets, or the target
   deployment secret manager.
2. Do not print or commit tokens, authorization headers, cookies, passwords, or
   raw request bodies.
3. Use Product Owner approval for paid providers, public endpoints, production
   credentials, and external-facing deployment choices.
4. Record provider assumptions and deployment boundaries in handoff notes.

### Logs, Evidence, And Diagnostics

1. Do not log document contents, full filenames, tokens, cookies, raw request
   bodies, or secret-like paths.
2. Log issue keys, redacted field names, validation outcomes, and relative
   artifact paths only.
3. Redact operator-visible status views and evidence before Jira or Confluence
   publication.
4. Keep failed-request artifacts and diagnostics free of personal documents and
   secrets.

## R3 Upload Backend Handoff

For the Release 3 guest upload backend path, use the approved R2 inputs from
`AP-68`, `AP-70`, and `AP-71` before implementing upload or session stories.

`AP-79` must carry these checks forward:

1. Exactly one owner: registered user id or guest session id.
2. Cryptographically random guest identifiers.
3. Secure HTTP-only SameSite cookies for guest browser sessions.
4. No shared guest user.

`AP-80` must carry these checks forward:

1. Upload validation for extension, MIME type, content signature, size, page
   count, and protected or unsupported PDFs.
2. Private randomly named temporary PDFs and scratch files.
3. No permanent original PDF storage.
4. Cleanup that is idempotent and does not log document contents or full
   filenames.
5. Synthetic/redacted-data-only until Product Owner approval changes the data
   gate.

## Outputs

The agent should leave one or more of these durable outputs:

1. Jira subtask or story comment summarizing completed checks.
2. PO inbox item for missing Product Owner decisions.
3. Test or evidence path under `data/agent-logs/<JIRA_ISSUE>/`.
4. Follow-up Jira candidate when a reusable guardrail is missing.
5. Handoff note for Review, Tester, Release Manager, or Docs/Confluence.

If the checklist produces no blockers, say so explicitly in the handoff. If it
does produce blockers, do not move the story forward until the blocking item is
visible in Jira or the PO inbox.
