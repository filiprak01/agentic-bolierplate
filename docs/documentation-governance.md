# Documentation Governance

Documentation governance separates approved shared knowledge from role-specific
working notes.

The Product Owner remains the final authority for shared documentation truth.
Agents may propose documentation changes, but they must not treat drafts or
role-specific notes as approved shared content.

## Scopes

Shared documentation can become approved truth and may be committed as Markdown
in Git, published to GitHub Pages, and optionally synced to Confluence after
Product Owner approval. Release 1.2 defaults to the strategy in
`docs/github-pages-documentation-strategy.md`.

Shared categories:

1. `product_vision`
2. `requirements`
3. `architecture`
4. `adr`
5. `process`
6. `release`
7. `report`

Role-specific notes are working context for one role and do not sync to
Confluence as approved truth.

Role-specific categories:

1. `product_planning`
2. `architecture`
3. `developer`
4. `review`
5. `tester`
6. `release_manager`

## Proposal Status Flow

Documentation proposals use this status flow:

```text
draft -> proposed -> po_review -> approved
```

Allowed alternate paths:

1. `draft -> rejected`
2. `proposed -> draft`
3. `proposed -> rejected`
4. `po_review -> proposed`
5. `po_review -> rejected`
6. `approved -> superseded`

Only `approved` shared documentation can be treated as shared truth.

Rejected and superseded proposals are terminal.

Approved shared documentation can contain AI/operator knowledge without a Jira
story when it is context-only. When a line describes implementation,
automation, process behavior, role responsibility, operator UI behavior,
integration behavior, roadmap scope, or release work, it must be covered by
`docs/documentation-to-backlog-traceability-audit.md` before backlog approval or
release planning.

## Publication Eligibility

Approved shared documentation is eligible for provider-level publication when:

1. The proposal scope is `shared`.
2. The category is one of the shared documentation categories.
3. The proposal status is `approved`.
4. The category allows the configured documentation provider.
5. The body content is not empty.

Role-specific notes and draft shared proposals are not publication eligible.

The governance model returns local sync decisions and approved shared content
payloads. GitHub Pages generation, Confluence page creation, and local mirror
writes remain adapter-level responsibilities.

## Repo Slimming And Archive Policy

Release 1.2 uses deterministic retention decisions before agents add, publish,
or archive documentation-like files. This prevents the project repository from
becoming a dumping ground for raw logs while preserving the AI-facing source
documents that workers need.

Retention classes:

1. Approved shared Markdown source stays in `docs/` and may publish to GitHub
   Pages.
2. Approved release packages and partner-visible reports stay as reviewed
   report source and publish to GitHub Pages.
3. Context packs stay in durable local storage by default. Only approved,
   release-relevant context packs may be mirrored into a configured repo path.
4. Role notes and raw command logs stay in durable local storage and must not be
   treated as shared truth.
5. Generated site output is rebuildable and should be ignored by Git.
6. Credentials, secrets, and raw sensitive payloads must be redacted or stored
   outside Git before any publication or archive step.

Optional Confluence or partner archive publication is allowed only after the
same classification passes and the project explicitly enables that provider.

## Report Artifacts

Report artifacts are shared documentation when they are intended for Product
Owner review, sprint/release traceability, or partner/client communication.
Publication channels and redaction defaults for those artifacts are governed by
`docs/shared-evidence-publication-policy.md`.

Report artifacts include:

1. Story test evidence summaries.
2. Regression evidence and regression manifests.
3. Sprint retros.
4. Sprint closure notes.
5. Release notes and release readiness summaries.
6. Post-mortems.
7. Partner-facing delivery or quality summaries.

Local repo files remain durable mirrors and worker context inputs. For final
Release 1.2, approved report artifacts should also be published to GitHub Pages
by default so the Product Owner can use a repository-backed documentation site
as the practical collaboration and reporting surface. Confluence publication is
optional when a project explicitly enables the adapter.
Confluence publication is optional for the default Release 1.2 setup and must
not replace GitHub Pages unless the Product Owner chooses that provider.

Internal-only role notes, raw debugging logs, secrets, and noisy local command
output should not be published as partner-facing reports unless the Product
Owner explicitly approves the content.

## Agent Behavior

Agents should:

1. Store temporary role reasoning as role-specific notes.
2. Create documentation proposals for reusable decisions.
3. Route missing or ambiguous requirements to the Product Owner.
4. Promote content to shared documentation only after Product Owner approval.
5. Keep GitHub Pages, Confluence, and local mirror publication behind adapter
   boundaries.
6. Run or reference the documentation-to-backlog traceability audit before
   promoting approved docs into Jira backlog creation.

Agents must not:

1. Treat role-specific notes as approved product or architecture truth.
2. Publish drafts to GitHub Pages or Confluence as approved documentation.
3. Resolve missing Product Owner decisions silently.
4. Leave implementation-worthy commitments only in docs without Jira
   traceability, doc-only classification, deferral, rejection, or a PO inbox
   decision.
