# Test vectors

Packet captures (`*.pcap`) of **reference** Ableton Link peers built from the pinned
upstream commit (`LAST_REVIEWED_SHA`), driven through scripted scenarios by
[`tools/capture-vectors.sh`](../tools/capture-vectors.sh). They are golden traces of
real protocol behavior, used to validate the spec text and as conformance fixtures.

These captures are **protocol facts** (uncopyrightable observations of wire behavior)
and contain **no reference source code**. To remove any doubt they are dedicated to
the public domain under **CC0** (see [PROVENANCE.md](../PROVENANCE.md)).

## How to read this directory

Three artifacts per scenario:

| Artifact | Authority |
|---|---|
| `<scenario>.pcap` | the evidence itself |
| [`manifests/<scenario>.md`](manifests/) | facts **generated from the pcap bytes** by [`tools/analyze_pcap.py`](../tools/analyze_pcap.py) — topology, peers, gateways, message-type counts, datagram shapes and sizes. Regenerated with the capture; cannot drift from the capture. |
| the scenario description below | the **script's intent** (which peers were started, which keys were pressed, when) — useful context, but not evidence. Where intent and manifest disagree, the manifest wins. |

Every capture must additionally pass the structural assertions in
[`tools/check_vectors.py`](../tools/check_vectors.py), which verify the pcap really
contains the protocol events its scenario exists to demonstrate (a scenario that
silently failed cannot ship a hollow vector).

## How they were produced

Each scenario runs inside an **isolated network namespace**. The baseline topology is
loopback-only: every peer has exactly one network interface (`lo`), hence exactly one
Link gateway — the manifests confirm this per capture ("gateways per peer"). The
multi-gateway scenario deliberately adds a second interface (a veth device) inside
the namespace. Reference binaries: `LinkHutSilent` (Link only, dummy audio) and
`LinkAudioHut` (LinkAudio, JACK dummy backend), built from the pinned SHA; captures
made with `tcpdump -U` inside the namespace.

Regenerate with:

```
sudo tools/capture-vectors.sh                     # all scenarios
sudo tools/capture-vectors.sh sync-tempo-change   # one scenario
```

Node identifiers, ephemeral ports, clocks, and round counts vary per run, so captures
are reproducible at the level of *which messages appear and how their fields are laid
out*, not byte-for-byte. Conformance checks should assert on structure (as
`check_vectors.py` does), never on identifiers or timing.

## Protocols by frame magic

| Magic (bytes 0–7) | Protocol | Chapter |
|---|---|---|
| `5F 61 73 64 70 5F 76 01` (`_asdp_v\x01`) | discovery (multicast `224.76.78.75:20808`) | 1 |
| `5F 6C 69 6E 6B 5F 76 01` (`_link_v\x01`) | sync ping/pong (unicast) | 2 |
| `63 68 6E 6E 6C 73 76 01` (`chnnlsv\x01`) | LinkAudio v1 (unicast) | 3 |

## Scenarios

### `discovery-join-leave`

Script: peer A enables Link; ~3 s later peer B enables; ~4 s later B quits; A runs on
~2 s more, then quits. Demonstrates — and `check_vectors.py` asserts — multicast
Alive cadence, the unicast Response to a newly heard peer, ByeBye on departure, and
the complete sync measurement chain (initial `Ping{__ht}` 25 B → `Pong` 57 B →
steady-state 41 B/73 B; Chapters 1–2).

Reading note: the manifest reports **three** NodeIds for two processes. That is the
session-reset rule in action (Chapter 2 §7.3): when B's departure leaves A with zero
session peers, A founds a fresh session under a **new random NodeId** and keeps
announcing under it.

### `sync-tempo-change`

Script: two synced peers; A raises the tempo 4 bpm in 1-bpm steps, then B lowers it
2 bpm. Asserted: ≥3 distinct `tmln` tempo values gossiped (manifest lists the exact
µs/beat values) and a strictly increased `beatOrigin` across the changes — the
timeline-priority stamp of Chapter 2 §6.

### `sync-start-stop`

Script: two peers enable start/stop sync; A starts the transport, ~3 s later stops
it. Asserted: `stst` entries with both `isPlaying` values and ≥3 distinct
(isPlaying, timestamp) states — the ghost-time-ordered start/stop propagation of
Chapter 2 §8.

### `audio-channel-lifecycle`

Script: LinkAudio peers "Alice" and "Bob" join a session and enable LinkAudio; Alice
starts her transport; Bob subscribes to Alice's channel and holds the subscription
~12 s; Alice changes tempo mid-stream; Bob unsubscribes; Alice disables LinkAudio;
both quit. Asserted (Chapter 3): `aep4` advertisement in discovery, unicast
PeerAnnouncements and Pongs, ChannelRequest **re-sent** (the 5 s keepalive — ≥2
requests on the wire), the AudioBuffer stream with **no `_abu` wrapper**, codec 1
only, `numBytes` always equal to the trailing sample bytes, chunks carrying **two
distinct tempo values** (the mid-stream change), StopChannelRequest, ChannelByes, and
`groupId` 0 throughout.

### `multi-gateway-discovery`

Script: a second interface is added inside the namespace before two peers enable
Link, so each peer runs **two gateways**. Asserted: at least one NodeId transmits
from two distinct source addresses. The manifest shows each peer announcing
per-gateway with gateway-specific measurement endpoints (Chapter 1 §2's
one-gateway-per-interface model).

### `discovery-ipv6` — not yet captured

The IPv6 link-local variant of discovery. Neither the v0.1.0 nor the v0.4.0 capture
environment's kernel has IPv6 support, so this vector has not been produced (the
capture script detects support and emits it automatically where present). Chapter
3's question 8 (cross-host usability of advertised `aep6` endpoints, given scope
ids are not transmitted) was **resolved [B] at v0.4.0** by reference analysis —
advertised v6 endpoints are always link-local addresses of the sending gateway, so
the receiver's scope substitution is correct by construction on the shared link.
This capture would raise that verdict's evidence class to [W] but is no longer
required to answer the question.
