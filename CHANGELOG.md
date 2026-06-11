# Changelog

All notable changes to this specification. Every entry records the upstream
pin (`Ableton/link` commit) the spec describes at that version.

## [0.1.0] — 2026-06-11

First complete release. Spec text plus test vectors; this is the only artifact
the clean-side implementation ([link-wire-rs](https://github.com/structuresound/link-wire-rs))
is permitted to consume.

Upstream pin: `902aef95bf94af49746fdda5369b42cdcfa1e6d2` (2026-05-19).

### Added

- **Chapter 1 (Discovery):** completed from stub — multicast transport
  (`224.76.78.75:20808` v4, `ff12::8080` port 20808 v6), `_asdp_v\x01` framing,
  Alive/Response/ByeBye message types, peer-state payload entries (`tmln`, `sess`,
  `stst`, `mep4`/`mep6`, `aep4`/`aep6`) with the family-switch rule, ttl-based
  timeout/pruning, and full byte layouts.
- **Chapter 2 (Sync):** completed from stub — `_link_v\x01` ping/pong measurement
  protocol, `__ht`/`__gt`/`_pgt`/`sess` entries, the ghost-time transform and median
  offset filter, the `tmln` timeline model with beat-origin priority, session
  election/merge rules (ghost-time-wins with session-id tie-break), `stst` start/stop
  propagation, and the quantum/phase model. Algorithm rationale cited to F. Goltz,
  "Ableton Link — A technology to synchronize music software," LAC 2018.
- **Test vectors** (`vectors/*.pcap`, CC0): `discovery-join-leave`,
  `sync-tempo-change`, `sync-start-stop`, `audio-channel-lifecycle`, each described in
  `vectors/README.md`.
- **Capture rig** (`tools/capture-vectors.sh`, MIT) and CI workflow
  (`.github/workflows/capture-vectors.yml`) that build the pinned reference and record
  the scenarios above. Reference source is cloned outside the repo and never vendored.

### Open-question verdicts

Resolved against the captures and reference runtime behavior:

| # | Chapter | Question | Verdict |
|---|---|---|---|
| 00-§4.2 | Overview | string length `N` not bound-checked before construction | Bound is normative for implementations (`N` > remaining ⇒ parse error). Not exercisable by golden vectors; no on-wire string exceeds its region. |
| 00-§4.5(7) | Overview | are duplicate payload-container keys ever legitimate? | No. Never emitted in any vector; senders MUST NOT emit duplicates, receivers apply last-one-wins defensively. |
| 03-1 | Audio | does an `_abu` header precede the AudioBuffer structure? | **No** — confirmed by `audio-channel-lifecycle.pcap`; payload begins bare with the channel id. |
| 03-2 | Audio | do receivers enforce a 1176- vs 1180-byte payload ceiling? | No receive-side ceiling; bounded only by the 1200-byte socket buffer (≤1180 payload). 24-byte budget is sender-side only. |
| 03-3 | Audio | exact derivation of the 50-byte non-audio allowance | None — it is a hand-chosen fixed allowance; the encoder subtracts the real chunk-list size at runtime. Implementations need not reproduce 50. |
| 03-4 | Audio | receiver behavior for names > 256 bytes | 256-byte cap is sender-side only; receivers accept longer length-prefixed names, bounded by the payload. |
| 03-5 | Audio | handling of unknown nonzero codec values | Reference parses and decodes as PCM i16 (no recheck); only codec 1 ever transmitted. Spec recommends implementations reject unknown codecs. |
| 03-6 | Audio | semantics of nonzero `groupId` | Reserved; reference sends 0 and drops nonzero. All captured traffic uses 0. MUST send 0, MUST ignore nonzero. |
| 03-7 | Audio | duplicate payload entries legitimate? | Same as 00-§4.5(7): no. |
| 03-8 | Audio | cross-host usability of advertised IPv6 (`aep6`) addresses | **Deferred** — requires `discovery-ipv6.pcap`, not producible in the v0.1.0 capture environment (no interface with both IPv4 and link-local IPv6). Carried to the next release. |

## [0.1.0-draft] — initial scaffolding

- Provenance rules, upstream-watch workflow, version pin.
- Drafts: 00-overview (serialization, transport model), 03-audio (LinkAudio v1).
  Chapters 01-discovery and 02-sync were stubs.
- Upstream pin: `902aef95bf94af49746fdda5369b42cdcfa1e6d2` (2026-05-19).
