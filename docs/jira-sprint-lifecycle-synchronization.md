# Jira Sprint Lifecycle Synchronization

`AGENT-197` adds a reusable sprint lifecycle seam so Release Manager workflows
can validate and synchronize Jira sprint state without hardcoding the current
dogfooding board.

## Why This Exists

Sprint closure drift caused two recurring problems during dogfooding:

1. Jira sprint state stayed open after the process said the sprint was closed.
2. Regression or retro support tasks were missing from the sprint, so board
   visibility broke for the Product Owner.

The workflow now treats sprint lifecycle sync as a first-class decision instead
of a one-off script.

## Lifecycle Rules

Supported transitions:

1. `future -> active`
2. `active -> closed`
3. `active -> active` or `closed -> closed` as a no-op verification pass

Unsupported transitions are blocked and must not be forced silently.

Starting a sprint requires:

1. Configured board access.
2. A sprint id and sprint name.
3. `start_date` and `end_date`.

Starting the next sprint because a dependency-safe story is waiting also
requires a Product Owner decision recorded in the PO inbox or equivalent shared
decision record. Dependency readiness does not by itself start the next sprint.

Closing a sprint requires:

1. Configured board access.
2. The sprint to be currently `active`.
3. Board-visible regression and retro/closure tasks assigned to the sprint.
4. All sprint stories, tasks, bugs, and support items to be `ACCEPTED/DONE`.
5. Sprint regression to have passed.
6. Retro and closure task to be completed.
7. Shared documentation not to contradict the Jira sprint state.

Jira Agile sprint updates must preserve the sprint name and include required
date fields when starting a sprint. When closing a sprint, the adapter can send
the sprint `name` along with the target state so Jira Cloud payload validation
does not depend on hardcoded board behavior.

## Product Owner Safeguard

If Jira state and shared documentation disagree, the workflow blocks the change
and generates a Product Owner question. Workers should not guess whether Jira
or documentation is correct.

If a future sprint is missing `start_date` or `end_date`, Release Manager must
create a Product Owner blocking question for the exact dates. Workers must not invent sprint dates. A reusable Product Owner policy such as "start at current
datetime and end one week later" may be applied only after it is documented in
the inbox or shared sprint policy.

## Next-Sprint Start Requests

When the current sprint is closing and a next-sprint story becomes
dependency-safe, Release Manager evaluates sprint lifecycle before work starts:

1. Verify the current sprint closure state.
2. Verify the next sprint id, name, and Jira state.
3. Verify board-visible regression and closure tasks are present in the current
   sprint before closing it.
4. Ask the Product Owner whether to start the next sprint, defer the story, or
   approve an override when the next sprint is still future.
5. Start the next sprint only after Product Owner input supplies the required
   sprint dates or an approved reusable date policy.

This workflow keeps sprint lifecycle changes visible and prevents workers from
using dependency-safe future work as an implicit sprint-start command.

## Adapter Expectations

The Jira adapter now provides these sprint-aware operations:

1. `list_sprints`
2. `get_sprint`
3. `get_sprint_issues`
4. `add_issues_to_sprint`
5. `transition_sprint`

These operations must always use the configured project and board values from
the environment, not a hardcoded `AGENT` board.

## Decision Record

The domain workflow renders a durable Markdown decision note that captures:

1. Current and target sprint state.
2. Requested lifecycle action.
3. Whether a Jira change should be recorded.
4. Missing support tasks.
5. Blockers.
6. Product Owner question text when documentation and Jira drift.
