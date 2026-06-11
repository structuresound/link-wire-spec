# Provenance rules — spec side ("dirty room")

This repository is the **dirty side** of a clean-room reimplementation
process. Its authors read the GPL-licensed reference implementation
(`Ableton/link`) in order to document protocol facts. The implementation
repository ([link-wire-rs](https://github.com/structuresound/link-wire-rs))
is the **clean side** and must never consume the reference source — only the
artifacts published here.

## Rules for spec authors

Spec authors MAY:

- Read the reference source, run reference binaries (`LinkHut`,
  `link_audio_hut`), and capture their network traffic. GPLv2 restricts
  distribution of the code, not use or observation.
- Document any wire-mandated fact: byte layouts, field sizes, endianness,
  magic constants, message type numbers, ports, multicast addresses, size
  limits, enum values, timing constants, state machines, and observable
  behavior.
- Cite public non-GPL sources, e.g. F. Goltz, *"Ableton Link — A technology
  to synchronize music software"* (Linux Audio Conference 2018).

Spec authors MUST NOT:

- Copy any source code, pseudo-code that mirrors source structure, or
  comments from the reference implementation into this repository — not in
  spec text, not in issues, not in commit messages, not in triage notes.
- Reproduce internal naming or file/class structure beyond what the wire
  itself mandates. Describe behavior as protocol requirements, not as a
  paraphrase of the code.

The spec is the contamination boundary. If expression from the reference
leaks into the spec, it can leak into every downstream implementation. When
in doubt, express the fact as a table, equation, or state machine.

## Artifacts and licenses

| Artifact | License | Notes |
|---|---|---|
| Spec text (`spec/`) | CC-BY-4.0 | facts only, per the rules above |
| Test vectors (`vectors/`) | CC0 | packet captures of reference peers; protocol facts |
| Tooling (workflows, capture scripts, conformance harness) | MIT | the harness (`conformance/`) contains no protocol logic: it asserts on observable endpoint behavior only |

Reference binaries are built from upstream in CI for capture and conformance
purposes and are never redistributed from this repository.

## Firewall: rules for implementers (enforced in link-wire-rs)

Implementations claiming clean-room provenance from this spec may use ONLY:

1. Released versions of this specification and its test vectors.
2. The released conformance harness (`conformance/`) — which the clean side
   may execute against its candidate, fetching this repository at a release
   tag into CI caches only (never vendoring it) — and the harness's results
   phrased as observations (pass/fail, measured behavior) — never as
   reference-source diffs. The harness is authored on the dirty side and is
   releasable because it contains no protocol implementation logic.
3. Public non-GPL documentation (the Goltz paper, Ableton's public help
   pages and FAQ).

Forbidden inputs: the `Ableton/link` and `Ableton/LinkKit` repositories and
any diffs of them; GPL-licensed implementations including `ableton-link-rs`
(GPLv3) and the bound portions of `rusty_link`; any decompilation of shipped
Ableton products.

## Maintenance without breaking the firewall

When upstream moves (see `upstream-watch` workflow and `LAST_REVIEWED_SHA`):

1. **Triage (dirty side):** classify each upstream commit — *no wire impact*
   (advance pin), *behavioral change* (spec errata + regenerate vectors), or
   *wire-format change* (chapter revision + spec version bump).
2. **Spec release:** changelog entry records the verdict per commit and the
   new pin.
3. **Implementation update (clean side):** implementers receive the spec
   *diff* and new vectors only.
4. **Audit:** new implementation code is reviewed for similarity against the
   reference before release, as a backstop — the same backstop traditional
   clean rooms use.

The empirical tripwire is the implementation repo's canary CI job (interop
against upstream HEAD), which detects drift that editorial triage misses.

## Agent provenance

Spec text in this repository may be authored by AI agents operating under
these rules. Agent sessions that read the reference source are permanently
"dirty" and never author implementation code. Session transcripts
demonstrating what inputs an author had access to are retained where the
tooling supports it; this is an *additional* evidence trail on top of, not a
substitute for, the rules above.
