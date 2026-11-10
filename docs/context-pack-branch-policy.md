# Context Pack Branch Policy

Status: Release 1.2 policy

Context pack branches are non-delivery artifact branches. They let parallel
workers load the same approved facts without making Jira think that a delivery
story has a new implementation PR.

## Branch Classes

Use these branch classes consistently:

| Class | Pattern | Jira delivery visible by default | Purpose |
| --- | --- | --- | --- |
| Delivery | `feature/{JIRA_KEY}-{short-slug}` | yes | Implementation for one Jira story, bug, or task. |
| Context | `context/{PROJECT_KEY}/{agent-role}/{sprint-or-story}` | no | Published context packs for workers. |
| Docs | `docs/{release-or-sprint}` | no | Documentation publication branches. |
| Process | `process/{JIRA_KEY}-{short-slug}` | yes | Process changes tracked by a Jira issue. |

Context branches can be referenced from Jira as Context Pack artifacts, but
must not be linked as implementation PRs unless a Product Owner explicitly
asks for that unusual behavior.

## Context Pack Reference

A context artifact reference must include:

1. Project key.
2. Agent role.
3. Sprint or story scope.
4. Context branch name.
5. Git revision hash.
6. Context artifact hash.
7. Source documents used to generate the pack.
8. Main branch revision used as the generation baseline.

Both the context branch revision and the main generation baseline are required
as lowercase git hashes. Workers validate this reference before claiming an
assignment. If the current main revision does not match the generation
baseline, the context is stale and must be regenerated before work starts.

## Safety Rules

Context packs must exclude:

1. Tokens, passwords, private keys, API keys, and other credential-like content.
2. Unresolved assumptions.
3. Source documents from another target project unless they are explicitly
   shared platform docs.
4. Conversation memory or role notes from another project.

If a worker detects unsafe content, stale context, cross-project memory, or a
branch mismatch, it stops and records a durable blocker or PO inbox item. It
must not silently fall back to old chat memory.

## Parallel Worker Use

Multiple workers may use the same approved context branch when each worker has:

1. Its own assignment lock.
2. Its own isolated workspace.
3. Its own delivery feature branch.
4. Its own evidence/log path.
5. The same verified context ref/hash.

The context branch is read-only for workers after publication. A changed source
document creates a new context branch revision/hash and workers must reload it
before continuing.
