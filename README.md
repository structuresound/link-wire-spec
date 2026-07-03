# link-wire-spec

Independent, facts-only documentation of the wire protocols used by
[Ableton Link](https://github.com/Ableton/link) — peer discovery, tempo/beat
synchronization, and the LinkAudio v1 audio-sharing protocol — written for
interoperability.

The purpose of this repository is to be a **specification good enough to
implement from**: a developer who has never seen the reference implementation
should be able to build a wire-compatible peer using only these documents and
the captured test vectors.

## Why

The reference implementation is C++ under GPLv2+ (with a proprietary license
available from Ableton). The protocol itself — message layouts, constants,
state machines, observable behavior — consists of uncopyrightable facts. This
repository documents those facts so that independent implementations under any
license are possible. The first consumer is
[link-wire-rs](https://github.com/structuresound/link-wire-rs), a clean-room
MIT implementation built exclusively from this spec.

See [PROVENANCE.md](PROVENANCE.md) for the rules that keep that separation
meaningful, including the firewall between spec authors (who read the GPL
source) and implementers (who must not).

## Contents

| Chapter | Scope | Status |
|---|---|---|
| [spec/00-overview.md](spec/00-overview.md) | Terminology, transport model, common serialization rules | v0.4.0 |
| [spec/01-discovery.md](spec/01-discovery.md) | Multicast peer discovery, peer state gossip | v0.4.0 |
| [spec/02-sync.md](spec/02-sync.md) | Timeline, tempo, clock measurement, start/stop sync | v0.4.1 |
| [spec/03-audio.md](spec/03-audio.md) | LinkAudio v1: channels, sinks/sources, audio buffers, beat-time alignment | v0.4.3 |
| [spec/proposals/](spec/proposals/) | Forward-looking design studies (non-normative), e.g. [tactus-native-audio](spec/proposals/tactus-native-audio.md) | draft |
| [vectors/](vectors/) | Captured packet traces (golden test vectors) with auto-generated observed-fact manifests | v0.1.0 (re-validated at v0.4.0) |
| [conformance/](conformance/) | Conformance harness: reference-vs-candidate scenarios emitting pass/fail observations; no protocol logic | v0.1.0 |

Every claim in the spec carries an evidence class (Chapter 0 §1.1): wire-observed
in a vector, behavioral (reference analysis), or normative. Observable facts about
the vectors are generated from the capture bytes
([tools/analyze_pcap.py](tools/analyze_pcap.py)) and structurally asserted
([tools/check_vectors.py](tools/check_vectors.py)), so descriptions cannot drift
from what the captures contain.

## Versioning and upstream tracking

Every spec release pins the upstream commit it documents. The current pin is
in [LAST_REVIEWED_SHA](LAST_REVIEWED_SHA). A scheduled workflow
([upstream-watch](.github/workflows/upstream-watch.yml)) compares
`Ableton/link` HEAD against the pin weekly: commits that do not touch
wire-relevant paths advance the pin automatically; commits that do open a
triage issue. Triage classifies each change (no wire impact / behavioral /
wire-format), updates the affected chapter, regenerates test vectors when
needed, and bumps the spec version. The spec's CHANGELOG records the verdict
for every reviewed upstream commit, so any spec version answers the question
*"which upstream state does this describe?"*

Conformance is verified empirically, not just editorially: the implementation
repository runs interop tests against reference peers built from both the
pinned SHA (regression) and upstream HEAD (canary). A canary failure is
treated as protocol drift even if triage saw nothing.

## License

Specification text: [CC-BY-4.0](LICENSE). Captured packet traces in
`vectors/` are uncopyrightable protocol facts; to avoid any doubt they are
dedicated to the public domain (CC0).

## Affiliation

This project is not affiliated with, endorsed by, or sponsored by Ableton AG.
"Ableton", "Link", and "Ableton Link" are trademarks of Ableton AG, used here
only to identify the protocol being described. This repository contains no
code or text from the reference implementation.
