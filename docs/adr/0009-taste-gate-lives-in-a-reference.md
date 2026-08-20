# ADR 0009 — The taste gate moves to a reference; the connector rules stay in SKILL.md

**Status:** accepted (v2.5.18)

## Context

ADR 0004 set `MAX_SKILL_BYTES` at 40,000 and ruled that the frontmatter `description` — the only
text an agent reads before deciding to load the skill — is never traded for body prose. At
v2.5.15, after ADR 0007 admitted ten new types, `SKILL.md` was 38,874 bytes: 97% of the cap,
less than one visual type of headroom.
Adding a type is not optional prose. It costs a §3 selection row, a §7 budget row, and a
lexical hook in the description that `verify-docs-sync.py` requires. The next type would have
hit the cap, and the cheapest way out of that corner is the wrong one — cutting the description.

Two sections were candidates for extraction. §9, the pre-output checklist, was 3,808 bytes.
§6, the core SVG primitives, was 9,673 — by far the largest, and the tempting answer.

## Decision

1. **§9 moves to [`references/taste-gate.md`](../../skills/diagram-design/references/taste-gate.md).**
   `SKILL.md` keeps the heading, a five-group summary, and the link. The gate is read **once,
   after the diagram is drawn**, which is exactly the shape progressive disclosure is for: it is
   never needed while choosing a type, and loading it at the end costs one read on the jobs that
   produce a diagram and nothing on the jobs that don't.
2. **§6 stays in `SKILL.md`.** Its rules — elbow connectors, attach-point fanning, label masks,
   paint order — apply to *every* diagram of every type. Moving them out would not defer a read;
   it would add an indirection to a file that is loaded anyway, and it would break the `§6`
   citations that twelve files across references, commands, ADRs, and `verify-geometry.py`
   depend on. Byte count is not the only cost worth minimizing.
3. §0 and §11 are compressed in place rather than moved. Both keep the strings the verifiers
   pin — the §11 heading and its `import-drawio.md` / `output-spec.md` / `drawio_extract.py`
   references, checked by `verify-drawio-import.py` — while dropping wording that restates
   `profiles.md`, `onboarding.md`, and `output-spec.md`.

## Consequences

- `SKILL.md` is 35,287 bytes, leaving ~4,700 of headroom: room for several types rather than
  a fraction of one.
- The taste gate is now a file an installed agent must read to run, so a type reference or command
  that tells the agent to "run the §9 gate" is telling it to load `taste-gate.md`. Both phrasings
  point at the same content; keep the §9 numbering stable so existing citations stay valid.
- The size threshold that should trigger the next extraction is a section that is large *and*
  read late. If a future candidate is large but read on every diagram, compress it in place —
  do not move it and call the cap satisfied.
