# Chapter 2 — Link Clock Sync and Timeline Protocol (STUB)

| | |
|---|---|
| Spec version | 0.1.0-draft |
| Upstream reference | Ableton/link @ `902aef95bf94af49746fdda5369b42cdcfa1e6d2` |
| License | CC-BY-4.0 |

This document describes protocol facts determined from observation and analysis for
interoperability purposes. It contains no copied expression from the reference
implementation.

---

## Scope

This chapter will specify how peers in a session converge on a shared timeline: the
unicast UDP ping/pong measurement protocol served at each peer's advertised
measurement endpoint (`mep4`/`mep6`), the host-time/global-host-time payload entries
(`__ht`, `__gt`, `_pgt`), the clock-offset filtering model, the timeline payload
(`tmln`: tempo, beat origin, time origin), session election and merging, and the
start/stop state (`stst`) propagation rules.

## TODO

- [ ] Measurement message framing and the ping/pong exchange sequence.
- [ ] Payload entries `__ht` (0x5f5f6874), `__gt` (0x5f5f6774), `_pgt` (0x5f706774): layouts and roles in offset estimation.
- [ ] Measurement scheduling: number of pings, intervals, retry/timeout behavior, measurement completion criteria.
- [ ] Clock-offset estimation and filtering as a normative algorithm description.
- [ ] Timeline encoding (`tmln`): tempo as µs/beat, beat origin in micro-beats, time origin in µs; 24-byte layout.
- [ ] Session identity, election (which peer's timeline wins), and merge behavior when sessions meet.
- [ ] Start/stop state (`stst`) encoding and propagation, including timestamps for conflict resolution.
- [ ] Quantum and phase model shared with Chapter 3 §6 (phase, nextPhaseMatch, closestPhaseMatch, phase-encoded beats).
- [ ] Constants table and open questions for pcap verification.
