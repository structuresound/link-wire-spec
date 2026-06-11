# Test vectors

Packet captures (`*.pcap`, libpcap format, Ethernet link-layer) of the **reference**
Ableton Link peers built from the pinned upstream commit
(`LAST_REVIEWED_SHA`), driven through scripted loopback scenarios by
[`tools/capture-vectors.sh`](../tools/capture-vectors.sh). They are golden traces of
real protocol behavior, used to validate the spec text and as conformance fixtures.

These captures are **protocol facts** (uncopyrightable observations of wire
behavior) and contain **no reference source code**. To remove any doubt they are
dedicated to the public domain under **CC0** (see [PROVENANCE.md](../PROVENANCE.md)).

## How they were produced

All peers ran on a single host over the loopback interface (`lo`), so every datagram
appears twice-ish in the routing sense but is captured once on `lo`. Captures were
made with `tcpdump -i lo -U`. Reference binaries: `LinkHutSilent` (Link only, dummy
audio) and `LinkAudioHut` (LinkAudio, JACK dummy backend), both from the pinned SHA.
Regenerate with:

```
sudo tools/capture-vectors.sh                 # all scenarios
sudo tools/capture-vectors.sh sync-tempo-change   # one scenario
```

Because node identifiers, ephemeral ports, clocks and the exact number of
announcement rounds vary per run, captures are **not** byte-for-byte reproducible;
they are reproducible at the level of *which messages appear and how their fields are
laid out*. Conformance checks should assert on message structure, not on timing or
identifiers.

## Protocols by frame magic

| Magic (bytes 0–7) | Protocol | Chapter |
|---|---|---|
| `5F 61 73 64 70 5F 76 01` (`_asdp_v\x01`) | discovery (multicast `224.76.78.75:20808`) | 1 |
| `5F 6C 69 6E 6B 5F 76 01` (`_link_v\x01`) | sync ping/pong (unicast) | 2 |
| `63 68 6E 6E 6C 73 76 01` (`chnnlsv\x01`) | LinkAudio v1 (unicast) | 3 |

## Captures

### `discovery-join-leave.pcap` (≈302 frames)

Two plain Link peers. Peer A enables Link and announces alone; peer B joins ~3 s
later; B then quits (sending a ByeBye) while A keeps announcing. Shows:

- **Alive** (type 1) multicasts to `224.76.78.75:20808`, ~250 ms apart, 107-byte
  datagrams (payload entries `tmln`, `sess`, `stst`, `mep4`; Chapter 1 §6).
- **Response** (type 2) unicast back to a newly heard peer's ephemeral source port.
- **ByeBye** (type 3): 20-byte header, `ttl = 0`, empty payload.
- The full sync **ping/pong** measurement (`_link_v\x01`, types 1/2) that runs once
  the two peers see each other: first ping 25 B, first pong 57 B, steady-state ping
  41 B / pong 73 B (Chapter 2 §4).

### `sync-tempo-change.pcap` (≈343 frames)

Two synced peers; A raises tempo (120→124 bpm), then B lowers it (→122 bpm). Shows
successive `tmln` entries (Chapter 2 §6) with **monotonically increasing
`beatOrigin`** acting as the timeline-priority stamp, and the tempo field encoded as
µs/beat.

### `sync-start-stop.pcap` (≈362 frames)

Two peers with start/stop sync enabled; transport started then stopped on one peer.
Shows the `stst` entry (Chapter 2 §8): 17-byte value = `isPlaying` (u8) + beats (i64
µbeats) + ghost-time timestamp (i64 µs), propagated through discovery and re-gossiped
by both peers.

### `audio-channel-lifecycle.pcap` (≈1356 frames)

Two LinkAudio peers, "Alice" and "Bob", on the JACK dummy backend. Alice publishes a
sink channel; Bob subscribes, receives streamed audio, then unsubscribes; Alice then
withdraws the channel. Shows the complete LinkAudio v1 control + data plane
(Chapter 3):

- **Audio endpoint advertisement** in discovery: 121-byte Alive datagrams carrying
  the extra `aep4` entry (Chapter 3 §2) once LinkAudio is enabled.
- **PeerAnnouncement** (type 1) unicasts with `sess`, `__pi` (peer name), `auca`
  (channel announcements) and the embedded `__ht` ping.
- **Pong** (type 3) replies echoing `__ht`.
- **ChannelRequest** (type 4) and **StopChannelRequest** (type 5), each carrying a
  single `chid` entry.
- **AudioBuffer** (type 6): the bare audio structure with **no `_abu` wrapper** — the
  payload begins directly with the 8-byte channel id (Chapter 3 §5.1, resolves
  open question 1). Observed: `codec = 1` (PCM i16), `sampleRate = 48000`,
  `numChannels = 1`, one chunk, `numBytes = 502` (the sender's per-datagram sample
  cap, Chapter 3 §5.6), and the trailing sample bytes exactly fill `numBytes`.
- **ChannelByes** (type 2) when Alice withdraws her channel.

All LinkAudio datagrams carry `groupId = 0`.

## Not yet captured

- **`discovery-ipv6.pcap`** — the IPv6 link-local variant of discovery. The capture
  environment had no interface with both an IPv4 and a link-local IPv6 address (the
  reference only uses IPv6 on such interfaces), so this vector could not be produced
  here. The capture script includes the scenario and emits it automatically when a
  suitable interface is present. Open question 8 (cross-host usability of advertised
  `aep6` addresses, given scope ids are not transmitted) remains open pending this
  capture.
