# Regression Artifact Publication

Status: implemented for MVP Sprint 10

This helper turns a regression manifest plus already-delivered helper outputs
into one publishable bundle for Release Manager review.

## Goal

The helper exists so AGENT-198 can stay narrow.

It does not recreate:

1. Regression manifest records from AGENT-135.
2. Evidence comment, attachment, and link primitives from AGENT-134.
3. Overview Task visibility rules from AGENT-133.
4. Test Execution create-or-update logic from AGENT-336.

Instead, it composes those pieces into one dry-run or live-ready bundle.

## Bundle Contents

The bundle contains:

1. Manifest key.
2. Overview Task reference.
3. Test Execution reference.
4. Included Test Case keys.
5. Durable evidence path.
6. Focused regression result summary.
7. Full-suite result summary.
8. One `EvidencePublicationRequest` when enough data exists.
9. Readiness warnings when important inputs are missing.

## Composition Rules

The helper uses:

1. Manifest records as the source of Test Case keys, evidence paths, and result
   scope.
2. AGENT-134 evidence publication planning for comments, attachments, and
   links.
3. AGENT-336 Test Execution upsert output when a create-or-update plan is
   already available.

If no upsert plan is provided, the helper can still publish around an existing
Test Execution key already present in the manifest references.

## Warnings

The helper emits explicit warnings for missing:

1. Overview Task key.
2. Test Execution reference or upsert plan.
3. Included Test Cases.
4. Durable evidence path.
5. Focused result summary.
6. Full-suite result summary.

Warnings do not guess hidden business decisions. They tell Release Manager what
still needs to be supplied before publication is complete.
Bundles with warnings stay in a not-ready state even if some publish actions can
already be previewed in dry run.

## Dry Run

Dry-run output renders the exact planned comments, attachments, and links so
Release Manager can inspect the publication surface before a live adapter is
used.
