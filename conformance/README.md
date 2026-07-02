# Conformance harness

Drives a **reference** Link peer (built from the pinned upstream commit) and a
**candidate** implementation side by side through the same scenarios the test
vectors capture, and emits pass/fail **observations** as plain text:

```
OBS | tempo-follow | PASS | reference adopted candidate's tempo 100 bpm in 0.2s (reference reports 100.0)
```

## Why it lives in the spec repository

This harness is dirty-side tooling (its authors read the GPL reference; see
[PROVENANCE.md](../PROVENANCE.md)), so it is published here — behind the spec
repo's release gate, where provenance review happens — rather than authored
into the clean-side implementation repo. It is part of the release artifact
(MIT, like the capture tooling). The clean side consumes it the same way it
consumes vectors: **from a released version**, fetched into CI caches at a
pinned tag and never vendored. The clean team performs its own integration
(see "Integrating in a candidate repository" below), which requires no
protocol knowledge.

Two properties keep that consumption safe:

1. **No protocol logic.** The harness never constructs, parses, or inspects a
   network message. Every assertion is about *observable endpoint behavior*:
   what each peer reports about its peers, tempo, transport, beat position,
   and audio reception. Reading this code teaches nothing about the wire
   beyond what the released spec already states.
2. **Observations only.** Results are pass/fail statements with measured
   behavior — the form of evidence the PROVENANCE firewall explicitly permits
   the clean side to use. Never reference-source diffs.

The reference itself is cloned and built **outside the repository**
(`tools/build-reference.sh`) and exists only in CI caches.

## Files

| File | Role |
|---|---|
| `run.py` | scenario runner and assertions (pure orchestration) |
| `hut_adapter.py` | drives the reference hut binaries through their own keyboard/stdout interface, translating to the candidate contract; also serves as the self-test stand-in candidate |
| `run-isolated.sh` | wrapper: builds the reference, enters an isolated network namespace (loopback only), starts a dummy JACK server, runs `run.py` |
| `CANDIDATE-CONTRACT.md` | the stdin/stdout interface a candidate must expose |
| `example-candidate-ci.yml` | a workflow a candidate repository can copy to run the harness against its binary |

## Scenarios and observations

| Scenario | Observed behavior (each line an OBS) |
|---|---|
| `discovery-join-leave` | each side reports the other after enable; reference's peer count returns to 0 after the candidate quits |
| `tempo-follow` | tempo set on either side is adopted by the other |
| `start-stop` | transport start/stop on either side is followed by the other (start/stop sync enabled) |
| `beat-alignment` | skew-compensated phase difference at quantum 4 within 0.3 beats |
| `audio-stream` | each side sees the other's announced channel; subscribed audio arrives in both directions; withdrawing a channel empties the other side's list |

The `audio-stream` scenario runs only when the candidate declares the `audio`
feature (`CANDIDATE_FEATURES=audio`).

## Running

Self-test (reference vs reference — validates the harness itself; this is what
the spec repo's CI runs):

```
sudo conformance/run-isolated.sh
```

Against a candidate:

```
export CANDIDATE_CMD="path/to/candidate --contract"   # speaks CANDIDATE-CONTRACT.md
export CANDIDATE_FEATURES=""                          # or "audio"
sudo conformance/run-isolated.sh
```

Exit code is 0 iff no observation failed. Individual scenarios can be selected
by name: `sudo conformance/run-isolated.sh tempo-follow beat-alignment`.

## Impaired-network runs

`run-isolated.sh` can degrade the namespace's loopback link to probe behavior
at various latencies, loss rates, and throughputs (the operating-envelope facts
in spec chapters 02 §5.1 and 03 §5.8 were measured this way):

```
SHAPE="--delay 200 --jitter 50" sudo --preserve-env=SHAPE,CANDIDATE_CMD,CANDIDATE_FEATURES \
  bash conformance/run-isolated.sh
```

`SHAPE` is passed to `tools/udp-shaper.py` (one-way `--delay`/`--jitter` in ms,
`--loss` in percent, `--rate` in kbit/s), a userspace NFQUEUE shaper that works
on kernels without qdisc modules (`tc netem` unavailable in many containers).
It requires the `NetfilterQueue` pip package and kernel nfnetlink_queue
support. Delay is applied once per packet, so one-way delay = `--delay`,
RTT = 2×.

Interpretation guide: scenario timing assertions assume LAN-like latency.
Run the same `SHAPE` in self-test mode (no `CANDIDATE_CMD`) as a control —
only candidate failures that the reference-vs-reference control does *not*
reproduce indicate a candidate divergence. Expected from the spec's
envelope: all scenarios hold through ≈ 100 ms one-way delay; at ≥ 200 ms
one-way, session merging becomes probabilistic (setup failures) for the
reference itself; ≥ 10 % loss makes merging intermittent; rate limits below
an audio stream's bandwidth starve reverse-direction control traffic.

## Integrating in a candidate repository

Copy `example-candidate-ci.yml` into the candidate repo's workflows after
review. It checks out this spec repository **at a pinned release tag** into the
runner's temp directory (a CI cache, never committed), builds the candidate,
and runs the harness with `CANDIDATE_CMD` pointing at the candidate binary.
The observation log is the job output; the firewall obligation on the
candidate side is to keep it that way — consume observations, never the
reference source that the harness builds in its cache.
