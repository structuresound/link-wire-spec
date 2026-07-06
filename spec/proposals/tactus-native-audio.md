# Proposal — Tactus Native Audio

| | |
|---|---|
| Status | Rationale record — wire encodings now pinned normatively in `spec/04-native-audio.md` (0.5.0); where the two disagree, Chapter 4 wins |
| Targets | link-wire-spec ≥ 0.4.1; LinkAudio v1 (ch. 03) as a compatibility floor |
| License | CC-BY-4.0 |
| Provenance | Dirty-side design note. Documents a protocol a clean-room implementation (`tactus`) MAY build; contains no reference-source expression. |

**This is not a LinkAudio-parity effort.** Tactus Native is its *own* audio
protocol and mesh, designed for what a modern clean-room implementation can do
between its own peers — higher throughput, real codec choice, forward error
correction, multicast fan-out, negotiable latency, an optional media clock, and a
routed multi-transport mesh. Compatibility with Ableton Link / LinkAudio v1 is a
**graceful-degradation floor** for mixed sessions, *not* the design target: when a
tactus peer meets a non-tactus peer it falls back to conformant v1, but the
protocol is architected around the native case and diverges from LinkAudio
wherever divergence is better. Where this note says "v1", it means that fallback
floor, not a goal to match.

This is a **design study**, not a normative chapter. The native wire, the
capability handshake, the mesh control plane, and the transport tiers are laid out
here; the boundary of what stays safe against a *v1* peer is set by two empirical
facts about the reference established in this repository (ch. 03 §5.8, §5.9). A
follow-up normative chapter (`04-native-audio`) would pin the bytes.

The mesh **control plane** and route/optimization logic are an application-layer
concern that lives *above* tactus, in the GPL orchestration layer
([ipauro](https://github.com/partial-signals/ipauro), crate `ipauro-mesh`), not in
the MIT clean-room wire crate. This note specifies only the *wire-relevant* parts
of the mesh — how capabilities and topology are represented and gossiped, and how
a mesh overlay slots into Link's gateway model (§8). The algorithms themselves are
ipauro's.

---

## 1. Design principles

1. **Native-first; v1 is the fallback floor.** A tactus peer *can* speak
   conformant LinkAudio v1 (ch. 03) to a non-tactus peer, but native mode is the
   design center. Fallback is a compatibility mode, not a subset the native
   protocol is confined to.
2. **Capabilities are advertised, features are negotiated per pair.** Two tactus
   peers discover each other's capabilities and run native mode *between them*. A
   third (reference) peer subscribing to the same sink still receives plain v1.
3. **The wire proves the fallback is safe.** Every behavior that a v1 peer might
   observe either rides an entry/field the reference already ignores, or is gated
   behind a capability the reference cannot assert. Both are established
   empirically below, not assumed. (This bounds the *fallback*; native-to-native
   traffic is unconstrained by v1.)

### 1.1 Empirical basis (this repository)

Probed against the pinned reference (`Ableton/link` @ `902aef9`, Link 4.0),
minimal from-spec peer vs `LinkAudioHut`, isolated netns:

- **Unknown payload entries are ignored.** A `PeerAnnouncement` carrying an extra,
  unknown payload-container entry (fourcc `tcap`) alongside the v1 entries is
  processed normally — the reference lists the channel and answers the ping. This
  is ch. 00 §4.5 rule 2 (skip unknown keys by size) exercised on the audio control
  plane. **Capability advertisement is therefore invisible and safe to v1 peers.**
- **Unknown message types are ignored.** Type-7 and garbage datagrams to the
  reference audio endpoint leave it fully operational (ch. 03 §9). **A native data
  plane can use its own message type without disturbing v1 peers.**
- **The 512-frame-per-chunk receive limit** (ch. 03 §5.9): the reference *renderer*
  overruns a fixed 512-sample buffer on any chunk above 512 frames. This is the
  hard edge of backward-compatible throughput — see §3.

## 2. Feature grid

Following the Inferno README's comparison style (Inferno vs DVS vs AES67), placed
against the audio-over-IP field. "LinkAudio v1" is the reference; "Tactus native"
is what this proposal adds when both ends are tactus.

| Feature | LinkAudio v1 | **Tactus native** | AES67 | Dante (DVS) | AVB (1722) |
|---|---|---|---|---|---|
| Discovery | Link multicast gossip | Link gossip + `tcap` | SAP/SDP, mDNS | proprietary mDNS | SRP / 1722.1 (AVDECC) |
| Transport | unicast UDP | unicast + opt. multicast | RTP multicast | unicast+multicast UDP | L2 AVTP (802.1Q) |
| Clock | Link ghost-time (musical) | ghost-time **or** ext. PTP/gPTP | PTPv2 (1588) | PTPv1/v2 | gPTP (802.1AS) |
| Sync accuracy | sub-ms, beat-phase | sub-ms → sub-µs (w/ PTP) | sub-µs | sub-µs | sub-µs |
| Sample lock | no (rate-nominal) | opt. (PTP domain) | yes | yes | yes |
| Codecs | PCM i16 only | i16/i24/f32, FLAC, Opus | L16/L24 | L16/L24/L32 | L16/L24, AAF |
| Bit depth | 16 | 16/24/32 | 16/24 | 16/24/32 | 16/24/32 |
| Max datagram use | 502 B samples (of 1200) | full 1200 B, negotiated jumbo | MTU (≤1440 typ.) | MTU | L2 MTU |
| One-to-many | N unicast copies | multicast group | multicast | multicast | multicast (MSRP) |
| Loss handling | open-loop, detect-only | seq-FEC / redundancy | none (rely on net) | none (rely on net) | reservation (no loss) |
| Bounded latency | no | only on reserved transport | no (unless PTP+QoS) | no (unless QoS) | **yes** (Qav+SRP) |
| Latency control | none (buffer-driven) | negotiated rx/tx target | receiver offset | 1–40 ms configurable | 2 ms class A |
| Backward compat | — | **v1 to any non-tactus peer** | — | — | — |
| Infra required | none (any IP) | none (native = any IP) | PTP-aware net helps | Dante net | AVB switches |
| License | GPLv2+ / proprietary | MIT (tactus) | varies | proprietary | standard |

Reading of the grid: **v1's weak columns are exactly the ones a native mode can
lift without new infrastructure** — datagram efficiency, one-to-many, codecs, loss
robustness, and latency control are all software-only and need no special network.
The columns that *do* need infrastructure — sample lock and bounded latency — are
the AES67/Dante/AVB territory, reachable by tactus only when the transport
underneath provides PTP/gPTP and (for bounded latency) reservation. §5–§6 handle
those.

## 3. Backward-compatible wins available with **zero** negotiation

Two improvements are legal to send *to a reference peer today*, because they stay
inside v1's documented and probed receive envelope:

1. **Fill the datagram.** The reference sender uses only 502 of 1200 bytes (ch. 03
   §5.6). A tactus sender may pack up to the 1200-byte limit as long as **every
   chunk stays ≤ 512 frames** (ch. 03 §5.9) — e.g. four 251-frame chunks, or two
   275-frame chunks (probed: a 1200-byte, 2×275 datagram is received cleanly).
   This cuts datagrams-per-second ≈ 2.3× for the same audio, reducing per-packet
   CPU and header overhead on both ends, with a reference receiver none the wiser.
2. **Coalesce across the flush boundary.** v1 already carries multiple chunks per
   datagram (ch. 03 §5.3); a tactus sender can batch more aggressively under the
   ≤512-frame rule to trade a little latency for far fewer packets.

Neither needs `tcap`. They are simply the efficient corner of v1 that the reference
sender leaves unused. **Constraint (normative, ch. 03 §5.9):** never exceed 512
frames per chunk toward a peer not known to be tactus.

## 4. Capability negotiation

### 4.1 The `tcap` entry

A tactus peer adds one payload-container entry to the `PeerAnnouncement` it already
sends (ch. 03 §4.1). Reference peers skip it (§1.1); tactus peers read it.

| Key | `u32` | Value |
|---|---|---|
| `tcap` | `0x74636170` (`tcap`) | version `u16`, then a capability bitmap / TLV block (§4.2) |

Placing capabilities on the **announcement** (not discovery) keeps them on the
audio control plane, scoped to audio peers, and refreshed at the same 250 ms
cadence. A tactus peer that sees `tcap` from the announcer marks that peer's
channels as *native-capable*.

### 4.2 Capability block (TLV)

A minimal, forward-compatible TLV list. Each entry: `u16 type, u16 len, value`.

| Type | Capability | Value |
|---|---|---|
| 1 | codecs supported | bitmap: i16, i24, f32, FLAC, Opus |
| 2 | max chunk frames | `u16` (peer's own render-buffer ceiling; ≥ 512) |
| 3 | multicast group | `aep`-style endpoint the peer will accept native multicast on |
| 4 | FEC schemes | bitmap: none, XOR-parity, RaptorQ |
| 5 | clock domains | list of PTP/gPTP domain numbers the peer is disciplined to (empty = ghost-time only) |
| 6 | latency target | negotiable rx/tx target, ns |

### 4.3 Per-channel upgrade

1. Sink and source both advertise `tcap`. Each learns the other is tactus.
2. The **source** requests native mode for a channel by adding its own `tcap`
   (and a chosen codec/FEC/clock intersection) to the `ChannelRequest` payload
   (again an entry a reference sink would ignore — but a reference sink is never
   in this path, because native mode is only entered when *both* peers saw
   `tcap`).
3. The sink, if the intersection is non-empty, streams that channel to that
   requester in **native data-plane** datagrams (§5); to any *other* (reference)
   requester of the same channel it continues plain v1. Per-requester send state
   already exists in v1 (ch. 03 §7.2), so this is a per-requester format choice,
   not a new fan-out model.
4. If the intersection is empty, or either side drops `tcap`, the channel falls
   back to v1 with no interruption.

**Session identity, discovery, sync, start/stop, and beat alignment stay pure
Link** throughout — native mode changes only how audio *samples* move between two
consenting peers.

## 5. Native data plane

The native data plane uses a **distinct message type** (proposed 16, well clear of
v1's 1–6; probed safe as "unknown type" to reference) with its own payload,
carrying beat-stamped chunks exactly as v1 does (so ch. 03 §6 beat-time alignment
is unchanged) plus:

- **Codec field with real negotiation.** Unlike v1 (where an unknown codec is
  silently mis-decoded, ch. 03 §5.4), the native codec is chosen from the §4.2
  intersection, so both ends agree before a byte is sent. Enables i24/f32 for
  headroom and FLAC/Opus for bandwidth.
- **Larger chunks.** Once `tcap` type 2 confirms the peer's render ceiling, chunks
  may exceed 512 frames up to that ceiling — fewer, larger datagrams for
  latency-tolerant flows (recording, monitor sends).
- **Forward error correction.** Because the data plane is open-loop with no
  retransmit (ch. 03 §5.8), native mode adds optional FEC: XOR parity across a
  sequence window for light protection, or RaptorQ for heavier loss. This targets
  the "robustness" column directly — the single biggest weakness the §5.8
  throughput study exposed — without inventing a feedback channel.
- **Optional multicast.** When several tactus sources subscribe to one sink, the
  sink may publish to a negotiated multicast group (`tcap` type 3) instead of N
  unicast copies (ch. 03 §5.7), collapsing one-to-many bandwidth the way
  AES67/Dante do. Reference requesters still get their unicast copy.

All of these are inert to a reference peer: it never negotiates them, never
receives the type-16 datagrams, and continues to see a conformant v1 sink.

## 6. Clock: the pro-audio gap and how to bridge it

This is where "better than LinkAudio" meets a real limit, and it is worth stating
plainly.

- **Link ghost-time is musical sync, not media-clock sync.** Ch. 02's median-filtered
  ghost transform aligns *beats* to within sub-millisecond and fixes slope at 1
  (no rate discipline). That is excellent for musical phase but is **not** a
  sample-locked media clock: two peers agree on where beat 3 is, not on a common
  audio sample edge. AES67, Dante, and AVB all require IEEE-1588 PTP (or 802.1AS
  gPTP) with, ideally, hardware timestamping, reaching sub-microsecond and true
  sample lock.
- **Native mode can carry a clock-domain reference.** `tcap` type 5 lets a tactus
  peer declare it is disciplined to a PTP/gPTP domain. When two tactus peers share
  a domain, native chunks can be stamped in that domain's timescale in addition to
  beat-time, giving sample-accurate alignment — the bridge to AES67/Dante/AVB-grade
  audio. When no PTP grandmaster exists, they fall back to ghost-time (musical)
  alignment, i.e. exactly today's LinkAudio behavior. This mirrors Inferno's
  dependence on an external PTP stack (Statime) rather than reinventing 1588.
- **Recommendation.** tactus should *consume* a media clock rather than implement a
  grandmaster: keep Link for discovery + musical time, and layer sample-accuracy
  from whatever the transport supplies — an external PTP/gPTP domain on a switched
  fabric, or **transport-native clock recovery on a point-to-point link, where PTP
  is the wrong tool (see §7.2)**. The `tcap` type-5 record carries whichever
  applies.

## 7. Transport tiers (including ad-hoc AVB and USB p2p)

Native audio quality is bounded by the transport beneath it. Four tiers, weakest
guarantee first:

| Tier | Sync source | Loss/latency guarantee | tactus role |
|---|---|---|---|
| T0 best-effort IP (Wi-Fi/LAN) | Link ghost-time | none (open-loop + optional FEC) | today's LinkAudio, packed + FEC |
| T1 PTP-aware LAN | ext. PTPv2 | sub-µs sync, no bandwidth guarantee | sample-lock, AES67-adjacent |
| T2 AVB switched fabric | gPTP (802.1AS) | bounded latency via Qav+SRP | needs AVB NICs+switches; tactus as AVTP talker/listener |
| T3 **ad-hoc AVB over p2p link** | gPTP over the link | bounded by dedication, not reservation | the interesting case ↓ |

### 7.1 Ad-hoc AVB over a point-to-point link

Full AVB needs AVB-capable **switches**: 802.1Qav credit-based shaping and SRP
(802.1Qat) stream reservation exist to protect reserved streams from *other*
traffic on a *shared* fabric. On a **dedicated point-to-point link with a single
talker**, that contention does not exist — so the two hardest infrastructure
dependencies fall away:

- **gPTP (802.1AS)** runs fine peer-to-peer; it is a link-local protocol and a
  two-node link is its simplest case. Sub-µs sync is achievable if both NICs
  timestamp.
- **AVTP (1722)** media transport needs no switch — it is just L2 framing the two
  ends agree on.
- **Qav/SRP become unnecessary**, not merely absent: with one talker on a dedicated
  link there is nothing to shape against and nothing to reserve bandwidth away from.
  The "guarantee" is provided by *link dedication* instead of by admission control.

So **"ad-hoc AVB" over a direct link is feasible** and is a legitimate T2-class
transport for a two-peer tactus session, provided both ends have gPTP-capable
(hardware-timestamping) interfaces. tactus would run gPTP for the media clock
(feeding §6 type-5), carry native chunks in AVTP frames, and skip the reservation
machinery. Where the link is *not* dedicated (a shared switch without AVB support),
this degrades to T1 (PTP sync, best-effort delivery) — still better than T0.

### 7.2 Point-to-point over USB / Thunderbolt, and why PTP is the wrong default there

The question: can an Apple USB / Thunderbolt peer-to-peer link stand in for an AVB
fabric, given that it is inherently point-to-point?

Naming caveat: on macOS the `anpi*` interfaces are Apple's *internal* co-processor
management links, not a user data path; the user-facing p2p transports are
USB/NCM, the Thunderbolt/USB-C IP bridge, and AWDL. The "480" is USB 2.0's
480 Mbit/s signalling rate. The substance is the same for any of them.

**The dedication half: yes, for free.** A p2p link is a single-talker dedicated
pipe, so — as in §7.1 — there is nothing to reserve or shape against. 480 Mbit/s
carries many channels of L24/48 kHz (≈ 1.15 Mbit/s each), so bandwidth is not the
constraint. Point-to-point removes AVB's reservation requirement outright.

**The sync half — and the correction to the naive plan.** The reflex is "run
software PTP over the link." That is both *harder than it looks* and *the wrong
tool for a p2p link*:

- **Why software PTP under-delivers here.** Hardware timestamping (what gPTP/1588
  use to hit sub-µs) latches the clock *in the MAC, triggered by the PHY* the
  instant a frame crosses the wire — before any OS, driver, or interrupt latency.
  Software timestamping reads the clock up in the stack and inherits IRQ,
  scheduler, and — on USB — 125 µs microframe polling jitter. What matters for a
  *guarantee* is the bounded worst case, and software timestamping's worst case is
  loose and load-dependent, which is exactly what AVB exists to eliminate. You
  cannot get PHY timestamps on these interfaces without hardware/driver support
  Apple does not expose: no unsigned kexts without disabling SIP + Reduced
  Security, DriverKit mediates hardware access, and there is no public PHC /
  `SO_TIMESTAMPING`-equivalent for the USB/TB-net interfaces. So emulating gPTP in
  software is fragile, unshippable, and still worse-bounded than a real NIC.
- **Why you don't need it on a p2p link.** PTP exists to discipline *independent*
  clocks across a *switched* network with no shared timing reference. A dedicated
  link with a single talker has neither problem. Two better options are already
  available:
  - **Transport-native clocking.** USB already solves point-to-point audio
    clocking without PTP — that is USB Audio Class *async mode*: the bus
    start-of-frame (1 ms / 125 µs microframe) is a shared reference both ends see,
    and a *feedback endpoint* reports the device's exact sample rate so the other
    end matches it. Glitch-free multichannel audio, zero PTP, because the bus is
    the clock domain. A tactus p2p transport can lean on the same idea rather than
    reinvent 1588.
  - **Master by construction.** With one talker, make it *the* clock master and
    have the receiver recover its rate from the stream (feedback, or ASRC from
    packet-arrival + explicit rate). A far smaller, better-bounded problem than
    distributed PTP.
- **Thunderbolt ≫ USB 2.0 here.** Thunderbolt networking is PCIe-tunneled and
  DMA-driven, not 125 µs-polled — much lower latency and jitter, closer to
  real-NIC behavior. For the best p2p sync on a modern (port-less) Mac, target
  Thunderbolt; USB 2.0 is the cheap-and-available fallback.

**Placement and recommendation.** A dedicated USB/TB link sits **between T0 and T2**:
better-bounded than contended Wi-Fi (dedicated, low-jitter, ample bandwidth), short
of switched AVB (no hardware time). But tactus should reach that placement by
**transport-native clocking (UAC-style feedback / SOF, master-by-construction),
not by emulating gPTP** — feeding §6's media-clock reference from the recovered
rate, using Link ghost-time for musical alignment, and negotiating a latency
target (`tcap` type 6) to the measured jitter. PTP re-enters the picture only when
you leave the p2p link for a switched fabric (T1/T2), where no shared bus clock
exists. If genuine PHY hardware timestamping is required on a port-less Mac, the
realistic path is a **PTP-capable USB3/Thunderbolt Ethernet adapter** whose
chipset exposes a hardware clock — i.e. add a real NIC — not the built-in p2p
interface.

## 8. Control plane and mesh (tactus-native)

Tactus-native is not confined to Link's multicast/L2 discovery. A **mesh overlay**
carries tactus sessions across subnets and over the p2p cables that multicast
cannot traverse, and picks the best of several transports to each peer. The
*algorithms* (routing, optimization, service-order policy, transcoding
orchestration) live above tactus in `ipauro-mesh` (GPL); this section specifies
only the wire-relevant shape so independent implementations interoperate.

### 8.1 The overlay is another gateway

Link already tracks peers **per gateway** (per interface) and selects the best
path per (peer, gateway) using the ch. 03 §4.2 quality metric. A mesh overlay
connection (e.g. [iroh](https://github.com/n0-computer/iroh): authenticated,
encrypted, NAT-traversing QUIC keyed by a node public key) is simply **another
gateway — a virtual one** — reaching where multicast cannot. This slots into the
existing model with no new peer abstraction: a tactus node speaks Link on each
local segment and the overlay to the wider mesh, and the same per-gateway
best-path logic ranks a Thunderbolt path, a LAN path, and a relay path against
each other. The overlay's own path management (relay-bootstrap → direct-path
upgrade) *discovers* the Thunderbolt/USB-C IP path as a candidate; **service order**
(§8.3) then combines the measured quality with explicit policy.

### 8.2 Control plane vs media plane — keep them apart

The single most important rule: **the reliable overlay carries control, never live
audio.**

- **Control plane over the QUIC overlay** — membership, topology, capability
  (`tcap`) exchange, subscription setup, routing, policy. Wants reliability, auth,
  encryption, cross-subnet reach.
- **Media plane stays unreliable/timely** — v1 or native datagrams (§5). A
  retransmitted late sample is useless; never run PCM through QUIC reliability.
  QUIC *unreliable* datagrams (RFC 9221) are an option that keeps the media plane
  timely while adding congestion-awareness — which directly counters the ch. 03
  §5.8 failure mode where the open-loop stream saturates a link and starves its
  own control traffic — **provided** the sender degrades gracefully (drop a
  channel / drop quality) instead of merely shedding packets. Use overlay
  datagrams on shared links (congestion-awareness is a feature), and raw UDP on
  dedicated links and on embedded peers where per-packet crypto cost matters.

### 8.3 Coordination: gossip and a shared objective, not consensus

The mesh needs agreement, but **not** ACID/CAP-grade consensus. The model:

- **Gossip for membership, topology, capabilities, liveness.** This *is* what Link
  discovery already is; extend it (SWIM-style over the overlay) to carry each
  peer's transports, link qualities, and `tcap`. Eventually consistent,
  partition-tolerant, leaderless.
- **Leaders by deterministic tie-break, not Raft.** The few genuinely single-owner
  roles — media-clock master (§6/§7), multicast-group owner, sink owner — are
  resolved by gossip + a deterministic tie-break, reusing Link's own session
  election (greatest ghost-time, lowest session-id wins; ch. 02 §7.2). No
  consensus protocol is introduced.
- **Flow optimization by shared objective, converging on inputs not outputs.**
  Nodes agree on the *weights/objective* (a gossiped policy), then either (a)
  **deterministically recompute** the global assignment from the converged
  topology + demand set — same inputs and the same deterministic function yield
  the same result everywhere (link-state / OSPF-style), so no output consensus is
  needed; or (b) run **distributed utility-maximization / back-pressure**, which
  converges to the shared optimum under local updates for larger, churnier meshes.
  Consistency follows from gossip convergence of the inputs; transient
  disagreement is a brief suboptimal route, acceptable for audio. The hazard is
  *oscillation*, damped by **hysteresis** — and Link already supplies the
  primitive: replace a path only with a *strictly* better one (ch. 03 §4.2). The
  only strongly-ordered datum is a monotonic **policy epoch** (which objective is
  in force), gossiped with highest-epoch / lowest-id wins — still not Raft.

### 8.4 Service order = measured quality + policy, feasibility-first

"Service order" (which transport to prefer when several reach a peer) layers
explicit policy on the §4.2 measurement: e.g. prefer Thunderbolt even at slightly
higher measured RTT because it is higher-bandwidth and more stable, or cap on
cost. When routing must also satisfy a *function* — the far peer needs a specific
codec, or the flow must pass a fan-in/transcode hub (the "make it just work"
goal) — preference and function can appear to conflict. They compose if applied in
order: **constraints filter** (keep only paths that reach the right endpoints with
the required conversion and bandwidth), then **preferences rank** the feasible
set. Preference never overrides feasibility, so "prefer Thunderbolt" means "prefer
it among paths that actually work." This is constraint-based routing; the
algorithm is ipauro's, the inputs (topology, `tcap`, link quality) are what the
wire carries.

### 8.5 Honest limits

- **Clock across a transcoding hub.** A route that resamples at a hub makes the hub
  a clock boundary (ASRC each side). Fine for musical sync; end-to-end
  sample-accuracy across a converting hop is not a promise to make.
- **Overlay setup latency.** QUIC handshake + relay bootstrap precede the
  direct-path upgrade; the media plane should hold until the *direct* path is up
  and not fall back to a relay for live audio.
- **Re-route is not seamless.** Eventual consistency means a path change is a brief
  discontinuity; budget a crossfade/reclock rather than pretending otherwise.

## 9. Backward-compatibility & provenance summary

- Native-to-native traffic is unconstrained by v1. The *fallback* is what stays
  safe against a reference peer: §3 wins are legal v1, §4–§8 native behaviors are
  entered only between two peers that both advertised `tcap`, and everything
  collapses to conformant v1 on any mismatch. No reference peer ever sees a native
  datagram or an unparseable message.
- This proposal is a **dirty-side design note**. It cites only observable reference
  behavior (the §1.1 probes and ch. 03 §5.8/§5.9 findings) and public protocol
  facts; it contains no reference-source expression. A clean-room `tactus` (MIT)
  implementation may build the wire from it under the usual firewall
  (PROVENANCE.md). The mesh control plane (`ipauro-mesh`) is GPL application code
  that *consumes* tactus's public API and lives in a separate repository; it is not
  part of the clean-room crate and does not affect its provenance.

## 10. Open questions

Questions 1, 2, 3, 5, and 6 are **closed by Chapter 4** (spec 0.5.0); the
entries below record what was open and where each answer landed. Question 4
remains open (tracked in ch. 04 §12).

1. **Closed (ch. 04 §2).** `tcap` = `0x74636170` assigned final; TLV types 1–8
   pinned with a registry and allocation policy (9–`0x7FFF` spec-assigned,
   `0x8000`–`0xFFFF` private).
2. **Closed (ch. 04 §4–§6).** Native media = message type 16, repair = 17;
   payload grammar, per-chunk coded lengths, FEC framing (XOR window + RaptorQ
   profile), and multicast join/filter semantics pinned.
3. **Closed (ch. 04 §4.3, §8).** A clocked flag adds a 10-byte clock-domain
   record to the datagram header and a `u64` nanosecond domain timestamp per
   chunk, alongside beat time (which remains mandatory).
4. **Open.** p2p sync precision (§7.2) is asserted from transport structure, not
   measured. A capture on real Apple USB/Thunderbolt p2p hardware would move the
   T1/T2 placement from reasoned to observed — the same [B]→[W] gap the spec
   tracks elsewhere.
5. **Closed (ch. 04 §7.2).** Default and minimum chunk ceiling = 512 frames
   (the ch. 03 §5.9 constant); TLV 2 raises it per peer.
6. **Closed (ch. 04 §9).** Four signed, origin-sequenced gossip records
   (Peer/Link/Demand/Policy) pinned; the spec fixes identity, envelope, bodies,
   and adoption/ordering rules, and the routing algorithms stay in
   `ipauro-mesh`.
