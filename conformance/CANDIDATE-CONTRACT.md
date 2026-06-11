# Conformance candidate contract

| | |
|---|---|
| Contract version | 1 |
| License | CC-BY-4.0 |

To be tested by the conformance harness (`conformance/run.py`), a candidate
implementation provides an executable that exposes its peer through this
line-based stdin/stdout interface. The contract is deliberately about
*application-observable state only* — peers, tempo, transport, beats, audio
channels — so that neither the harness nor the contract encodes any wire
knowledge beyond the released specification.

The harness launches the executable given by `CANDIDATE_CMD` (and, for audio
scenarios, `CANDIDATE_AUDIO_CMD`), writes commands to its stdin, and reads
status lines from its stdout.

## Requirements

- The peer MUST start in the **disabled** state with tempo 120 bpm and quantum 4.
- Lines are UTF-8, newline-terminated. Unknown commands MUST be ignored.
- Stdout MUST NOT contain lines other than those defined here.

## Commands (stdin)

| Command | Effect |
|---|---|
| `enable` / `disable` | join / leave the network (Link enable state) |
| `tempo <bpm>` | set the session tempo |
| `start` / `stop` | start / stop the transport |
| `startstop-sync <0\|1>` | disable / enable start-stop synchronization |
| `quit` | shut down cleanly (send departure announcements) and exit |
| `audio-enable` / `audio-disable` | (audio feature) enable LinkAudio, publishing exactly one channel / withdraw it |
| `audio-subscribe <index>` | (audio feature) subscribe to the index-th channel of the currently visible channel list (sorted by peer name, then channel name) |
| `audio-unsubscribe` | (audio feature) drop the subscription |

## Status lines (stdout)

Emit `ready` once when the peer is operational, then a `status` line at least
every 500 ms *and* on every state change:

```
status peers=<int> tempo=<float> playing=<0|1> beat=<float> quantum=<float>
```

`beat` is the application beat time at the moment of emission (the value the
implementation would report to its client for "now", at the stated quantum).

Candidates declaring the `audio` feature (via the `CANDIDATE_FEATURES`
environment variable read by the harness) append:

```
 audio=<0|1> channels=<int> receiving=<0|1> publishing=<0|1>
```

where `channels` counts currently visible remote channels and `receiving` is 1
while subscribed audio is arriving.

## Notes

- Timing assertions in the harness allow several seconds; sub-second status
  cadence is sufficient.
- The harness compensates for sampling skew when comparing `beat` values, but
  the value should be computed at (or very near) emission time.
- Exit code of the candidate process is not asserted; `quit` MUST terminate it
  within 5 seconds.
