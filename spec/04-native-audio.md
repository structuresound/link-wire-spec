# Chapter 4 — Tactus Native Audio and Mesh Wire Protocol

| | |
|---|---|
| Spec version | 0.5.0 |
| Status | **Draft-normative** — byte layouts are pinned (change only by errata before 1.0), golden-capture evidence pending (§1.1) |
| Upstream reference | none — this chapter specifies an **original** protocol; every fact about v1 peers cites Chapters 0–3 |
| License | CC-BY-4.0 |

This chapter is an original protocol design. It is clean by construction: it is
not derived from any reference implementation, and the provenance firewall
(PROVENANCE.md) applies only to the LinkAudio v1 facts it cites from Chapters
0–3. It normatively pins the wire encodings sketched in
`spec/proposals/tactus-native-audio.md` (the *proposal*), which remains the
rationale record; where the two disagree, this chapter wins.

All encodings use the common serialization rules of Chapter 0 §4 (big-endian
integers, length-prefixed strings, the tagged payload container, 8-byte
identifiers) unless stated otherwise.

---

## 1. Scope and evidence model

Native mode is what two tactus peers speak *between themselves*: negotiated
codecs, chunks above the v1 512-frame ceiling, forward error correction,
multicast fan-out, media-clock stamping, and a signed gossip layer for the mesh
control plane. Toward any peer not known to be tactus, conformant LinkAudio v1
(Chapter 3) — including the §5.9 512-frame-per-chunk cap — remains the floor,
and everything in this chapter is invisible: capabilities ride a payload entry
v1 peers skip (Chapter 0 §4.5 rule 2), and native datagrams use message types
v1 peers ignore (Chapter 3 §9).

This chapter closes proposal open questions §10.1 (`tcap` assignment and
registry, §2), §10.2 (native data-plane grammar, §4–§5), §10.3 (clock-domain
stamping, §4.4, §8), §10.5 (default chunk ceiling, §7.2), and §10.6 (gossip
record encoding and the spec/`ipauro-mesh` boundary, §9). §10.4 (measured p2p
sync precision) remains open.

### 1.1 Evidence classes for native content

The Chapter 0 §1.1 classes are reference-anchored and do not transfer to a
protocol with no upstream. For this chapter:

| Tag | Meaning here |
|---|---|
| **[N]** | unchanged: a requirement of this specification |
| **[D]** | design rationale: a decision argued from the proposal's analysis, with no external oracle |
| **[W]** | for native content: exercised by a released **tactus golden capture** (candidate-vs-candidate under the conformance harness's self-test structure), pinned by manifest + structural checks — the oracle is this spec, not the reference |
| **[B]** | applies only to cited v1 facts, with the Chapter 0 meaning |

No native golden captures exist yet; no native claim below carries [W]. The
chapter leaves Draft-normative status when two independently written peers (or
the candidate self-test pair) interoperate on released captures covering §4,
§5, and §6.

## 2. Capability advertisement: the `tcap` entry

### 2.1 Assignment

The fourcc **`tcap` = `0x74636170`** is assigned (final, was placeholder) as a
payload-container entry key on the LinkAudio v1 control plane. It MAY appear
in:

- **PeerAnnouncement** (type 1, Chapter 3 §4.1) — the peer's standing
  capabilities on that gateway;
- **ChannelRequest** (type 4, Chapter 3 §4.3) — the requester's receive
  constraints for that subscription (§3).

It MUST NOT appear in any other v1 message type, and native content MUST NOT
be placed in any other new entry key without a future version of this
specification [N]. Reference peers skip the entry by size (Chapter 0 §4.5
rule 2; probed on announcements, proposal §1.1) [B].

Announcement splitting (Chapter 3 §4.1): `tcap` SHOULD be included in every
announcement message; a receiver MUST retain a peer's last-seen `tcap` until
no announcement from that peer has carried one for the announcement ttl (5 s),
and only then treat the peer as having withdrawn native capability [N]. This
keeps split rounds and occasional omissions from flapping native mode.

### 2.2 Capability block encoding

The `tcap` entry value is:

| Offset | Size | Type | Description |
|---|---|---|---|
| 0 | 2 | `u16` | capability-block version; this chapter defines **1** |
| 2 | to end of entry | — | TLV list |

A receiver that does not recognize the version MUST treat the peer as
non-native (ignore the whole entry) [N].

Each TLV:

| Offset | Size | Type | Description |
|---|---|---|---|
| 0 | 2 | `u16` | type (registry §2.3) |
| 2 | 2 | `u16` | value length `L` in bytes |
| 4 | `L` | bytes | value |

Rules, mirroring the payload container's (Chapter 0 §4.5) [N]:

1. Unknown types MUST be skipped via `L`.
2. A TLV whose `L` runs past the end of the entry invalidates the whole entry.
3. Senders MUST NOT emit duplicate types; receivers apply last-one-wins.
4. A TLV whose value is shorter than its type's defined minimum is invalid and
   MUST be ignored (the rest of the list is still processed).

### 2.3 TLV type registry

| Type | Name | Value encoding | Defined in |
|---|---|---|---|
| 0 | invalid | never emitted; reserved as the parse-failure marker | — |
| 1 | decode codecs | `u32` bitmap: bit 0 PCM i16, bit 1 PCM i24, bit 2 PCM f32, bit 3 FLAC, bit 4 Opus; other bits reserved (senders 0, receivers ignore) | §4.5 |
| 2 | max chunk frames | `u16` ≥ 512: the peer's own per-chunk render ceiling as a receiver | §7.2 |
| 3 | native multicast group | 6 bytes (IPv4: `u32` address + `u16` port) or 18 bytes (IPv6: 16 address bytes + `u16` port), `aep`-style (Chapter 3 §2): the group this peer **transmits** native audio on | §6 |
| 4 | FEC decode schemes | `u32` bitmap: bit 0 XOR parity, bit 1 RaptorQ; other bits reserved | §5 |
| 5 | clock domains | `N` × 10-byte clock-domain records (§8.1), `N` = `L`/10 | §8 |
| 6 | latency target | `u64` nanoseconds: the receive-side scheduling target the peer asks senders to aim for | §7.3 |
| 7 | flags | `u32` bitmap: bit 0 = will join multicast groups as a receiver; other bits reserved | §6 |
| 8 | max datagram bytes | `u16` ≥ 1200: largest native datagram the peer accepts | §7.1 |

Allocation policy [N]: types 9–`0x7FFF` are assigned only by future versions
of this specification; types `0x8000`–`0xFFFF` are private/experimental and
MUST NOT be required for interoperation. The same split governs future codec
ids (§4.5), FEC scheme ids (§5.1), clock kinds (§8.1), gossip record types
(§9.2), transport kinds (§9.3), and metric ids (§9.6): values up to `0x7F`
(or `0x7FFF` for 16-bit registries) are spec-assigned, the rest private.

Semantics and defaults:

- **Absent TLV 1** — the peer decodes PCM i16 only. Every tactus receiver MUST
  accept PCM i16 (the v1 floor), so bit 0 MUST be set whenever type 1 is
  emitted [N].
- **Absent TLV 2** — the peer's chunk ceiling is **512** frames (§7.2).
- **Absent TLV 4** — the peer cannot use FEC repair; senders MUST NOT count on
  repair datagrams being processed (they MAY still send them; receivers ignore
  unknown types).
- **Absent TLV 8** — the peer accepts native datagrams up to **1200** bytes.
- TLV 3 and TLV 7 are role-asymmetric: 3 is a transmitter-side datum (where
  this peer's multicast output appears), 7 bit 0 a receiver-side one (this
  peer will join groups).

## 3. Per-channel modes and the upgrade handshake

Native mode is decided **per (channel, requester) at the sink**, and the data
plane is self-describing, so no acceptance/grant message exists. The design
rule [D]: negotiation never *selects* the stream format — it only establishes
the envelope the receiver can accept; the sink chooses within it and every
datagram declares what it is.

### 3.1 Requester side

A tactus source attaches `tcap` (its receive constraints: at minimum TLV 1;
TLVs 2, 4, 6, 7, 8 as applicable) to **every** ChannelRequest it sends,
regardless of what it knows about the sink [N]. A reference sink skips the
entry and serves v1; no ordering or discovery precondition exists. A source
MAY narrow its request `tcap` relative to its announcement `tcap` to steer the
sink's choice (e.g. advertise only Opus to force low bandwidth) [D].

A subscribed native source MUST accept, at any time and in any interleaving,
both v1 AudioBuffer (type 6) and native media (type 16) datagrams for its
channel, scheduling both on the beat grid (Chapter 3 §6) [N]. This single rule
makes every upgrade, downgrade, and fallback seamless: format is whatever
arrives.

### 3.2 Sink side

Per (channel, requester), re-evaluated on every request (initial or 5 s
refresh, Chapter 3 §4.3):

| Request carries | Codec intersection (requester TLV 1 ∩ sink's encodable set) | Mode served |
|---|---|---|
| no valid `tcap` | — | **v1** (Chapter 3 §5, ≤ 512 frames/chunk per §5.9) |
| valid `tcap` | empty | **v1** |
| valid `tcap` | non-empty | **native** (unicast §4, or multicast §6) |

Constraints on native service [N]: chunk frames ≤ the requester's TLV 2
(default 512); datagram bytes ≤ min(sender's own limit, requester's TLV 8,
1200 if absent); codec ∈ the intersection; repair datagrams only meaningful if
the requester advertised the scheme in TLV 4.

Fallback triggers, all downgrading to v1 with no interruption [N]:

- a request refresh arrives without `tcap` (requester dropped native);
- the intersection becomes empty (either side narrowed capabilities);
- sink-side native resources are withdrawn (sink simply resumes type-6
  encoding).

Requester expiry, StopChannelRequest, per-requester state, and the
transmission conditions of Chapter 3 §5.7 and §7.2 apply to native service
unchanged [N].

### 3.3 Continuity across format switches

The per-channel **chunk sequence number** (Chapter 3 §5.3) is a single counter
at the sender, shared by v1 and native encodings; a format switch MUST occur
at a chunk boundary and MUST NOT reset, skip, or repeat sequence numbers [N].
Loss detection therefore spans switches. The native **datagram sequence**
(§4.2) counts type-16 datagrams only and simply pauses while a channel is
served as v1.

## 4. Native media datagram (message type 16)

### 4.1 Framing

Native datagrams use the LinkAudio framing of Chapter 3 §3 unchanged: the
`chnnlsv 0x01` magic, the 20-byte header, the same audio endpoint sockets, and
the same admission rules. New type values:

| Value | Name | ttl | Payload form |
|---|---|---|---|
| 16 | NativeMedia | 0 | bare structure (§4.2); no payload container |
| 17 | NativeRepair | 0 | bare structure (§5.2); no payload container |

Types 7–15 remain unassigned. Reference peers ignore both types (Chapter 3
§9; type-7/garbage probe, proposal §1.1) [B].

### 4.2 Payload layout

Let `N` = chunk count, `C` = 1 if the clocked flag is set else 0. Offsets are
relative to the payload start (datagram offset 20):

| Offset | Size | Type | Description |
|---|---|---|---|
| 0 | 8 | id | channel identifier |
| 8 | 8 | id | sender's session identifier |
| 16 | 4 | `u32` | **datagram sequence**: per-channel count of type-16 datagrams, first = 1; compared modulo 2³² (RFC 1982 serial arithmetic) |
| 20 | 1 | `u8` | flags: bit 0 = clocked (per-chunk domain timestamps present); bits 1–7 reserved, senders 0, receivers ignore |
| 21 | 1 | `u8` | codec (§4.5) |
| 22 | 4 | `u32` | sample rate, Hz |
| 26 | 1 | `u8` | interleaved channel count, ≥ 1 |
| 27 | 1 | `u8` | chunk count `N`, MUST be ≥ 1 |
| 28 | 10·C | — | clock-domain record (§8.1), present iff clocked |
| 28 + 10·C | `N` × (28 + 8·C) | — | chunk records (§4.3) |
| … | Σ codedBytes | bytes | coded chunk payloads, concatenated in chunk order |

The coded payloads MUST extend exactly to the end of the datagram (as v1,
Chapter 3 §5.2) [N]. As in v1, the same encoded bytes are sent to every
unicast requester served natively with identical parameters, and one copy to
a multicast group (§6); the datagram sequence is per channel, not per
requester [N].

### 4.3 Chunk record (28 or 36 bytes)

The v1 chunk record (Chapter 3 §5.3) extended by a coded length and an
optional domain timestamp:

| Offset | Size | Type | Description |
|---|---|---|---|
| 0 | 8 | `u64` | chunk sequence number (the Chapter 3 §5.3 counter, shared with v1; §3.3) |
| 8 | 2 | `u16` | `numFrames` covered by this chunk, ≥ 1 |
| 10 | 8 | `i64` | session beat time of the first frame, micro-beats (Chapter 3 §6, unchanged) |
| 18 | 8 | `i64` | tempo, µs per beat |
| 26 | 2 | `u16` | `codedBytes`: size of this chunk's coded payload |
| 28 | 8·C | `u64` | domain time of the first frame, **nanoseconds** in the datagram's clock domain (§8.2), present iff clocked |

Beat time MUST be present and valid in every chunk, clocked or not — domain
time is an *additional* schedule for receivers disciplined to the same domain,
never a replacement [N]. Each chunk's payload is independently decodable
(§4.5): a lost datagram never invalidates a later one [N].

### 4.4 Chunk ceilings

`numFrames` MUST NOT exceed the receiving peer's ceiling: its TLV 2 value, or
**512** when TLV 2 is absent (for a multicast group, the minimum over joined
requesters' ceilings, §6.3) [N]. The 512 default is deliberately the Chapter 3
§5.9 v1-interop constant, so an implementation that never parses TLV 2 is
automatically safe [D]. Receivers MUST bound their decode-to-render copy by
their real capacity regardless of what arrives (Chapter 3 §5.9 receiver rule
applies to native reception too) [N].

### 4.5 Codec registry and per-codec rules

| Value | Name | Coded form of one chunk (`numFrames` F, `channels` H) |
|---|---|---|
| 0 | invalid | MUST NOT be transmitted; receivers reject the datagram |
| 1 | PCM i16 | as v1 (Chapter 3 §5.5): 16-bit two's-complement big-endian, frame-interleaved; `codedBytes` = 2·F·H |
| 2 | PCM i24 | 3-byte two's-complement big-endian samples, frame-interleaved; `codedBytes` = 3·F·H |
| 3 | PCM f32 | IEEE 754 binary32, big-endian, nominal range ±1.0, frame-interleaved; `codedBytes` = 4·F·H |
| 4 | FLAC | one self-contained FLAC frame (streamable subset); its blocksize MUST equal F, its sample rate, channel count, and bit depth (16 or 24) MUST match the datagram header |
| 5 | Opus | one Opus packet (RFC 6716); header sample rate MUST be 8000, 12000, 16000, 24000, or 48000 Hz; H MUST be 1 or 2; the packet's decoded duration MUST equal F frames at the header rate |

Validation [N]: a receiver MUST reject a datagram whose codec is 0 or
unrecognized (no v1-style silent fall-through — this is the fix for Chapter 3
§5.4), whose PCM `codedBytes` fails the arithmetic above, or whose coded
chunk decodes to a frame count ≠ `numFrames`. Channel counts above 2 are
legal on the wire for PCM codecs; whether a receiver renders them is
implementation-defined, but size validation MUST still be applied.

The codec sent MUST be in the receiver's TLV 1 bitmap (bit positions match
codec values minus 1) [N]. Within the intersection the choice is the sink's;
it SHOULD honor the order of its own preference and MAY switch codecs at a
chunk boundary (each datagram is self-describing) [D].

## 5. FEC repair datagram (message type 17)

Repair protects the open-loop data plane (Chapter 3 §5.8) without a feedback
channel: the sender emits redundancy; receivers that advertised the scheme
(TLV 4) use it; everyone else ignores type 17.

### 5.1 Model and scheme registry

Repair covers **windows of consecutive type-16 datagrams of one channel**,
identified by datagram sequence (§4.2). The protected unit is the type-16
**message payload** (datagram bytes from offset 20), zero-padded to the
window's longest payload. A recovered payload is processed exactly as if its
type-16 datagram had arrived [N].

| Scheme | Value | Recovery power |
|---|---|---|
| XOR parity | 1 | any 1 loss per window |
| RaptorQ (RFC 6330) | 2 | up to `r` losses per window given `r` repair symbols (probabilistically, per RFC 6330) |

### 5.2 Payload layout

| Offset | Size | Type | Description |
|---|---|---|---|
| 0 | 8 | id | channel identifier |
| 8 | 8 | id | sender's session identifier |
| 16 | 1 | `u8` | scheme (§5.1) |
| 17 | 4 | `u32` | `firstSeq`: datagram sequence of the window's first covered type-16 datagram |
| 21 | 1 | `u8` | `K`: number of covered datagrams, 2 ≤ K ≤ 32; the window is `firstSeq … firstSeq+K−1` |
| 22 | 2 | `u16` | `T`: padded payload size = the longest covered payload's length |
| 24 | scheme-specific | — | below |

**Scheme 1 (XOR):** `T` bytes — the byte-wise XOR of the K covered payloads,
each zero-padded to `T`. A receiver holding K−1 of the K payloads recovers the
missing one as the XOR of the repair bytes with the K−1 known padded payloads,
then trims trailing zero padding by parsing (§4.2's "extends exactly to the
end" rule bounds the real length; the parsed structure determines it) [N].
Senders MUST emit at most one XOR repair datagram per window [N].

**Scheme 2 (RaptorQ):** a 3-byte `u24` encoding symbol id (ESI), then one
`T`-byte repair symbol. The source block is the K covered payloads zero-padded
to `T`, one payload per source symbol (ESI 0…K−1 in sequence order); repair
symbols carry ESI ≥ K; encoding and decoding per RFC 6330 with symbol size
`T`. A sender MAY emit any number of repair symbols per window (distinct
ESIs) [N].

### 5.3 Sender and receiver rules

- Repair windows MUST NOT overlap and MUST cover only one channel [N]. Window
  size, scheme choice, and repair rate are sender policy, bounded by the
  receiver's TLV 4 [D].
- Repair datagrams follow the media path (same unicast destination or
  multicast group) and count against the same datagram size limit (§7.1) [N].
- Receivers MUST tolerate missing, reordered, or duplicate repair datagrams,
  and MUST ignore repair for windows they have fully received [N].
- Repair recovers *datagrams*, not lateness: recovered chunks are still
  scheduled by beat/domain time and may be too late to play; recovery is most
  valuable when the sender keeps windows short relative to the latency target
  (§7.3) [D].

## 6. Multicast operation

### 6.1 Group advertisement

A transmitting peer that can serve native multicast advertises **one group per
gateway** in its announcement `tcap` TLV 3 (family matching the gateway, as
`aep4`/`aep6` do). The group address MUST be a multicast address and SHOULD be
administratively scoped (IPv4 `239.0.0.0/8`, RFC 2365; IPv6 organization-local
scope `ff18::/16`) with spread confined to the deployment's administrative
domain; scope administration is deployment policy [N]. All of the sink's
multicast-served channels on that gateway share the one group; receivers
demultiplex by channel id [D].

### 6.2 Join semantics

A native requester that set flags bit 0 (TLV 7) and requested a channel from a
sink advertising TLV 3 SHOULD join the group (IGMP/MLD) for the lifetime of
its subscription and leave when the subscription ends [N]. Group membership is
IP-level only; subscription state remains the unicast ChannelRequest keepalive
loop of Chapter 3 §4.3, unchanged [N].

Receivers on a group MUST discard datagrams whose header NodeId is not the
expected sink's, whose channel id is not one they subscribed to, or whose
session id differs from their own current session — the group address space is
unauthenticated and may collide [N].

Multicast delivery is not observable to the sender. A source that joined a
group but receives no type-16 datagram for a subscribed multicast-served
channel within **2 seconds** SHOULD clear flags bit 0 in its next request
refresh, converting itself to unicast service (§3.2 re-evaluation) [N]. This
bounds the damage of non-multicast-capable segments to one refresh period [D].

### 6.3 Sink service rule

A sink MAY serve a channel to the group when at least two native requesters
with flags bit 0 share a non-empty codec intersection; the group stream's
parameters are chosen from the intersection **over the joined requesters**,
with chunk frames ≤ the minimum of their ceilings and datagram size ≤ the
minimum of their TLV 8 limits [N]. Requesters outside that intersection, and
all v1 requesters, continue to receive per-requester unicast copies (Chapter 3
§5.7) concurrently — a reference peer subscribing to a multicast-served
channel still sees a conformant v1 unicast stream [N]. With one (or zero)
group-capable requesters left, the sink SHOULD revert to unicast [D].

## 7. Sizing and latency

### 7.1 Datagram size

Native datagrams MUST NOT exceed min(sender limit, receiver's TLV 8, 1200
when absent) bytes; TLV 8 values below 1200 are invalid (§2.3 sets 1200 as
the floor every implementation accepts, matching the Chapter 3 §3.1 socket
bound) [N]. Datagrams above 1200 bytes will fragment on standard-MTU paths;
senders SHOULD exceed 1200 only on dedicated links whose MTU and loss profile
they know (proposal §7.2) [D].

### 7.2 Chunk ceiling default

When a native peer's `tcap` carries no TLV 2, its ceiling is **512 frames per
chunk** — identical to the Chapter 3 §5.9 v1-interop constraint — and TLV 2
values below 512 are invalid (a tactus receiver MUST stage at least 512-frame
chunks; that is what "v1 floor" means on the receive side) [N]. This closes
proposal §10.5.

### 7.3 Latency targets

TLV 6 declares the receive-side scheduling target in nanoseconds: the delay,
from a frame's rendering at the source to its datagram's transmission, that
the receiver's buffering is provisioned for. A sink SHOULD bound its batching
(chunk coalescing, FEC window length) so that the oldest frame in any
datagram is younger than the smallest active requester's target; where
targets conflict with efficiency, the smallest target wins [N]. The target is
advisory scheduling input, not a delivery guarantee — bounded latency exists
only where the transport provides it (proposal §7) [D].

## 8. Media clock domains

### 8.1 Clock-domain record (10 bytes)

Used in `tcap` TLV 5 (list) and in the clocked type-16 header (§4.2):

| Offset | Size | Type | Description |
|---|---|---|---|
| 0 | 1 | `u8` | kind: 0 invalid; 1 = IEEE 1588-2019 PTP; 2 = IEEE 802.1AS gPTP; 3 = transport-native (recovered clock / master-by-construction, proposal §7.2) |
| 1 | 1 | `u8` | domain number (PTP/gPTP domain; 0 for kind 3) |
| 2 | 8 | bytes | identity: kinds 1–2, the grandmaster ClockIdentity (EUI-64); kind 3, the Link NodeId of the clock-master peer |

Two records denote the same domain iff kind, domain number, and identity all
match [N].

### 8.2 Domain time

Chunk domain time (§4.3) is `u64` nanoseconds: for kinds 1–2, the PTP
timescale (TAI nanoseconds since the PTP epoch); for kind 3, nanoseconds on
the master's monotonic timebase — arbitrary origin, no discontinuities while
the identity is unchanged [N].

A receiver disciplined to the datagram's domain (same §8.1 triple in its own
TLV 5) MAY schedule samples by domain time for sample-accurate alignment; all
other receivers MUST fall back to beat time, which is always present (§4.3)
[N]. A sink MUST stamp a channel from at most one domain at a time and MUST
change domains only at a datagram boundary, updating the header record [N].

### 8.3 Who serves the clock

tactus consumes a media clock, never implements a grandmaster (proposal §6)
[D]. Kind-3 masters are elected per §9.7; PTP/gPTP domains are external
infrastructure whose presence peers merely advertise.

## 9. Mesh gossip records

The mesh control plane runs **above** the datagram protocols, over a reliable,
authenticated overlay (proposal §8.2); gossip records never appear in Link
discovery or LinkAudio datagrams [N]. This section pins only what independent
meshes need to interoperate: identity, record bytes, and adoption/ordering
rules. Route computation, optimization, and policy *content* are the
orchestration layer's (`ipauro-mesh`), by design (proposal §8; this is the
§10.6 boundary) [D].

### 9.1 Identity

A mesh node's identity is an Ed25519 public key (RFC 8032), 32 bytes. Its
PeerRecord (§9.3) binds that key to the node's 8-byte Link NodeId; the
envelope signature makes the binding self-certifying — a receiver MUST NOT
accept a NodeId↔key binding from any other source [N]. (NodeIds regenerate on
session re-found, Chapter 2 §7.3; a fresh PeerRecord re-binds.)

### 9.2 Record envelope

Records travel on reliable overlay streams, each prefixed by a `u32` byte
length. Inside:

| Offset | Size | Type | Description |
|---|---|---|---|
| 0 | 1 | `u8` | envelope version = 1 |
| 1 | 1 | `u8` | record type: 1 PeerRecord, 2 LinkRecord, 3 DemandRecord, 4 PolicyRecord |
| 2 | 32 | bytes | origin public key |
| 34 | 8 | `u64` | `originSeq`: strictly increasing per (origin, record type, subject §9.6) |
| 42 | 8 | `u64` | `issuedAt`: µs since the Unix epoch, informational only (the mesh has no shared wall clock; ordering is `originSeq`) |
| 50 | 4 | `u32` | body length `B` |
| 54 | `B` | bytes | body (per record type) |
| 54 + `B` | 64 | bytes | Ed25519 signature over bytes 0 … 54+`B`−1 |

Receivers MUST drop records with unknown envelope versions, invalid
signatures, or bodies that fail to parse; unknown record *types* MUST be
re-gossiped opaquely (forward compatibility: intermediaries do not gate what
they cannot read, the signature protects it) [N].

### 9.3 PeerRecord (type 1) — subject: the origin itself

| Field | Encoding |
|---|---|
| Link NodeId | 8 bytes (the §9.1 binding) |
| display name | string (Chapter 0 §4.2) |
| transport count | `u8`, then per transport: |
| — kind | `u8`: 1 Link gateway (multicast segment), 2 overlay direct, 3 overlay relay, 4 p2p bridge (Thunderbolt/USB) |
| — endpoint | `u16` length + bytes: kinds 1 and 4, a family-tagged socket address (`u8` family 4 or 6, then 4 or 16 address bytes, then `u16` port); kinds 2–3, opaque overlay addressing bytes (overlay-defined) |
| tcap | `u16` length + a §2.2 capability block (version + TLVs) |

### 9.4 LinkRecord (type 2) — subject: (target key, transport kind)

Directional measurements origin → target:

| Field | Encoding |
|---|---|
| target public key | 32 bytes |
| transport kind | `u8` (§9.3 values) |
| RTT | `u32` µs; `0xFFFFFFFF` = unknown |
| jitter | `u32` µs; `0xFFFFFFFF` = unknown |
| loss | `u16`: lost/65535 fraction over the measurement window |
| bandwidth estimate | `u32` kbit/s; 0 = unknown |

The RTT/jitter inputs SHOULD be the Chapter 3 §4.2 keepalive metrics where
the transport is a v1 path [D].

### 9.5 DemandRecord (type 3) — subject: flow id

A declared wish to receive a channel, input to route planning:

| Field | Encoding |
|---|---|
| flow id | 8 bytes, origin-chosen, stable per demand |
| channel id | 8 bytes (Chapter 0 §4.8) |
| publisher public key | 32 bytes |
| acceptable codecs | `u32` bitmap (TLV 1 semantics) |
| latency target | `u64` ns |
| priority | `u8`, 255 highest |

### 9.6 PolicyRecord (type 4) — subject: singleton, epoch-ordered

| Field | Encoding |
|---|---|
| epoch | `u64` |
| trust mode | `u8`: 0 open (jam — any valid signature admitted), 1 roster (adhoc — only roster keys admitted), 2 pinned (stage — roster keys, no runtime additions) |
| roster hash | 32 bytes: SHA-256 over the concatenation of the sorted (byte-wise ascending) admitted public keys; all-zeros in mode 0 |
| weight count | `u32`, then per weight: `u16` metric id (1 RTT, 2 jitter, 3 loss, 4 bandwidth, 5 hop count), `f32` weight (IEEE 754 big-endian) |

Adoption and ordering [N]: freshest-wins per (origin, type, subject) by
`originSeq` for types 1–3. PolicyRecord alone is globally ordered: adopt iff
`epoch` is greater than the current one, or equal with a byte-wise smaller
origin key — the monotonic policy epoch is the mesh's only strongly-ordered
datum (proposal §8.3). Nodes MUST NOT act on a record admissible under a
weaker trust mode than the policy in force.

### 9.7 Role election

Single-owner roles — the kind-3 clock master of §8.1, the multicast-group
owner where several sinks could claim one group, and analogous roles — are
computed, never negotiated: from the converged PeerRecord set, the candidates
are the peers whose `tcap` establishes the prerequisite (e.g. TLV 5 lists the
domain; TLV 3 claims the group), and the winner is the candidate with the
**byte-wise smallest origin public key** [N]. Every node evaluates the same
rule on the same gossiped inputs, mirroring the determinism of the Chapter 2
§7.2 session election (whose id tie-break this intentionally echoes); a
partition elects per-partition and reconciles deterministically on merge [D].

### 9.8 Consistency model (informative)

Consistency follows from gossip convergence of *inputs*: nodes share topology
(PeerRecords, LinkRecords), demand (DemandRecords), and one objective
(PolicyRecord epoch), and each deterministically recomputes routes
link-state-style — same inputs, same function, same answer, no output
consensus. Transient disagreement during churn is a briefly suboptimal route;
oscillation is damped by replacing a path only with a strictly better one
(Chapter 3 §4.2's hysteresis, applied to route selection). The algorithms
live in `ipauro-mesh`.

## 10. Security considerations (interim)

A dedicated Security Considerations chapter is planned; until then [N]:

- The **datagram plane is unauthenticated by design** (Chapters 1–3 inherit
  the trusted-local-segment assumption; native types 16/17 add no crypto).
  Deployments crossing trust boundaries MUST NOT rely on datagram contents
  for identity; identity enters only at the overlay (§9.1).
- Multicast widens the unauthenticated surface: the §6.2 filtering rules are
  mandatory, and administratively-scoped groups (§6.1) are the containment
  mechanism.
- Gossip records are signed but **replayable within an origin's lifetime**;
  `originSeq` freshest-wins bounds replay to reverting a subject to a stale
  state no older than the receiver's last-seen record. Receivers SHOULD
  persist last-seen `originSeq` per (origin, type, subject) across restarts
  where the trust mode is 1 or 2.
- Trust mode 0 (open/jam) admits any key — appropriate exactly where v1's
  open-LAN posture already is, and nowhere else.

## 11. Constants summary

| Constant | Value |
|---|---|
| `tcap` | `0x74636170` (assigned, final) |
| Capability-block version | 1 |
| TLV types | 1 codecs, 2 max chunk frames, 3 multicast group, 4 FEC schemes, 5 clock domains, 6 latency target, 7 flags, 8 max datagram |
| TLV registry split | 9–`0x7FFF` spec-assigned; `0x8000`–`0xFFFF` private |
| Message types | 16 NativeMedia, 17 NativeRepair (7–15 unassigned) |
| Codec ids | 1 i16, 2 i24, 3 f32, 4 FLAC, 5 Opus |
| FEC schemes | 1 XOR parity, 2 RaptorQ (RFC 6330) |
| FEC window | 2 ≤ K ≤ 32 datagrams |
| Default / minimum chunk ceiling | 512 frames (Chapter 3 §5.9 constant) |
| Default / minimum max datagram | 1200 bytes |
| Multicast no-data fallback | 2 s |
| Clock kinds | 1 PTP, 2 gPTP, 3 transport-native |
| Clock-domain record | 10 bytes; domain time `u64` ns |
| Chunk record | 28 bytes, 36 clocked |
| Gossip envelope version | 1; Ed25519 (RFC 8032) signatures; SHA-256 roster hash |
| Record types | 1 Peer, 2 Link, 3 Demand, 4 Policy |
| Transport kinds | 1 Link gateway, 2 overlay direct, 3 overlay relay, 4 p2p bridge |
| Metric ids | 1 RTT, 2 jitter, 3 loss, 4 bandwidth, 5 hop count |
| Trust modes | 0 open, 1 roster, 2 pinned |

## 12. Question tracking

Closed by this chapter (proposal §10): **1** (`tcap` assignment + registry,
§2), **2** (native grammar, message types, FEC framing, multicast join,
§4–§6), **3** (clock-domain stamping, §4.3, §8), **5** (default ceiling,
§7.2), **6** (gossip encoding + boundary, §9).

Remaining open:

1. **Proposal §10.4** — measured p2p sync precision on Apple USB/Thunderbolt
   hardware (would move §8 kind-3 placement from [D] to measured).
2. **Golden captures** — no native claim carries [W] yet (§1.1); the chapter
   holds Draft-normative status until candidate-vs-candidate captures cover
   §4, §5, §6.
3. **Opus/FLAC conformance detail** — whether chunk-independent coding needs
   further pinning (e.g. Opus pre-skip handling at stream start) will be
   settled by the first interop captures.
