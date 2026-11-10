# CI Quality Gate

Implemented for `AGENT-132`. The `CI` workflow in `.github/workflows/ci.yml`
provides the checks Review Agent verifies before merge. Local validation
remains available for development; it does not prove that remote CI passed.

## Workflow And Checks

`CI` runs on pull request `opened`, `synchronize`, `reopened`, `ready_for_review`,
and `edited` events. There are no branch or path filters, so PRs targeting
stacked feature branches are included and retargeting requests a fresh run.
`workflow_dispatch` also permits manual runs. New runs cancel older runs in
the same PR/ref concurrency group; cancellation is not a passing result.

| Check name | Job id | Validation | Output |
| --- | --- | --- | --- |
| `Pytest` | `pytest` | Python 3.12, `python -m pip install -e ".[dev]"`, then the full pytest suite | Job logs and JUnit XML |
| `Docker Compose` | `compose` | `docker-compose.yml`, all profiles, and the optional `docker-compose.ssh.example.yml` override | `Validate Docker Compose` step logs |

Keep these check names stable. The existing `Docs Pages` workflow is separate
and unchanged; its `Validate docs site` check still applies when triggered.
CI uses `contents: read`, does not persist checkout credentials, and needs no
integration secrets. It does not deploy, publish test results to AgileTest,
change branch protection, or start containers.

For PR events, the default checkout tests GitHub's temporary merge commit at
`refs/pull/<number>/merge`. Record the reviewed PR head SHA separately from
that tested merge SHA. A manual branch run does not by itself prove the PR's
merge result was tested. See [GitHub PR event semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request).

## Review Before Merge

1. Verify the PR's current head SHA and base branch, plus the reviewed base SHA
   for stacked work. Confirm the inspected `CI` run and attempt belong to that
   revision and base, including the merge ref/SHA actually checked out.
2. Inspect both `Pytest` and `Docker Compose` in the PR Checks tab. Missing,
   pending, failed, cancelled, timed-out, neutral, skipped, or stale checks block
   merge. Check all other applicable repository-required checks as well.
3. When `docker-compose.yml` is absent, the Compose step explicitly reports
   validation as not applicable and completes successfully. Review Agent must
   verify the absence in the reviewed tree and record that reason. An absent
   check or an unexplained skip is not equivalent to this result.
4. Link or summarize the observed CI output in the durable review record before
   approval. Recheck after new commits, rebase, retargeting, or base changes that
   invalidate the evidence. Never reuse a passing run from an older revision.
5. Merge only when the CI gate, findings, dependencies, and documented merge
   ownership all permit it. Follow [Review Agent PR Workflow](review-agent-pr-workflow.md)
   for the remaining review and handoff requirements.

These are Review Agent process requirements, not a claim that repository
branch protection has been configured. Agents must inspect real GitHub checks;
mock adapter check placeholders and local logs are not remote CI evidence.
Missing access or an Actions approval requirement leaves the gate blocked.
Do not change account permissions or protection settings to bypass it.

## CI Evidence In Review Records

Use the existing `ReviewRecord.head_sha` for the reviewed PR head. Record the
CI verification as a `testing` finding in `findings`, with the evidence in its
`description`; the [review-record schema](review-records.md) has no dedicated
CI fields. The workflow does not populate this evidence automatically.

The description must include the CI run URL and attempt, observation timestamp,
reviewed head SHA, base branch/SHA, tested ref/SHA, both check conclusions, and
a concise output summary or links to the relevant job logs. Include pytest
counts and failing tests when observed, or state that tests never started.
For Compose, record whether base/all-profile and SSH-override validation ran,
failed, or were not applicable. Do not include resolved environment values,
credentials, or raw private integration payloads.

This partial record illustrates **unverified evidence**, not an actual run or
a complete serializable record. Replace every placeholder using observed data
and preserve the other required record fields:

```json
{
  "head_sha": "<reviewed-head-sha>",
  "final_decision": "blocked",
  "findings": [
    {
      "id": "ci-quality-gate",
      "title": "CI quality gate verification pending",
      "kind": "testing",
      "severity": "blocking",
      "status": "open",
      "description": "CI run URL: https://github.com/<owner>/<repo>/actions/runs/<run-id>; reviewed SHA: <reviewed-head-sha>; Pytest: not verified; Docker Compose: not verified. Remote CI evidence is pending."
    }
  ]
}
```

Keep the finding open while evidence is missing or the gate fails. After
verifying passing checks for the current revision, update the description with
the actual run details and mark it `addressed`; retain the evidence when the
normal review workflow determines the final decision. Update `updated_at`.
Store the record at the configured
`<review-record-root>/<review-record-id>/review-record.json` and reference it
from the PR review summary. Do not invent extra JSON fields that serialization
would discard.

The `Pytest` job writes `data/ci/pytest.xml` and attempts to upload it as the
`ci-pytest-results` artifact even after a test failure, with 14-day retention.
Find it in the workflow run's Artifacts section. If setup fails before XML is
produced, upload warns about the missing file; this does not turn the failed
job into success. Compose output is in job logs, not a separate artifact.
Capture the observed summary durably before hosted logs/artifacts expire.
See [GitHub workflow run logs](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-workflow-run-logs)
for locating output and copying log permalinks.

## Local And Offline Validation

Run from the repository root in a Python 3.12 environment to match CI.
The package supports Python 3.11+, but the CI runtime is specifically 3.12.
The `python` commands below assume that environment is active; an already
configured Poetry environment can use `poetry run python` instead.

Install the package and development extra before going offline:

```bash
python -m pip install -e ".[dev]"
```

This installs runtime dependencies plus pytest and PyYAML. Initial installation
requires package-index access or a prepared local package source/cache; the
installation command is not an offline guarantee. Once installed, tests use
local/mock integrations and do not require GitHub, Jira, AgileTest, database,
Redis, or Codex credentials or live services.

Run the full suite and retain the same XML output as CI:

```bash
python -m pytest --junitxml=data/ci/pytest.xml
```

Run just the workflow/configuration contracts and existing docs-workflow checks:

```bash
python -m pytest tests/test_ci_quality_gate.py tests/test_docker_compose_foundation.py tests/test_github_pages_deployment_workflow.py -q
```

The shell-behavior contract tests use a fake Docker executable and require
POSIX Bash; those cases skip outside POSIX/Bash while YAML contracts still run.
Real Compose validation additionally needs the Docker CLI with Compose v2
installed (`docker compose version`). Use Linux, macOS, or WSL with Bash and
standard `mktemp`, `cp`, `rm`, and `rmdir` utilities. The config-only commands
below do not need a running Docker daemon or downloaded container images.

Run the same Compose validation used by CI:

```bash
bash <<'BASH'
set -euo pipefail
if [[ ! -f docker-compose.yml ]]; then
  echo "No docker-compose.yml present; Compose validation is not applicable."
  exit 0
fi

# Keep service env_file resolution away from the developer's .env.
validation_dir="$(mktemp -d)"
trap 'rm -f "$validation_dir/.env"; rmdir "$validation_dir"' EXIT
cp .github/ci/compose.env "$validation_dir/.env"
compose=(docker compose --project-name agentic-ci
  --project-directory "$validation_dir" --env-file "$validation_dir/.env"
  -f "$PWD/docker-compose.yml" --profile "*")

"${compose[@]}" config --quiet
echo "Base Compose configuration and all profiles passed."
if [[ -f docker-compose.ssh.example.yml ]]; then
  "${compose[@]}" -f "$PWD/docker-compose.ssh.example.yml" config --quiet
  echo "SSH example override and all profiles passed."
fi
BASH
```

The committed `.github/ci/compose.env` contains only placeholders. A temporary
project directory satisfies Compose's `env_file: .env` without reading or
overwriting a developer's `.env`. Relative paths resolve within that directory
for validation; no real SSH key is read. This validates configuration, not
image builds, mount contents, service health, or live integrations. Do not
start services with this fixture. Normal runtime setup remains documented in
[Docker Compose Foundation](docker-compose-foundation.md).

For documentation changes, run the existing local docs commands:

```bash
python -m agentic_boilerplate.cli docs-site validate --docs-root docs
python -m agentic_boilerplate.cli docs-site build --docs-root docs --output-root site
```

The docs commands check and build the configured site navigation, not every
Markdown file. Inspect links in changed pages as part of focused review.

## Failure Recovery

Record failed commands/checks, revision, runtime, and evidence path. Follow
[CI Failure Recovery](ci-failure-recovery-playbook.md) to return corrections to
the owning Developer Agent and refresh the review evidence after validation.
Local success allows offline development to continue, but remote CI must be
observed before merge. Requests to change credentials, permissions, scope, or
merge with failing checks require the documented Product Owner inbox process.
