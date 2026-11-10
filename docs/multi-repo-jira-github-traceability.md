# Multi-Repo Jira GitHub Traceability

Status: implemented for `AGENT-678`

This policy keeps Jira stories visibly connected to pull requests when one
story affects the target product repository, the boilerplate/process repository,
documentation repository, or automation repository.

## Repository Lanes

Project configuration distinguishes four repository lanes:

1. `target-implementation` - the product code repository for the client or
   test project.
2. `boilerplate-process` - this agentic boilerplate repository when process,
   agent, runtime, or framework behavior changes.
3. `documentation` - optional docs site or GitHub Pages repository.
4. `automation` - optional test automation framework repository.

Configure these lanes with:

```text
TARGET_IMPLEMENTATION_REPOSITORY=<owner>/<repo>
TARGET_IMPLEMENTATION_DEFAULT_BRANCH=main
TARGET_IMPLEMENTATION_JIRA_DEV_PANEL_EXPECTED=true
BOILERPLATE_PROCESS_REPOSITORY=example-org/agentic-boilerplate
BOILERPLATE_PROCESS_DEFAULT_BRANCH=main
BOILERPLATE_PROCESS_JIRA_DEV_PANEL_EXPECTED=true
DOCUMENTATION_REPOSITORY=
DOCUMENTATION_DEFAULT_BRANCH=main
DOCUMENTATION_JIRA_DEV_PANEL_EXPECTED=false
AUTOMATION_REPOSITORY=
AUTOMATION_DEFAULT_BRANCH=main
AUTOMATION_JIRA_DEV_PANEL_EXPECTED=false
```

Leave optional lanes blank when the project does not use them.

## Story Description Contract

Every generated story that can touch code or process files must include an
`Expected Repositories` section. The section names each affected lane, the
configured repository, default branch, and whether Jira development-panel PR
visibility is expected.

When more than one lane is affected, the story must include visible reasoning
for why the work spans repositories. This is required before development starts.

## Branch Commit And PR Contract

For every affected repository:

1. Branch names include the Jira issue key.
2. Commit messages include the Jira issue key.
3. PR titles include the Jira issue key.
4. PR descriptions include the Jira issue key and repository lane.
5. PR descriptions explain cross-repo reasoning when more than one lane is
   touched.
6. Boilerplate/process repository PRs explain which project story caused the
   process change.

Use repository-specific feature branches. Do not mix AP project implementation
PRs with boilerplate process PRs unless the Jira story and PR body explicitly
explain the reason.

## Jira Visibility Fallback

If GitHub for Jira is not installed, is not connected to the configured repo,
or is not expected to show PRs for a lane, the agent must add an explicit Jira
comment with:

1. Repository role.
2. Repository owner/name.
3. Branch.
4. PR URL.
5. Commit messages or commit SHAs.
6. Process/change reason when the boilerplate repository is touched.

The manual fallback comment is required even when the PR title and branch
already contain the Jira issue key.

## Setup Diagnostics

Setup diagnostics should warn for every configured repository lane where
`*_JIRA_DEV_PANEL_EXPECTED=false`. The warning means the worker should not wait
for the Jira development panel to show the PR automatically and should use the
manual Jira PR link fallback immediately.

## Agent Responsibilities

Product Planning Agent:

1. Adds `Expected Repositories` to stories.
2. Adds cross-repo reasoning when multiple lanes are affected.
3. Creates dependencies so policy stories are completed before dependent
   implementation stories.

Developer Agent:

1. Uses the configured lane repository for each affected change.
2. Keeps branch, commit, PR title, and PR body Jira-keyed.
3. Adds manual Jira PR link comments when automatic visibility is unavailable.

Review Agent:

1. Verifies each affected repository has its own visible PR or explicit
   documented reason for a combined process PR.
2. Blocks merge when the story touches a repository not named in the story.
3. Blocks merge when Jira lacks either automatic PR visibility or the manual
   fallback comment.

Release Manager:

1. Verifies release notes include cross-repo PRs that affected the release.
2. Confirms boilerplate/process changes are traceable to the project story that
   caused them.
