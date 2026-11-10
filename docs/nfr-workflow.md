# Architecture Agent NFR Workflow

The Architecture Agent uses the NFR workflow before risky implementation starts
to identify missing non-functional requirements and route Product Owner
questions.

The workflow is local-first. It creates durable PO inbox questions, promotes
answered decisions into shared documentation governance, and marks affected
stories for follow-up.

## Checklist

The required NFR checklist contains:

1. Performance
2. Security
3. Reliability
4. Observability
5. Maintainability
6. Cost
7. Token optimization
8. Data retention

Architecture Agent should evaluate all eight categories for C3 or higher work
and for any lower-complexity story where an NFR can change architecture,
security posture, model spend, data retention, or operational behavior.

## Missing NFR Questions

When an NFR category is missing, Architecture Agent creates a PO inbox
`blocking_question`.

Each question includes:

1. Story key.
2. Architecture context.
3. NFR category.
4. Business impact.
5. Recommendation.
6. Suggested answer options.
7. Context pack path when available.

Implementation must wait when the missing NFR can change architecture,
security, data handling, or model spend.

## Answer Promotion

Answered NFR questions are promoted into shared requirements documentation.

Promotion creates:

1. A shared documentation proposal with category `requirements`.
2. Approved shared content ready for local mirror and Confluence sync.
3. Markdown that includes source inbox item ids, answer timestamps, affected
   stories, and the Product Owner answer.

Only answered Architecture Agent blocking questions can be promoted. Open
questions must remain in the PO inbox and continue blocking risky work.

## Affected Story Follow-Up

Answered NFR decisions can affect more than the original story.

The workflow creates follow-up marker data containing:

1. Affected story key.
2. Related NFR categories.
3. `nfr-follow-up` label.
4. Category labels such as `nfr-security` or `nfr-token-optimization`.
5. A note describing which NFR decisions must be reviewed before
   implementation.

Agents use this marker data to update Jira stories or draft follow-up work
without silently changing business scope.

## Confluence Preparation

The workflow does not call Confluence directly.

It prepares approved shared documentation content using documentation
governance. Adapter-level synchronization is responsible for pushing approved
content to Confluence and durable local mirrors.

## Agent Behavior

Architecture Agent should:

1. Run the checklist before C3 or higher implementation starts.
2. Create PO inbox questions for missing NFRs.
3. Wait for Product Owner answers when the NFR can change architecture or
   delivery scope.
4. Promote answered NFR decisions into shared documentation governance.
5. Mark affected stories for follow-up.

Developer Agent should:

1. Treat unresolved blocking NFR questions as development blockers.
2. Read approved NFR documentation before implementation.
3. Respect affected-story follow-up markers.

Release Manager should:

1. Include approved NFR decisions when evaluating sprint and release risk.
2. Confirm data retention, observability, and reliability decisions before
   release when they affect regression or operations.
