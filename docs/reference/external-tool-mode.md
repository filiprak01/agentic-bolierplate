# Public Main External-Tool Mode

Public `main` intentionally omits root `AGENTS.md` and `CLAUDE.md` while the
Product Owner uses an external development tool. No other role files, skills,
target-project templates, runtime data, or release refs are removed.

The original instruction content is preserved without auto-discovery filenames:

- [Platform agent instructions](platform-agent-instructions.md)
- [Claude handoff](claude-handoff.md)

These reference copies retain the Release 1.2.0 text. References in that text
to the platform `AGENTS.md` mean the platform reference above when using public
`main`; target-project `AGENTS.md` files are unaffected. Existing role/session
starter guidance can be loaded explicitly using this substitution.

Explicit worker startup and validation prefer a root `AGENTS.md` when present,
otherwise use the platform reference. Both missing is still a validation error.
Removing auto-discovery entrypoints does not waive PO, design, dependency,
quota, review, or security requirements for platform workers.

## Complete Stable Fallback

`release/1.2.0` and immutable tag `v1.2.0` retain both original root files at
commit `5ab75997ac3bc49eb23e43b1e155935b50e95e5e`.

Preserve local work before switching versions. Inspect the immutable snapshot:

```bash
git fetch origin --tags
git switch --detach v1.2.0
```

Alternatively switch to the maintained `release/1.2.0` branch. Do not move the
tag or merge the external-tool cleanup into that branch.

To restore only the two root files in a working checkout without switching:

```bash
git restore --source=v1.2.0 -- AGENTS.md CLAUDE.md
```

This creates local files for explicit opt-in; it does not publish a change.
Root auto-discovery starts applying again once those files are restored.
