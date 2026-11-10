# UI V1 Frontend Handoff

Status: AP-75 frontend handoff package

Related Jira: AP-75, AP-71, AP-73, AP-74, AP-160

This handoff converts approved UI V1 discovery, architecture, wireframe, and
visual mockup artifacts into a frontend acceptance checklist. It is a design
handoff for future implementation stories. It does not authorize frontend
implementation by itself.

## Source Artifacts

Approved Jira and durable evidence inputs:

1. AP-71 - Define parsed, verified, and export data model requirements.
   Evidence:
   `data/agent-logs/AP-71/test-evidence-20260719T122804Z.md`.
2. AP-73 - Create low-fidelity UI V1 wireframes for approved screens.
   Handoff:
   `data/agent-logs/AP-73/ap-73-ui-v1-low-fidelity-wireframes-20260804.md`.
   Board:
   `data/agent-logs/AP-73/ap-73-ui-v1-wireframe-board-20260804.svg`.
   Snapshot:
   `data/agent-logs/AP-73/ap-73-ui-v1-wireframe-board-20260804.png`.
3. AP-74 - Create visual mockups for the first UI implementation slice.
   Handoff:
   `data/agent-logs/AP-74/ap-74-ui-v1-visual-mockups-handoff-20260805.md`.
   Board:
   `data/agent-logs/AP-74/ap-74-ui-v1-visual-mockup-board-20260805.svg`.
   Snapshot:
   `data/agent-logs/AP-74/ap-74-ui-v1-visual-mockup-board-20260805.png`.
4. AP-160 - Tested metric taxonomy and dashboard placement handoff, used by
   AP-73 and AP-74 for Parsed Summary metric placement.

Source product and architecture documents in the target repository:

1. `04-release-scope/release-2-ui-v1-product-discovery.md`
2. `03-nfr/ui-v1-privacy-security-product-requirements.md`
3. `01-architecture/release-2-ui-v1-architecture-plan.md`
4. `01-architecture/adr-002-ui-v1-parsed-verified-export-data-boundaries.md`
5. `01-architecture/ui-v1-pdf-lifecycle-and-guest-ownership.md`

## Scope Boundary

UI V1 first-slice frontend implementation may cover only:

1. Import / Parse
2. Parsed Summary
3. Delegation Editor
4. Export / Reports

The first-slice workflow is:

```text
Import PDF -> Parsed Summary -> fix warning-linked delegation rows -> Export verified draft
```

The wider UI V1 screen map from AP-73 remains design context, but Dashboard,
Schedule Review, and a dedicated Warnings / Unresolved Lines screen are not
first-slice visual implementation scope unless a later Product Owner-approved
frontend story promotes them.

The frontend must preserve the product boundary:

1. Independent and employer-agnostic product identity.
2. No airline logo, copied airline styling, official-employer claim, payroll
   claim, allowance claim, or accounting authority claim.
3. No permanent original PDF storage claim.
4. Guest-first import/review behavior unless a later Architecture-approved
   account story is READY TO START.
5. Generated exports are private drafts that require user or accountant
   verification.

## Stage 1 Source Review Result

The AP-75 dependency gate is satisfied because AP-74 is in `TEST COMPLETED`
and AP-71 is in `ACCEPTED/DONE`. No AP-75 source artifact introduces frontend
implementation approval. The handoff therefore prepares acceptance criteria for
future implementation stories and keeps Architecture-dependent work blocked
until the required contracts are created.

## Frontend Acceptance Checklist

Future frontend implementation stories must copy or reference this checklist
and keep any story-specific omissions explicit.

### Design Match

1. The implementation references the exact AP-74 visual mockup frame or local
   artifact used for the story.
2. The implemented route keeps the same screen purpose, primary action,
   secondary action hierarchy, warning placement, and privacy/disclaimer
   placement as the AP-74 mockup.
3. The neutral working identity stays independent and data-first. Do not add
   airline colors, airline logos, aircraft imagery, employer authority cues, or
   official payroll/accounting language.
4. Components preserve the AP-74 visual priority:
   - primary actions use the approved primary treatment;
   - warnings are amber and text-labelled;
   - destructive actions are red and text-labelled;
   - draft/privacy disclaimers remain readable body text.
5. The first-slice task stepper is informational. It must not imply completed
   backend persistence, account history, or public launch readiness.
6. Dashboard and Schedule Review navigation may appear only as disabled,
   future, or secondary context when the story explicitly includes them.

### Responsive Requirements

Frontend stories must validate the affected route at:

1. Wide desktop, with persistent navigation and full table where supported.
2. Medium width, with wrapped actions and two-column metrics where supported.
3. Narrow/mobile, with labelled navigation, one-column metric stacks, and a
   form or labelled overflow fallback for dense delegation rows.
4. 320 CSS pixels and 200 percent zoom, with no text overlap, hidden primary
   action, keyboard trap, or page-level horizontal overflow.

Dense table behavior:

1. Schedule/delegation table overflow must be inside a labelled region, not on
   the whole page.
2. Row insertion, row removal, undo, export, and warning navigation controls
   remain visible and keyboard reachable.
3. Hover-only insertion handles are optional only when supplemented by visible
   keyboard-reachable add-row controls.
4. Touch/narrow editing may use one-row detail forms, but must preserve the
   same typed fields, validation rules, warning links, and undo behavior.

### Required State Coverage

Every implementation story must include empty, loading, error, and success
states for each route it touches.

Import / Parse:

1. Empty: upload control, file requirements, authorization/privacy copy, parse
   action disabled until a valid PDF is selected.
2. Loading: parser progress/status text, cancel action where supported, no
   final metrics or raw PDF contents.
3. Error: safe reason, retry/reselect action, no echoed document text,
   filename detail, employee number, private path, or raw row.
4. Success: parser completion announcement and handoff to Parsed Summary.

Parsed Summary:

1. Empty: not directly routable before parse; return to Import with context.
2. Loading: skeleton metrics and parser status; no invented zero values.
3. Error: parse failed with retry/reselect action and safe error code.
4. Success: period/person summary, AP-160 metrics, parser warning banner, and
   primary action to edit delegations.

Delegation Editor:

1. Empty: no delegation candidates; allow an explicit first row only within
   the approved typed schema.
2. Loading: read-only placeholders; edit, undo, and export actions unavailable.
3. Error: draft-load/autosave error with retry and retained-local-edit message
   where applicable; never show a false `Saved` state.
4. Success: editable typed cells, optional `User note`, warning-linked rows,
   autosave status, undo last, undo all/restore parser result during active
   verification, add/remove row controls, validation summary, and export
   action.

Export / Reports:

1. Empty: no verified draft; return to Delegation Editor.
2. Loading: generation status, selected format retained, duplicate submission
   prevented.
3. Error: safe generation error and retry; no private object paths or storage
   keys.
4. Success: generated format, timestamp, verified revision, private download
   action, and guest/history deletion note.

### Privacy And Copy Obligations

The exact final legal copy remains a later Product Owner/legal/compliance
gate. Frontend stories must still place and test copy with the approved meaning
below.

Upload/import copy obligations:

1. Explain that the user must be authorized to process the document.
2. Explain temporary processing and deletion behavior without claiming full
   anonymity.
3. Explain that the service is independent and not affiliated with, endorsed
   by, or operated by any airline or employer.
4. Avoid displaying PDF contents, full filename details, employee numbers,
   private paths, raw rows, or generated report contents in errors, logs, or
   analytics.

Delegation/editor copy obligations:

1. Distinguish parser proposal, active verification draft, verified revision,
   and generated export.
2. Use neutral labels such as `Scheduled time` or `Block hours` only when the
   source supports the value.
3. Do not use paid, unpaid, payroll, allowance, entitlement, official, approved
   by employer, or similar authority language.
4. Make autosave status textual: `Saving`, `Saved`, or `Could not save`.

Export copy obligations:

1. Generated CSV, XLSX, and PDF outputs are private drafts.
2. Generated documents require user or accountant verification.
3. The app is not an official airline, employer, payroll, accounting, or
   delegation system.
4. Guest exports must not imply account history or permanent retention.

### Accessibility Requirements

Target: WCAG 2.2 AA.

1. Use native controls for file upload, buttons, radio choices, table/form
   editing, and row actions unless an approved component offers equivalent
   semantics.
2. Keep logical headings, labelled navigation landmarks, skip link behavior,
   visible focus, and keyboard order.
3. Warning and error states use text plus icon; color is never the only
   signal.
4. Upload progress, parser completion, autosave, validation errors, and export
   completion must be announced through appropriate status or alert regions.
5. Failed actions move focus to an error summary linked to the affected
   control, cell, or row.
6. Inserted row focus moves to the new row or row detail form.
7. Row removal is reversible through undo or confirmation and is announced.
8. Privacy/disclaimer text is visible body text, not tooltip-only content.
9. CSV/XLSX export UI must remind implementation to protect generated files
   from formula injection.

## Architecture-Blocked Frontend Stories

No frontend implementation story should move to `READY TO START` until its
backend/API, privacy, persistence, and deletion contracts are approved and the
Product Owner has approved the exact Jira story.

| Candidate frontend story | Required prerequisite before READY TO START |
| --- | --- |
| Import / Parse route | Upload API contract for guest mode, file validation limits, temporary PDF storage/deletion lifecycle, parser job/status response, safe diagnostic/error contract |
| Parsed Summary route | Parser result contract for period/person summary, AP-160 metrics, warning count/link payloads, unsupported metric behavior, safe diagnostic fields |
| Warnings integration | Warning category/severity payload, affected-row references, acknowledgement rules, blocking versus non-blocking warning behavior |
| Delegation Editor route | Typed delegation row schema, editable-field contract, row insert/remove API, autosave API, optimistic concurrency/error behavior, undo-last and restore-parser-result model |
| Export / Reports route | CSV/XLSX/PDF export API, verified revision contract, warning acknowledgement rule, report generation status, private download URL policy, formula-injection mitigation requirement |
| Guest-to-account save prompt | Authentication mode, account/session transfer contract, explicit-save rule, privacy copy, data retention/deletion behavior |
| Saved history and re-download | Registered-user persistence model, saved import/report metadata, deletion contract, report versioning, account deletion implementation |
| Dashboard route | Persisted metrics source, supported metric definitions, filters, no-payroll/allowance semantics, backend aggregation contract |
| Schedule Review route | Parsed schedule row schema, warning references, filter contract, raw-code preservation boundary, row-level uncertainty behavior |
| Public/private beta shell | Hosting/provider decision, cookie/analytics policy, Terms/Privacy/retention documents, security review, production logging redaction |

## V2 Or Later Candidates

Implementation agents must not expand UI V1 into these areas unless a later
Product Owner-approved Jira story explicitly promotes the work and all
Architecture prerequisites are satisfied:

1. Full analytics Dashboard beyond AP-160 must-have metric placement.
2. Schedule Review as a full implementation route outside warning/delegation
   links required for the first slice.
3. Monthly comparisons and code-specific trend analytics.
4. Country/airport stay-time analytics beyond the delegation workflow.
5. Native Apple Numbers export.
6. Public launch, marketing pages, public demo mode, or public user profiles.
7. Employer, airline, accounting-company, supervisor, payroll, or back-office
   views.
8. Payroll, allowance, entitlement, official accounting, contract, or legal
   schedule-code interpretation.
9. Reduced-verification or auto-approve workflows before parser quality,
   warning semantics, and legal/business approvals are explicit.
10. Automated Figma/API/plugin integration unless Product Owner approves access,
    cost, permissions, and storage model.

## Acceptance Criteria Trace

| AP-75 criterion | Handoff coverage |
| --- | --- |
| R2-P1-S7-AC1 | `Source Artifacts` references AP-71, AP-73, AP-74, AP-160, and target product/architecture docs. |
| R2-P1-S7-AC2 | `Frontend Acceptance Checklist` defines design match, responsive behavior, required states, privacy/copy obligations, and accessibility behavior. |
| R2-P1-S7-AC3 | `Architecture-Blocked Frontend Stories` identifies candidate frontend stories and their backend/API/privacy/persistence/deletion prerequisites. |
| R2-P1-S7-AC4 | `V2 Or Later Candidates` records excluded UI V1 expansion areas so implementation agents do not promote them accidentally. |

## Handoff Use

Future frontend stories should include:

1. The specific AP-74 frame or local artifact reference.
2. The route or component subset from this checklist.
3. The backend/API contract version used by the route.
4. The story-specific validation commands for unit, accessibility, responsive,
   and screenshot/design-match checks.
5. A statement that public launch, account history, Dashboard expansion, and
   payroll/accounting semantics are out of scope unless promoted by that story.
