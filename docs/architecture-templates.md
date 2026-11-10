# Architecture And ADR Templates

Architecture templates help the Architecture Agent document technical decisions
before implementation starts.

Templates are local-first. They render Markdown for Product Owner and technical
review, then can be wrapped as shared documentation proposals for Confluence
sync after approval.

## Architecture Document Template

Architecture documents capture broader design context.

Required fields:

1. `title`
2. `owner`
3. `status`
4. `context`
5. `goals`
6. `decisions`
7. `affected_stories`

Each embedded decision summary must include:

1. `decision`
2. `rationale`
3. `alternatives`
4. `affected_stories`

Rendered sections:

1. Context
2. Goals
3. Non-goals
4. Decisions
5. Affected Stories

## ADR Template

Architecture Decision Records capture one decision.

Required fields:

1. `title`
2. `owner`
3. `status`
4. `decision`
5. `rationale`
6. `alternatives`
7. `affected_stories`

Rendered sections:

1. Decision
2. Rationale
3. Alternatives
4. Consequences
5. Affected Stories

## Governance Integration

Architecture documents become shared documentation proposals with category
`architecture`.

ADR documents become shared documentation proposals with category `adr`.

Infrastructure planning documents use
`docs/infrastructure-planning-template.md` when deployment target, scale,
budget, availability, or growth-path decisions affect project scope. They
produce planning recommendations and roadmap candidates only; live provisioning
requires separate Product Owner-approved stories.

Generated proposals start as drafts by default. The Product Owner approval flow
from documentation governance still decides whether the content becomes shared
truth and sync eligible.

## Agent Behavior

Architecture Agent should:

1. Create architecture documents for broad design context.
2. Create ADRs for specific decisions.
3. Link affected Jira stories.
4. Include alternatives and rationale before implementation starts.
5. Route missing business or non-functional requirements to the Product Owner.
6. Use the infrastructure planning template before recommending paid hosting,
   managed services, public deployment, backup, monitoring, or future
   Kubernetes work.

Developer Agent should not treat draft architecture or ADR templates as
approved implementation truth until the proposal is approved.
