# Context Pack Generator

The context pack generator creates durable worker execution snapshots from
approved Jira and documentation inputs.

Context packs do not replace Jira, Confluence, or local documentation. Those
remain the source of truth. A context pack packages approved inputs so a worker
can execute one Jira issue without rereading the whole repository or guessing
missing requirements.

## Timing

Generate a context pack only after:

1. The Product Owner moves the issue to `READY TO START`.
2. Dependency checks show no unresolved blockers.
3. Story description, acceptance criteria, documentation references, model
   routing, and expected outputs are available.
4. If the selected route requires different Codex settings than the current
   session, the manual switch checkpoint is prepared for the Product Owner.

If context is missing or unclear, create a Product Owner question and stop
instead of generating an executable pack.
For the planning-to-development session handoff that precedes this timing, see
`docs/session-mode-planning-handoff-validation.md`.

For Codex-spending assignments, the context pack or assignment metadata must
identify the platform instruction root so the worker can load
`.agents/skills/codex-quota-guard/SKILL.md`. Do not embed Codex credentials,
raw account identifiers, target-project secrets, unresolved assumptions, or
project-specific memory in the context pack; record only the configured durable
limit root, account scope label, bucket id, and evidence path needed for a
fresh guard decision.

## Outputs

The generator writes:

1. `data/context-packs/{ISSUE_KEY}/context-pack.md`
2. `data/context-packs/{ISSUE_KEY}/context-pack.json`

The Markdown file is PO-readable. The JSON file is machine-readable for worker
containers and the host-side Codex runner.

When a sprint path resolver artifact marks a story as stacked, the generator
copies the resolved stack metadata into both files. Workers must read this
metadata before deciding branch base, PR order, test timing, or handoff route.
If the context pack has no `stack_metadata` object or every stack field is
empty, the story is treated as non-stacked and existing worker behavior applies.

## CLI

Generate from approved source JSON:

```bash
agentic context-pack generate --input approved-context-source.json
```

Use a custom context-pack root:

```bash
agentic context-pack generate \
  --input approved-context-source.json \
  --context-pack-root data/context-packs
```

Generate draft packs for every story in a saved backlog draft:

```bash
agentic context-pack generate-from-backlog-draft \
  --draft-path data/backlog-drafts/REQ-R1.json \
  --context-pack-root data/context-packs \
  --target-repo-path /workspace/target-project \
  --documentation-reference docs/product/scope.md="Approved PO scope"
```

This batch command is for Product Planning handoff before Jira promotion. It
writes one context pack per draft story so future workers can see the approved
source docs, acceptance criteria, planned role/model routing, sprint ring, and
draft prerequisites without rereading the whole repository.

Before generating draft packs from approved docs, Product Planning should run
the documentation-to-backlog traceability audit in
`docs/documentation-to-backlog-traceability-audit.md`. Context packs should
reference the report when it influenced story slicing, missing-scope routing,
or Product Owner backlog approval.

Draft prerequisites are recorded in `shared_context`, not executable dependency
gates, because Jira issue keys and live dependency statuses may not exist yet.
After PO approval creates Jira stories and moves work to `READY TO START`, the
normal single-story context pack flow can regenerate executable packs with live
Jira dependency status.

## Source JSON Shape

```json
{
  "issue_key": "AGENT-42",
  "summary": "Implement Context Pack Generator",
  "issue_type": "Story",
  "status": "READY TO START",
  "sprint": "MVP S7 Developer",
  "role": "developer",
  "branch_name": "feature/AGENT-42-context-pack-generator",
  "target_repo_path": "/workspace/sample-project",
  "created_at": "2026-06-24T08:00:00Z",
  "routing": {
    "model": "gpt-5.4",
    "reasoning": "high",
    "speed": "normal",
    "complexity": "C3",
    "effort_mode": "complex",
    "rationale": "Development defaults to gpt-5.4 high from the role matrix.",
    "routing_source": "role",
    "role_instruction_path": "ai_agents/roles/developer.md",
    "role_instruction_version": "release-1.1",
    "role_routing_override_reason": "",
    "manual_switch_required": true,
    "manual_switch_prompt": "Before starting AGENT-42, switch Codex to gpt-5.4 with high reasoning and normal speed for the developer role."
  },
  "acceptance_criteria": [
    "Context packs are generated from approved Jira and docs."
  ],
  "dependencies": [
    {
      "issue_key": "AGENT-41",
      "status": "Accepted/Done",
      "summary": "Scheduler approved scope assignment",
      "satisfied": true
    }
  ],
  "stack_metadata": {
    "stack_id": "stack-agent-687",
    "lane_id": "stack-lane-agent-687",
    "stack_trunk": "main",
    "stack_layer": 2,
    "parent_story_key": "AGENT-687",
    "child_story_keys": ["AGENT-689"],
    "parent_branch": "feature/AGENT-687-stacked-pr-path-resolver",
    "base_branch": "feature/AGENT-687-stacked-pr-path-resolver",
    "pull_request_number": 0,
    "pull_request_url": "",
    "testability_state": "after-stack-layer-merge"
  },
  "documentation_references": [
    {
      "path": "docs/story-complexity-model.md",
      "description": "Model and reasoning routing.",
      "required": true
    }
  ],
  "design_references": [
    {
      "source_type": "figma",
      "url": "https://www.figma.com/file/example",
      "frame": "Operator Inbox - Accepted",
      "artifact_path": "docs/design/operator-inbox.png",
      "description": "Accepted UI/UX design frame for frontend implementation.",
      "required": true
    }
  ],
  "shared_context": [
    "Jira and docs remain the source of truth."
  ],
  "role_specific_context": [
    {
      "role": "developer",
      "instructions": [
        "Create implementation subtasks before code changes."
      ]
    }
  ],
  "test_expectations": [
    "Run focused unit tests for the context pack schema."
  ]
}
```

## Stacked PR Metadata

`stack_metadata` is optional and backward compatible. It is required only when
the resolved sprint path says the story is `stacked-dependent`.

Required stacked fields:

1. `stack_id`
2. `lane_id`
3. `stack_trunk`
4. `stack_layer`
5. `base_branch`
6. `testability_state`

Optional stacked fields:

1. `parent_story_key`
2. `child_story_keys`
3. `parent_branch`
4. `pull_request_number`
5. `pull_request_url`

Developer, Review, Tester, and Release Manager agents must not reinterpret the
sprint dependency graph when this metadata is present. They use the context pack
values and stop with a PO inbox question if Jira or the assignment record
contradicts them.

## Validation Rules

Executable context requires:

1. Issue metadata.
2. Branch and repository path.
3. Model, reasoning, and speed routing.
4. Routing source and rationale.
5. Role instruction path and version.
6. Role routing override reason when the selected route differs from the role
   matrix.
7. Manual switch prompt when the next task needs different Codex settings.
8. Markdown and JSON output paths.
9. At least one acceptance criterion.
10. At least one approved documentation reference.
11. Design references include a source type and either a URL or local artifact
    path when UI/UX handoff is required.
12. All listed dependencies marked satisfied.
13. No open Product Owner questions.

Validation messages report field names and rule failures only. They do not echo
prompt text, Product Owner answers, token values, or secret-like content.

## Figma And Manual Design References

Design references are first-class context pack source links. UI/UX and Frontend
agents use them to find the accepted design before touching UI code.

Supported baseline sources:

1. `figma` for a Figma file, page, component, or frame link.
2. `figma_export` for exported PNG, PDF, or SVG snapshots.
3. `local_html_mockup` for local review artifacts produced by a design story.
4. `manual_link` for project-specific design references when direct access is
   unavailable.

If a required design reference is missing or inaccessible, the worker creates a
Product Owner inbox question instead of inventing the UI. Direct Figma API or
plugin access remains optional and must be configured explicitly by the Product
Owner.
