# Release 1.1.0 Regression Scope

Status: release candidate regression plan for `AGENT-455`

This scope covers behavior delivered in Release 1.1.0 and the supporting
workflows that protect Product Owner control.

## Required Regression Areas

1. PO inbox path/schema guard and CLI/API behavior.
2. PO inbox operator UI list, read, answer, approve, reject, and archive flows.
3. First-project setup validation and durable path checks.
4. Codex limit record, status, pause/resume, and operator-visible status views.
5. Role instruction files, session starter prompts, and session-mode validation
   playbooks.
6. Developer, Review, Tester, and Release Manager delivery-session flow.
7. Docker worker requirements, credential/volume safety, trigger handoff, and
   parallel workspace isolation docs.
8. Security threat model, secret redaction, no-secret logging, and operator UI
   no-secret display rules.
9. Release track/version policy and release notes visibility.
10. Assignment scheduling, dependency co-scheduling, sprint acceptance, and
    sprint closure automation.

## Recommended Test Commands

```bash
git diff --check
PYTHONPATH=src python -m pytest
npm --prefix ui/operator run build
```

When the UI build is run from a Windows-mounted WSL path and Vite hangs, copy
`ui/operator` to a Windows temp directory and run `npm ci && npm run build`
there, then record the workaround in evidence.

## Current Candidate Evidence

Sprint 5 regression passed on main at
`99aa523d25daac5806b7d21daa84376a34d67c47`:

1. Targeted Sprint 5 regression: 91 passed.
2. Full Python suite: 616 passed.
3. No regression bugs found.

Final Release 1.1 regression should include all required regression areas above
after AGENT-455 is merged.
