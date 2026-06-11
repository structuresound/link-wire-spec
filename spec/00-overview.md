# Chapter 0 — Overview, Terminology, and Common Serialization

| | |
|---|---|
| Spec version | 0.1.0 |
| Upstream reference | Ableton/link @ `902aef95bf94af49746fdda5369b42cdcfa1e6d2` |
| License | CC-BY-4.0 |

This document describes protocol facts determined from observation and analysis for
interoperability purposes. It contains no copied expression from the reference
implementation.

---

## 1. Scope

This specification covers the family of UDP protocols used by Ableton Link and the
LinkAudio v1 extension:

- **Chapter 1 (Discovery):** peer discovery and state gossip over multicast/unicast UDP.
- **Chapter 2 (Sync):** clock measurement (ping/pong) and the tempo/beat timeline model.
- **Chapter 3 (Audio):** the LinkAudio v1 protocol for announcing, requesting, and
  streaming audio channels between peers, with beat-aligned scheduling.

This chapter defines terminology, the transport layout, and the **common serialization
rules** that every other chapter depends on.

### 1.1 Evidence classes

So that no statement in this specification can drift from what was actually verified,
claims are tagged with how they are known. The tags appear throughout all chapters:

| Tag | Class | Meaning |
|---|---|---|
| **[W]** | wire-observed | Demonstrated by a released capture in `vectors/`; the auto-generated manifest (`vectors/manifests/`) and the structural checks (`tools/check_vectors.py`) pin the fact to packet bytes. |
| **[B]** | behavioral | Determined by dirty-side analysis of the reference implementation or by runtime experiment, but **not exercised** by the released captures. Reliable, but not currently conformance-testable from the vectors alone. |
| **[N]** | normative | A requirement this specification imposes for interoperability or safety. May be stricter than what the reference enforces. |

Untagged statements describing byte layouts are [W] wherever the message type appears
in any vector, [B] otherwise. The changelog records, for every resolved open
question, which class its verdict rests on.

## 2. Terminology

| Term | Definition |
|---|---|
| **Peer** | One participating application instance on the network, identified by a randomly generated 8-byte node identifier (NodeId). |
| **Session** | A group of peers sharing one tempo/beat timeline. A session is identified by an 8-byte session identifier, which is the NodeId of the peer that founded the session. |
| **Session group** | A 16-bit wire field (`groupId`) present in message headers. The reference implementation always transmits 0 and discards messages with any other value. |
| **Channel** | A named, peer-published audio stream, identified by a random 8-byte channel identifier. Channel names are display strings; identifiers are stable for the channel's lifetime. |
| **Sink** | The *transmitting* end of a channel. A sink announces a channel to the session and transmits audio to subscribed peers. (Note the direction: in this protocol "sink" is the producer-facing object into which an application writes audio.) |
| **Source** | The *receiving* end of a channel. A source subscribes to a remote channel by its channel identifier and receives audio buffers. A sink MUST NOT transmit audio for a channel until at least one source has requested that channel, and MUST stop when no unexpired request remains. |
| **Gateway** | One network interface (one local IP address) over which a peer participates. A peer may run on several gateways simultaneously; the same channel may be reachable via more than one gateway. |
| **Audio endpoint** | The unicast UDP socket address (address + port) at which a peer accepts all LinkAudio v1 traffic on a given gateway. |
| **Measurement endpoint** | The unicast UDP socket address used by the Link sync (ping/pong clock measurement) protocol. Distinct from the audio endpoint. |
| **Timeline** | A (tempo, beat-origin, time-origin) triple establishing a bijection between beats and microsecond wall time (Chapter 2). |
| **Quantum** | A beat count defining the phase-alignment period (e.g. 4 = one bar of 4/4). |

## 3. Transport summary

| Traffic | Transport | Address / port | Max datagram | Frame magic |
|---|---|---|---|---|
| Peer discovery (Chapter 1) | UDP multicast (IPv4) | `224.76.78.75:20808` | 512 bytes | ASCII `_asdp_v` + byte `0x01` |
| Peer discovery (Chapter 1) | UDP multicast (IPv6, link-local) | `ff12::8080` port `20808` | 512 bytes | ASCII `_asdp_v` + byte `0x01` |
| Discovery responses (Chapter 1) | UDP unicast (back to sender) | sender's endpoint | 512 bytes | ASCII `_asdp_v` + byte `0x01` |
| Sync measurement (Chapter 2) | UDP unicast | advertised measurement endpoint (ephemeral port) | — | see Chapter 2 |
| LinkAudio v1 (Chapter 3) | UDP unicast only | advertised audio endpoint (ephemeral port) | 1200 bytes | ASCII `chnnlsv` + byte `0x01` |

All LinkAudio v1 traffic — announcements, requests, keepalives, and audio — is
**unicast**; only Link discovery uses multicast. Audio endpoints are bound with an
OS-assigned (ephemeral) port, one socket per gateway address; the port is advertised
through the discovery protocol (Chapter 3, §2).

The 1200-byte LinkAudio limit is chosen to stay below typical IPv4 (1500) and IPv6
(1280) MTUs after IP and UDP headers, avoiding fragmentation.

## 4. Common serialization rules

All protocols in this family share one serialization scheme. There is no padding, no
alignment, and no field tagging except where the payload container (§4.5) is used.
Fields are written back-to-back in the order given by each message definition.

### 4.1 Primitive types

| Type | Wire size | Encoding |
|---|---|---|
| `u8` | 1 | raw byte |
| `u16` | 2 | unsigned, **big-endian** (network byte order) |
| `u32` | 4 | unsigned, big-endian |
| `u64` | 8 | unsigned, big-endian |
| `i16` / `i32` / `i64` | 2 / 4 / 8 | two's-complement bit pattern, transmitted as the same-size unsigned big-endian value |
| `bool` | 1 | `u8`; 0 = false, any nonzero value decodes as true (encoders write 0 or 1) |
| `duration` (microseconds) | 8 | `i64` count of microseconds |

Decoders MUST reject a primitive read that would run past the end of the available
bytes (the reference treats this as a parse failure for the whole containing item).

### 4.2 Strings

| Offset | Size | Type | Description |
|---|---|---|---|
| 0 | 4 | `u32` | length `N` in bytes |
| 4 | `N` | bytes | string contents, raw bytes (no NUL terminator, no padding) |

The reference treats strings as opaque byte sequences; no character-set validation is
performed [B]. The reference decoder does not bound-check `N` against the remaining
bytes of the enclosing region before constructing the string [B]; a hostile `N`
larger than the available bytes is a memory-safety hazard in a naive port. No string
in any captured vector exceeds its enclosing region [W]. **[N] Requirement:**
implementations MUST treat `N` greater than the remaining byte count as a parse error
and MUST NOT read past the buffer.

### 4.3 Fixed-size arrays

A fixed-size array of `K` elements is encoded as the `K` element encodings
concatenated, **with no count prefix** (the count is implied by the type). The most
important instance is the 8-byte node/channel/session identifier, which is a fixed
array of 8 `u8` values, i.e. 8 raw bytes transmitted in order.

### 4.4 Variable-size vectors

| Offset | Size | Type | Description |
|---|---|---|---|
| 0 | 4 | `u32` | element count `N` |
| 4 | varies | — | `N` element encodings, concatenated |

Element sizes may vary per element (e.g. vectors of structures containing strings).
The reference decoder stops after `N` elements or when the byte range is exhausted,
whichever comes first; it does not treat a short vector as an error.

### 4.5 Payload container (tagged key-value entries)

Several messages carry a *payload*: a concatenation of self-describing entries that
enables forward compatibility. Each entry is:

| Offset | Size | Type | Description |
|---|---|---|---|
| 0 | 4 | `u32` | entry key: a four-character code (fourcc), interpreted as the big-endian `u32` formed by the four ASCII bytes (e.g. `'sess'` = `0x73657373`) |
| 4 | 4 | `u32` | value size `S` in bytes |
| 8 | `S` | bytes | entry value, encoded per the entry's definition |

Rules, stated as protocol requirements derived from observed behavior:

1. Entries are concatenated with no separator; the payload ends at the end of the
   message.
2. A receiver MUST skip entries whose key it does not recognize, using the size field.
3. An entry whose reported size would extend past the end of the message is a parse
   error for the whole payload.
4. A recognized entry whose value decodes to fewer bytes than its declared size is a
   parse error (declared size must be exactly consumed).
5. Encoders MUST omit an entry entirely (no header) when its value serializes to zero
   bytes. This is how *optional* values are encoded throughout the protocol family:
   presence of the entry = value present; absence of the entry = value absent.
6. Receivers MUST NOT assume any particular entry order. (The reference dispatches
   entries through a key-indexed table.)
7. Duplicate keys: each occurrence is dispatched in stream order; a later occurrence
   of the same key overwrites the effect of an earlier one in the reference
   (last-one-wins) [B]. No message in any captured vector emits a duplicate key [W].
   **[N] Requirement:** senders MUST NOT emit duplicate entry keys within one
   payload; receivers SHOULD apply last-one-wins defensively. (One systematic
   exception exists in the sync protocol, where a Pong echoes the Ping's payload
   bytes after its own entries — see Chapter 2 §4.1; the echoed keys do not collide
   with the Pong's own in practice.)

### 4.6 Tuples / composite structures

A composite value (tuple or struct) is encoded as its fields' encodings concatenated
in definition order, with no count, no tags, and no padding. Where a composite is used
as a payload entry value, the entry's size field covers the whole composite.

### 4.7 Music-time scalar types

These appear in both sync and audio chapters:

| Name | Wire type | Semantics |
|---|---|---|
| **Beat value** | `i64` | beats × 1,000,000 ("micro-beats"), rounded to nearest |
| **Tempo** | `i64` | microseconds per beat, computed as round(60 × 10⁶ / bpm). E.g. 120 bpm → 500000 |
| **Host time** | `i64` | microseconds (clock-relative; see usage in each chapter) |

Note that tempo is transmitted as a *period* (µs/beat), not as bpm.

### 4.8 Identifier type

| Name | Wire size | Encoding |
|---|---|---|
| NodeId / SessionId / ChannelId / PeerId | 8 | 8 raw bytes, generated uniformly at random by the originating peer, transmitted in array order |

### 4.9 Common payload entry keys used across chapters

| Key (fourcc) | `u32` value | Value encoding | Meaning |
|---|---|---|---|
| `sess` | `0x73657373` | 8-byte identifier | session membership (founding peer's NodeId) |
| `__ht` | `0x5f5f6874` | `i64` microseconds | host-time ping/pong timestamp |
| `tmln` | `0x746d6c6e` | tempo `i64`, beat-origin `i64`, time-origin `i64` (24 bytes) | timeline (Chapter 2) |
| `mep4` | `0x6d657034` | `u32` IPv4 address (big-endian) + `u16` port (6 bytes) | measurement endpoint, IPv4 |
| `mep6` | `0x6d657036` | 16 address bytes + `u16` port (18 bytes) | measurement endpoint, IPv6 |
| `aep4` | `0x61657034` | `u32` IPv4 address (big-endian) + `u16` port (6 bytes) | audio endpoint, IPv4 (Chapter 3) |
| `aep6` | `0x61657036` | 16 address bytes + `u16` port (18 bytes) | audio endpoint, IPv6 (Chapter 3) |

### 4.10 General error handling

Observed receiver behavior, stated as requirements:

- A datagram that is shorter than the fixed frame (magic + header) or whose first 8
  bytes do not equal the expected frame magic MUST be ignored without error.
- A message whose header parses but whose payload fails to parse MUST be discarded;
  the receiver continues operating. Partial side effects from already-dispatched
  payload entries may have occurred.
- A message carrying the receiver's own NodeId in the header MUST be ignored
  (loopback suppression).
