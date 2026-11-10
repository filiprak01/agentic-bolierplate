# Release E2E Runner

The release E2E runner prepares and records MVP release validation without
requiring live production data.

It consumes the approved release E2E scenario map and produces scenario-level
execution output under durable local storage.

## Environment Checklist

Before execution, the runner checks:

1. Local services.
2. Durable storage / volumes.
3. Jira configuration.
4. GitHub configuration.
5. Confluence configuration.
6. AgileTest configuration.
7. Sample target project readiness.

Required failed checks block release E2E execution until remediated.

## Scenario Execution

Each release E2E scenario records:

1. Scenario ID and title.
2. Execution mode: automated, manual-only, or supporting validation.
3. Result: passed, failed, blocked, or not-run.
4. Evidence path.
5. Linked bugs when failures are found.
6. Notes for manual-only execution.

For MVP, the runner can mark release scenarios as manual-only and not-run until
Tester or Release Manager executes them. This keeps the release gate visible
without pretending that manual validations are automated.

## Output

Execution output is rendered as Markdown and stored in durable local storage.
The release execution overview task should link to that output and to any
failed scenario bugs.
