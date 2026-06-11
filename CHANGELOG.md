# Changelog

All notable changes to this specification. Every entry records the upstream
pin (`Ableton/link` commit) the spec describes at that version.

## [0.4.0] — 2026-06-11

Upstream pin: `902aef95bf94af49746fdda5369b42cdcfa1e6d2` (2026-05-19) — unchanged
from 0.1.0; upstream has not moved past the pin. Versions 0.2.x–0.3.x were never
released; this release consolidates the discovery/sync chapter revision pass, the
capture-rig audit, and the final audio open-question resolution.

### Verified

Every protocol claim in Chapters 0–2 was re-verified line-by-line against the
pinned reference source (dirty-side analysis): framing and the strict
encoder/receiver size asymmetry, all message types, broadcast pacing
(50 ms minimum / `ttl·1000/ttlRatio` nominal), respond-before-process ordering,
prune-timer semantics, ping/pong payload shapes and the 32-byte responder
admission bound, both offset estimators and the >100-sample median completion,
the session join rule with ε = 500,000 µs and the id tie-break,
measurement-target selection (founder preferred), the 30 s re-measurement
schedule, beat-origin timeline priority including the
`max(now-beats, origin+1 µbeat)` modification rule, the 20–999 bpm receive-side
re-clamp, `stst` field order and latest-timestamp-wins propagation, the
session-peer-count-zero full reset (fresh NodeId), and the exact phase-encoding
equations including the inverse's opposite tie-break. No discrepancy was found;
all corrections below are additions, not retractions.

### Changed

- **Chapter 1 (Discovery):** documented the immediate Alive on gateway open
  (before the first nominal period) [B]; ByeBye for an unknown peer is a no-op
  [B]; sharpened the IPv6 gateway rule — every admitted IPv6 gateway address, and
  hence every advertised IPv6 endpoint, is a non-loopback **link-local**
  (`fe80::/10`) address, on all platforms with an IPv6 path [B].
- **Chapter 2 (Sync):** sharpened §7.3 — the 30 s re-measurement loop runs on
  peers that **joined** a foreign session; a founder still in its own session
  does not re-measure (its transform is exact by construction) [B]. Added to
  §7.2: after a join the abandoned session is retained in the known-sessions
  cache with its measurement (no re-measurement on re-encounter), and cached
  sessions' timelines follow the same beat-origin priority rule [B].
- **Chapter 3 (Audio):** resolved the last open question (see verdicts below);
  §2's IPv6-scope rule now cites the grounds.
- Chapter version stamps bumped to 0.4.0; vectors README updated for the
  question-8 verdict.

### Capture-rig audit

The full rig (`tools/build-reference.sh` + `tools/capture-vectors.sh` +
`capture-vectors.yml`) was exercised end-to-end in a fresh Linux environment:
reference built from the pinned SHA, all five capturable scenarios ran in
isolated network namespaces, manifests regenerated, and **every structural
assertion in `tools/check_vectors.py` passed**. The audit run reproduced the
released vectors' structural facts exactly (peer-state datagram sizes 107/121,
sync shapes 25/57/41/73, codec 1 only, keepalive repetitions, mid-stream tempo
change in chunks, multi-gateway announcements), differing only in the documented
per-run randomness (NodeIds, ephemeral ports, timestamps). The released v0.1.0
vectors remain the released evidence — captures are not byte-reproducible, so
re-capturing without cause would only churn the evidence base. The
`discovery-ipv6` scenario again skipped correctly: this environment's kernel,
like v0.1.0's, has no IPv6 support.

### Open-question verdicts

| # | Chapter | Question | Verdict | Evidence |
|---|---|---|---|---|
| 03-8 | Audio | cross-host usability of advertised IPv6 (`aep6`/`mep6`) endpoints, scope ids not being transmitted | **Resolved.** Usable cross-host on (and only on) the link they were learned on. All advertised v6 endpoints are link-local addresses (platform scanners admit only non-loopback `fe80::/10` v6 gateways); the v6 discovery group `ff12::8080` is link-local scope, so the receiving interface shares the advertiser's link and the scope substitution is correct by construction. Implementations MUST use a learned v6 endpoint only via the gateway it was learned on. | [B] reference analysis; rule [N]. A future `discovery-ipv6.pcap` raises this to [W] but is no longer needed to answer the question. |

With this verdict, **no OPEN QUESTION remains in any chapter.**

## [0.1.0] — 2026-06-11

First complete release. Spec text plus test vectors; this is the only artifact
the clean-side implementation ([link-wire-rs](https://github.com/structuresound/link-wire-rs))
is permitted to consume.

Upstream pin: `902aef95bf94af49746fdda5369b42cdcfa1e6d2` (2026-05-19).

### Evidence model

Every claim in the spec is tagged with how it is known (Chapter 0 §1.1): **[W]**
wire-observed (pinned to a released capture via auto-generated manifests and
structural assertions), **[B]** behavioral (dirty-side analysis of the reference,
not exercised by the captures), or **[N]** normative (a requirement of this spec).
Observable facts about the vectors — topology, gateways per peer, message-type
counts, datagram shapes — are *generated from the capture bytes* by
`tools/analyze_pcap.py` into `vectors/manifests/`, and each capture must pass the
per-scenario structural assertions in `tools/check_vectors.py` before release.

### Added

- **Chapter 1 (Discovery):** completed from stub — multicast transport
  (`224.76.78.75:20808` v4, `ff12::8080` port 20808 v6), `_asdp_v\x01` framing,
  Alive/Response/ByeBye message types, peer-state payload entries (`tmln`, `sess`,
  `stst`, `mep4`/`mep6`, `aep4`/`aep6`) with the family-switch rule, ttl-based
  timeout/pruning, socket-configuration facts with wire-visible consequences
  (notably: multicast loopback only on loopback-address gateways), and full byte
  layouts.
- **Chapter 2 (Sync):** completed from stub — `_link_v\x01` ping/pong measurement
  protocol, `__ht`/`__gt`/`_pgt`/`sess` entries, the ghost-time transform and median
  offset filter, the `tmln` timeline model with beat-origin priority, session
  election/merge rules (ghost-time-wins with session-id tie-break, including its
  behavior under measurement noise), `stst` start/stop propagation, and the
  quantum/phase model with the exact inverse phase-encoding equations. Algorithm
  rationale cited to F. Goltz, "Ableton Link — A technology to synchronize music
  software," LAC 2018.
- **Test vectors** (`vectors/*.pcap`, CC0), each captured in an isolated network
  namespace with a generated manifest: `discovery-join-leave`, `sync-tempo-change`,
  `sync-start-stop`, `audio-channel-lifecycle` (including request keepalive
  repetitions and a mid-stream tempo change), `multi-gateway-discovery`.
- **Tooling** (MIT): `tools/capture-vectors.sh` (netns-isolated scenario rig),
  `tools/analyze_pcap.py` (field-level decoder + manifest generator),
  `tools/check_vectors.py` (structural assertions), with CI workflows
  `capture-vectors.yml` and `upstream-watch.yml`. Reference source is cloned
  outside the repo and never vendored.
- **Conformance harness** (`conformance/`, MIT): drives a reference peer and a
  candidate (any program speaking `CANDIDATE-CONTRACT.md`) through the
  vector scenarios — discovery join/leave, tempo follow, start/stop, beat
  phase alignment, audio announce→subscribe→stream→bye — emitting pass/fail
  observations as plain text. Contains no protocol logic (assertions are on
  observable endpoint behavior only); self-tests reference-vs-reference in CI
  (`conformance-selftest.yml`); ships an example workflow for candidate
  repositories. Homed in this repo so the dirty-side-authored harness stays
  behind the release gate; the clean side consumes it from a release tag
  (PROVENANCE.md firewall item 2).

### Open-question verdicts

| # | Chapter | Question | Verdict | Evidence |
|---|---|---|---|---|
| 00-§4.2 | Overview | string length `N` not bound-checked before construction | Bound is required of implementations (`N` > remaining ⇒ parse error). No on-wire string exceeds its region. | [B] reference analysis; [N] requirement; benign case [W] |
| 00-§4.5(7) | Overview | are duplicate payload-container keys ever legitimate? | No. Senders MUST NOT emit duplicates; receivers apply last-one-wins. (Systematic near-exception: the sync pong's verbatim echo, Ch.2 §4.1.) | absence [W]; semantics [B]; rule [N] |
| 03-1 | Audio | does an `_abu` header precede the AudioBuffer structure? | **No** — payload begins bare with the channel id. | [W] asserted over every captured AudioBuffer |
| 03-2 | Audio | do receivers enforce a 1176- vs 1180-byte payload ceiling? | No receive-side ceiling; bounded only by the 1200-byte socket buffer. 24-byte budget is sender-side only. | [B]; not exercised by any vector |
| 03-3 | Audio | exact derivation of the 50-byte non-audio allowance | None — hand-chosen fixed allowance; encoder subtracts the real chunk-list size at runtime. | [B]; resulting 502-byte cap [W] |
| 03-4 | Audio | receiver behavior for names > 256 bytes | Cap is sender-side only; receivers accept longer length-prefixed names. | [B]; not exercised by any vector |
| 03-5 | Audio | handling of unknown nonzero codec values | Reference parses and decodes as PCM i16 (no recheck). Spec recommends rejecting unknown codecs. | [B]; codec-1-only traffic [W]; recommendation [N] |
| 03-6 | Audio | semantics of nonzero `groupId` | Reserved; MUST send 0, MUST ignore nonzero. | send-0 [W]; drop-nonzero [B]; rule [N] |
| 03-7 | Audio | duplicate payload entries legitimate? | Same as 00-§4.5(7): no. | as above |
| 03-8 | Audio | cross-host usability of advertised IPv6 (`aep6`) addresses | **Deferred** — requires `discovery-ipv6.pcap`; the capture environment's kernel has no IPv6 support. The rig emits it automatically where IPv6 exists. | open |

## [0.1.0-draft] — initial scaffolding

- Provenance rules, version pin.
- Drafts: 00-overview (serialization, transport model), 03-audio (LinkAudio v1).
  Chapters 01-discovery and 02-sync were stubs.
- Upstream pin: `902aef95bf94af49746fdda5369b42cdcfa1e6d2` (2026-05-19).
