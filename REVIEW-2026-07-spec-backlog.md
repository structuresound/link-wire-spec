# Spec backlog — 2026-07 architecture review

Companion to the implementation review in
[`link-wire-rs/docs/REVIEW-2026-07-parity-audio-mesh.md`](../link-wire-rs/docs/REVIEW-2026-07-parity-audio-mesh.md).
This doc collects the **spec-side** actionables (Lane D there) with enough detail
to delegate. IDs match the implementation review's `D*` labels.

The normative core (ch. 00–03) is essentially **closed** — "no OPEN QUESTION
remains in any chapter" (`CHANGELOG.md`). Everything below is either process
hygiene, one outstanding evidence upgrade, or the groundwork the tactus-native
chapters need before they can be normative.

---

## D1 — Tag releases · S · 🟢

**Problem.** No git tags exist (`git tag` is empty) despite the CHANGELOG
documenting v0.1.0–0.4.3, and the example candidate CI pins
`SPEC_REF: v0.1.0` (`conformance/example-candidate-ci.yml:23`) while README +
PROVENANCE instruct clean-side consumers to fetch "at a release tag." A
downstream candidate copying the example CI fails to clone a nonexistent tag.

**Do.** Tag the existing CHANGELOG versions (at minimum the current 0.4.3 and a
`v0.1.0` the example references), and adopt a tag-on-release step. This also lets
`link-wire-rs` pin the spec by tag instead of the branch SHA both its workflows
currently carry a "move to a release tag" note about.

---

## D2 — Gateway-trait design note (endpoint representation) · S · 🔴 decision

**Problem.** The implementation's overlay-gateway work (impl ticket A6) needs the
spec to be explicit about how a non-multicast, non-`SocketAddr` overlay peer
relates to the ch. 01 gateway model. The wire type stays `SocketAddr` for v1
compat; the question is the *runtime* endpoint representation.

**Do.** A short note (in ch. 01 or a design appendix) confirming that "gateway"
is a transport-neutral concept — one virtual gateway per overlay — and stating
the endpoint-repr recommendation (synthetic `SocketAddr` mapping for v1 vs an
abstracted endpoint type). *Recommendation: synthetic `SocketAddr`; revisit if it
leaks into the wire.* This is the spec-side twin of impl decision D2.

---

## D3 — `tcap` fourcc + TLV registry · M · 🟢 (with a numbering decision)

**Problem.** The proposal's `tcap` capability entry and TLV type numbers (1–6:
codecs / max-chunk-frames / multicast-group / FEC-schemes / clock-domains /
latency-target) are **placeholders** (`spec/proposals/tactus-native-audio.md`
§4.1-4.2, §10.1). Two implementations cannot interoperate until they are assigned.

**Do.** Assign the real `tcap` fourcc (currently placeholder `0x74636170`) and
fix the TLV type numbers, and add a small **registry section** governing future
type allocation (so native capabilities can grow without collisions). Unblocks
impl ticket B3. Because `tcap` rides an entry a reference peer skips
(ch. 00 §4.5 rule 2), this is additive and v1-safe.

---

## D4 — Normative `04-native-audio` chapter · L · 🔴 (the big one)

**Problem.** The native data plane is sketched (proposal §5) but not normative.
Impl tickets B4/B6/B8 are blocked on a pinned grammar.

**Do — pin, in a new `spec/04-native-audio.md`:**
1. Native data-plane **message type** (proposed 16) + payload grammar, preserving
   ch. 03 §6 beat-time alignment.
2. **Codec** field + negotiation encoding (i16/i24/f32/FLAC/Opus bitmap +
   intersection/selection handshake) — fixes v1's silent mis-decode (§5.4).
3. **FEC framing** (XOR-parity window; RaptorQ), including the sequence-window
   definition over chunk sequence numbers.
4. **Multicast** join/group semantics (`tcap` type 3), with reference-requester
   unicast coexistence.
5. **Clock-domain stamping** (`tcap` type 5): how a media-clock timestamp rides
   *alongside* beat-time in a native chunk.
6. **Per-channel upgrade handshake** state machine: how a source signals native
   in `ChannelRequest`, how the sink picks native-vs-v1 per requester, and the
   exact fallback triggers (empty intersection / either side drops `tcap`) with
   the "no interruption" guarantee.
7. **Default max-chunk-frames** + absent-`tcap`-type-2 fallback, reconciled with
   the ch. 03 §5.9 512-frame v1-interop constraint.
8. **Latency-target** negotiation (`tcap` type 6): units (ns) + reconciliation of
   two peers' targets.

See proposal §10 (open questions 1–5) — this chapter closes them.

---

## D5 — Capture `discovery-ipv6.pcap` · M · 🟢

**Problem.** The **only** outstanding `[B]→[W]` evidence upgrade in the normative
chapters. IPv6 endpoints and the 119-byte v6 peer-state size are derived/
behavioral only (`spec/01-discovery.md:76-77,:221`; `03-audio.md:670-675`
question 8; `vectors/README.md:106-116`) because no IPv6-capable capture
environment has existed.

**Do.** Capture the discovery exchange over IPv6, add the vector + manifest, and
promote the v6 rules from `[B]` to `[W]`. Pairs with impl ticket A2 (the v6
socket path), which can double as the capture peer once it exists.

---

## D6 — Topology / `tcap` gossip encoding boundary · L · 🔴 decision

**Problem.** The one open question the CHANGELOG explicitly **re-opened**
(`CHANGELOG.md` ~L449; proposal §10.6). The mesh needs a wire form for capability
+ link-quality + demand + policy records, and the spec must draw the precise line
between what it fixes (encoding, for interop) and what `ipauro` owns (the routing
algorithm).

**Do.** Pin the encoding of four signed, origin-sequenced gossip records — leave
the algorithm to `ipauro`:
- **`PeerRecord`** — identities (incl. the Link-NodeId ↔ mesh-Ed25519 signed
  binding, impl C3), transports, `tcap`.
- **`LinkRecord`** — a→b RTT / jitter / loss / bandwidth estimates.
- **`DemandRecord`** — flow needs: codec, latency target, priority.
- **`PolicyRecord`** — epoch, trust mode, roster hash, objective weights.

State that consistency follows from gossip convergence of *inputs* (nodes
deterministically recompute routes, link-state style), damped by the ch. 03 §4.2
"strictly-better path" rule, with a monotonic **policy epoch** as the only
strongly-ordered datum (proposal §8.3). Unblocks impl C3/C6.

---

## D7 — Security Considerations chapter + evidence-model rebase · M · 🔴

Two related structural findings the native roadmap forces.

### D7a — Security Considerations chapter

**Problem.** There is no threat model or Security Considerations section. The
protocol is "trusted local segment" **by design** (correct for jam) — but that
assumption is nowhere stated, and the LAN attack surface is undocumented. NodeId/
SessionId are 8 random bytes with no host binding (`00-overview.md:187`); there is
zero crypto in the wire path.

**Do.** Add a chapter that (a) states the trust assumption explicitly and (b)
enumerates the inherent unauthenticated-LAN-gossip surfaces, defensively:
- **Forged announcements** redirect a victim's measurement/audio endpoints
  (endpoint learning trusts advertised `mep*`/`aep*` entries).
- **Ghost-time election hijack** — the stateless responder answers any ping with
  its own ghost time (ch. 02 §4.3), so a crafted-large ghost time wins the join
  election (§7.2) and pulls the session timeline/tempo; beat-origin
  "strictly-greater-wins" (§6) lets a high beatOrigin monopolize updates.
- **Channel-request amplification** — one spoofed request → a sustained
  ~768 kbit/s/channel unicast stream until ttl; N spoofed requesters → egress DoS,
  compounded by the open-loop §5.8 self-starvation.
- **ByeBye griefing** and **measurement reflection/cross-abort** — both
  unauthenticated; the spec already suggests correlating pongs by source endpoint
  as a partial mitigation.

Frame it as: identity/authentication enter **only** at the mesh overlay
(authenticated QUIC), **above** the wire crate — never in the v1/native datagram
path. The tiered trust model (jam/adhoc/stage) is the consumer of this posture.

### D7b — Rebase the evidence model for native content

**Problem.** The `[W]`/`[B]`/`[N]` evidence tags **and** the conformance harness
are **reference-anchored**: `[B]` means "dirty-side analysis of the Ableton
reference," `[W]` means "capture of the reference," and the harness runs
reference-vs-candidate. A normative `04-native-audio` chapter documents a protocol
with **no upstream reference at all** — so upstream-watch (`upstream-watch.yml`,
globbed to `include/ableton/`), the link-wire-rs canary, and the `[B]` class
provide **zero** drift detection for native content, and the harness can only test
the v1 *fallback* against the reference.

**Do.** Before native chapters go normative, rebase the evidence model:
- Redefine `[W]` for native content as tactus's **own** golden captures (candidate-
  vs-candidate); the harness self-test mode already runs two peers, so the
  structure exists — the oracle just moves from "the reference" to "the spec."
- Add a **design-rationale** evidence class (native decisions have no reference to
  be `[B]` against).
- Add a PROVENANCE carve-out distinguishing "reverse-engineered from Link (dirty)"
  from "originally designed for tactus (clean)" — the firewall is moot for native
  content, which is clean by construction.

---

## Conformance coverage gaps (informative — feed future vectors)

Not blockers, but the golden-vector corpus (5 sets) leaves these `[B]`-only, and
they are the primitives the mesh + native work lean on:

- **Session merge/election between distinct sessions** — the join-rule tie-break /
  ε threshold / ghost-time comparison is never wire-pinned, yet the mesh reuses it
  for role election (proposal §8.3).
- **Path-quality metric / multi-gateway best-path selection** — the multi-gw
  vector carries no audio, so §4.2 selection is never observed (impl A4 fixes the
  behavior; a vector would pin it).
- **Loss / reorder / retry-budget exhaustion** (ch. 02 §5.1) and **throughput
  self-starvation** (§5.8) / **512-frame overrun** (§5.9) — all measured `[B]` via
  the `SHAPE` shaper, no golden vector (the reference never reaches these edges).
- **Subscription expiry / multiple concurrent requesters / per-requester
  teardown**; **split announcements/byes**; **oversized/duplicate-key payloads**.

Prioritize a session-election vector and a path-selection vector — those two back
mesh behavior the current suite can't see.
