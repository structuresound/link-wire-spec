# Chapter 1 — Link Peer Discovery Protocol (STUB)

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

This chapter will specify how Link peers find each other and gossip peer state on a
local network: the multicast announcement protocol on `224.76.78.75:20808` (IPv4) and
`ff12::8080` port 20808 (IPv6), framed with the `_asdp_v` + `0x01` magic, with message
types Alive=1, Response=2, ByeBye=3; the peer-state payload (session membership,
timeline, start/stop state, measurement endpoint, and the audio endpoint extension
referenced by Chapter 3 §2); and the ttl-based peer timeout model.

## TODO

- [ ] Discovery message framing: magic, header fields (type, ttl, groupId, NodeId), 512-byte size limit.
- [ ] Message types and triggers: Alive (periodic + on state change), Response (unicast reply to a newly seen peer), ByeBye (shutdown).
- [ ] Announcement cadence: ttl value, ttl-ratio derived period, minimum spacing.
- [ ] Peer-state payload entries: `sess`, `tmln`, `stst` (start/stop), `mep4`/`mep6`, `aep4`/`aep6`; exact value layouts and the family-switch optional rule.
- [ ] Peer table maintenance: ttl expiry, bye handling, gateway (per-interface) tracking, session membership changes.
- [ ] IPv6 specifics: link-local multicast scope, scope-id handling on responses.
- [ ] Self-message and group filtering rules.
- [ ] Interaction with sync (Chapter 2) session formation and with LinkAudio endpoint learning (Chapter 3).
- [ ] Constants table and open questions for pcap verification.
