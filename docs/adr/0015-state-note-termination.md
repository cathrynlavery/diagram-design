# ADR 0015: Preserve standalone states without accepting unfinished notes

Status: Implemented
Date: 2026-10-12

## Context

PR #392 retains bare state declarations. Note bodies can contain text that looks
like states, transitions or closing braces. An unfinished multiline note previously
silently consumed the remaining source and returned success.

## Decision

Track the opening source line while ignoring an opaque multiline state note.
Require `end note`; otherwise use the existing exit-2 diagnostic path. Inline notes
remain single-line annotations. Keep the standalone-state regression separately
named alongside the three import regressions merged in #410.

## Alternatives

Returning partial diagrams would conceal malformed input. Parsing note bodies as
states would introduce phantom structure. Both violate the import fidelity contract.

## Consequences

Valid note and state forms retain their meaning. Previously accepted unfinished
notes now report an error with the opening line number. No plugin version change.

## Validation

The new unterminated-left-note regression fails on the original PR head with exit
0, then passes for left and right notes after the fix. The full Mermaid import
verifier passes on the rebased candidate and independently in a separate review.
Tests also cover inline/adjacent notes, composite membership, concurrency separators
and special state shapes. Other gate outcomes are recorded in local review evidence.
