# Proposal — Tactus Native Audio over LinkAudio

| | |
|---|---|
| Status | Draft / design study |
| Targets | link-wire-spec ≥ 0.4.1, LinkAudio v1 (ch. 03) |
| License | CC-BY-4.0 |
| Provenance | Dirty-side design note. Documents an extension a clean-room implementation (`tactus`) MAY build; contains no reference-source expression. |

This is a **feasibility and design study**, not a normative chapter. It asks:
can a clean-room implementation (`tactus`) carry a richer audio protocol between
its own peers — higher throughput, better robustness, better efficiency, and a
path toward sample-accurate pro-audio interop — while remaining **wire-compatible
with Ableton Link** for every peer that is not a tactus peer?

The short answer is **yes, for a well-defined envelope**, and the boundary of that
envelope is set by two empirical facts about the reference established in this
repository (ch. 03 §5.8, §5.9). This note lays out the negotiation mechanism, a
feature grid, the wire extensions, the clock question, and the transport tiers —
including the ad-hoc AVB and USB-p2p ideas.

---

## 1. Design principles

1. **v1 is the floor, never regressed.** A tactus peer is a fully conformant
   LinkAudio v1 peer (ch. 03). Every tactus-specific behavior is *additive* and
   *negotiated*; with any non-tactus peer, only v1 is on the wire.
2. **Capabilities are advertised, features are negotiated per pair.** Two tactus
   peers discover each other's capabilities and upgrade the channels *between
   them* to native mode. A third (reference) peer subscribing to the same sink
   still receives plain v1.
3. **The wire proves the safety margin.** Every extension either rides an
   entry/field the reference already ignores, or is gated behind a capability the
   reference cannot assert. Both are established empirically below, not assumed.

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
- **Recommendation.** tactus should *consume* an external PTP/gPTP clock rather
  than implement a grandmaster: keep Link for discovery + musical time, layer a
  media clock only where the transport supplies one.

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

### 7.2 Apple USB / p2p networking (the "anpi / 480" question)

The question: can Apple's USB peer-to-peer networking offer the guarantees AVB
wants, given that it is inherently point-to-point?

A naming caveat first: on macOS the `anpi*` interfaces are Apple's *internal*
co-processor management links, not a user data path; the user-facing p2p transports
are USB/NCM tethering, the Thunderbolt/USB-C IP bridge, and AWDL (Apple Wireless
Direct Link). The "480" is USB 2.0's 480 Mbit/s signalling rate. The substantive
question is the same regardless of which of these it is: **can a dedicated USB p2p
link stand in for an AVB fabric?**

Applying the §7.1 analysis:

- **The dedication half: yes.** A USB p2p link is a single-talker dedicated pipe,
  so — exactly like the ad-hoc AVB case — there is no contention to reserve or
  shape against. 480 Mbit/s is ample for many channels of L24/48 kHz (one channel
  ≈ 1.15 Mbit/s), so bandwidth is not the constraint. This is the "given that it's
  p2p it might" intuition, and it is correct: p2p removes AVB's reservation
  requirement for free.
- **The sync half: this is the real limit.** AVB's guarantee is *bounded latency
  with a shared media clock*. USB does not provide 802.1AS or hardware
  timestamping; a clock would have to be software PTP carried over the USB-network
  link. USB 2.0's 125 µs microframe scheduling and host-controller polling add
  jitter that Ethernet PHY timestamping avoids. On a *quiet, dedicated* link this
  can still reach tens of microseconds — good enough for many uses, short of true
  gPTP sub-µs sample lock. So the honest placement is **between T0 and T2**: better
  than best-effort Wi-Fi (dedicated, low-jitter, ample bandwidth), short of switched
  AVB (no hardware time). Whether it meets a *specific* application's sample-lock
  requirement depends on that requirement — for musical/monitoring use it is
  comfortably sufficient; for sample-accurate multi-device capture it needs
  measurement.
- **Practical recommendation.** Treat a USB (or Thunderbolt) p2p link as a **T1-ish
  dedicated transport**: run software PTP over it, feed §6 type-5, and let tactus
  negotiate a latency target (`tcap` type 6) matched to the measured jitter. Bounded
  latency comes from dedication (no contention), sample-accuracy from the software
  clock's achievable precision on that specific hardware. Thunderbolt's lower-jitter
  path would move it closer to T2 than USB 2.0.

## 8. Backward-compatibility & provenance summary

- A tactus peer is a conformant LinkAudio v1 peer; §3 wins are legal v1; §4–§7 are
  entered only between two peers that both advertised `tcap`, and collapse to v1 on
  any mismatch. No reference peer ever sees a native datagram or an unparseable
  message.
- This proposal is a **dirty-side design note**. It cites only observable reference
  behavior (the §1.1 probes and ch. 03 §5.8/§5.9 findings) and public protocol
  facts; it contains no reference-source expression. A clean-room `tactus`
  implementation may build from it under the usual firewall (PROVENANCE.md): the
  spec is the only bridge.

## 9. Open questions

1. **`tcap` fourcc/registry.** `tcap` and the TLV type numbers here are placeholders;
   a real assignment (and a small registry section) is needed before any two
   implementations interoperate.
2. **Native data-plane message type + layout** are sketched (§5), not specified.
   A follow-up chapter (`04-native-audio`) would pin the type number, payload
   grammar, FEC framing, and multicast join.
3. **Clock-domain stamping format** (§6 type-5): how a PTP/gPTP timestamp rides
   alongside beat-time in a native chunk.
4. **USB-p2p sync precision** (§7.2) is asserted from the transport's structure,
   not measured. A capture on real Apple p2p hardware would move the T1/T2
   placement from reasoned to observed — the same [B]→[W] gap the spec tracks
   elsewhere.
5. **Interaction with the §5.9 512-frame limit** for *tactus receivers*: `tcap`
   type 2 advertises each peer's true ceiling, but a default safe value and the
   fallback when type 2 is absent need fixing.
