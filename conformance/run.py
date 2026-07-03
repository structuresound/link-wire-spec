#!/usr/bin/env python3
"""run.py — Link wire-protocol conformance harness.

Drives a *reference* peer (the pinned upstream implementation, wrapped by
hut_adapter.py) and a *candidate* peer (any program speaking
CANDIDATE-CONTRACT.md) side by side through the same scenarios the spec's
test vectors capture, and emits pass/fail OBSERVATIONS as plain text.

The harness contains no protocol implementation logic: it never constructs,
parses, or inspects a network message. Every assertion is about observable
endpoint behavior — what each peer *reports* about peers, tempo, transport,
and audio reception. This is what keeps the harness (and its results) safe
for the clean-room implementation side to consume; see PROVENANCE.md.

Environment:
  REFERENCE_BIN_DIR   dir containing LinkHutSilent and LinkAudioHut (required)
  CANDIDATE_CMD       shell command for the candidate peer; default: a second
                      reference peer via hut_adapter.py (self-test mode)
  CANDIDATE_AUDIO_CMD shell command for the candidate in audio scenarios;
                      default mirrors CANDIDATE_CMD's self-test behavior
  CANDIDATE_FEATURES  comma list of optional features ("audio");
                      self-test mode defaults to CONFORMANCE_AUDIO=1's value

Output: one line per observation:
  OBS | <scenario> | PASS|FAIL|SKIP | <observed behavior, with measurements>
Exit code 0 iff no FAIL. License: MIT
"""
import os
import shlex
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FAILED = []


def obs(scenario, ok, text):
    verdict = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
    print(f"OBS | {scenario} | {verdict} | {text}", flush=True)
    if ok is False:
        FAILED.append(f"{scenario}: {text}")


class Peer:
    """A peer process speaking the candidate contract on stdin/stdout."""

    def __init__(self, label, argv_or_cmd, shell=False):
        self.label = label
        self.proc = subprocess.Popen(
            argv_or_cmd, shell=shell, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.latest = {}
        self.latest_t = None
        self.ready = threading.Event()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for raw in self.proc.stdout:
            line = raw.decode("latin1").strip()
            if line == "ready":
                self.ready.set()
            elif line.startswith("status "):
                fields = {}
                for tok in line.split()[1:]:
                    if "=" in tok:
                        k, v = tok.split("=", 1)
                        try:
                            fields[k] = float(v) if "." in v else int(v)
                        except ValueError:
                            fields[k] = v
                self.latest = fields
                self.latest_t = time.monotonic()
                self.ready.set()

    def send(self, cmd):
        try:
            self.proc.stdin.write((cmd + "\n").encode())
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass

    def wait(self, pred, timeout):
        """Wait until pred(latest_status) is true. Returns (ok, elapsed)."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            st = self.latest
            if st and pred(st):
                return True, time.monotonic() - t0
            time.sleep(0.05)
        return False, timeout

    def stop(self):
        self.send("quit")
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


# ---------------------------------------------------------------- factories

def reference_cmd(audio=False, name="Ref"):
    bindir = os.environ["REFERENCE_BIN_DIR"]
    base = [sys.executable, os.path.join(HERE, "hut_adapter.py")]
    if audio:
        return base + ["--binary", os.path.join(bindir, "LinkAudioHut"),
                       "--audio", "--name", name]
    return base + ["--binary", os.path.join(bindir, "LinkHutSilent")]


def make_reference(audio=False, name="Ref"):
    p = Peer("reference", reference_cmd(audio, name))
    p.ready.wait(10)
    return p


def make_candidate(audio=False):
    env_key = "CANDIDATE_AUDIO_CMD" if audio else "CANDIDATE_CMD"
    cmd = os.environ.get(env_key) or (not audio and os.environ.get("CANDIDATE_CMD"))
    if audio and not os.environ.get("CANDIDATE_AUDIO_CMD") \
            and not os.environ.get("CANDIDATE_CMD"):
        cmd = None
    if cmd:
        p = Peer("candidate", cmd, shell=True)
    else:
        # self-test mode: the candidate is a second reference peer
        p = Peer("candidate(self-test)",
                 reference_cmd(audio=audio, name="Cand"))
    p.ready.wait(10)
    return p


def candidate_features():
    feats = os.environ.get("CANDIDATE_FEATURES")
    if feats is None and not os.environ.get("CANDIDATE_CMD"):
        # self-test: audio capability is decided by the wrapper (jackd present)
        feats = "audio" if os.environ.get("CONFORMANCE_AUDIO") == "1" else ""
    return {f.strip() for f in (feats or "").split(",") if f.strip()}


# ---------------------------------------------------------------- scenarios

def scenario_discovery_join_leave():
    s = "discovery-join-leave"
    ref, cand = make_reference(), make_candidate()
    try:
        ref.send("enable")
        ok, _ = ref.wait(lambda st: True, 5)
        cand.send("enable")
        ok, dt = ref.wait(lambda st: st.get("peers", 0) >= 1, 8)
        obs(s, ok, f"reference reported >=1 peer {dt:.1f}s after candidate enable")
        ok, dt = cand.wait(lambda st: st.get("peers", 0) >= 1, 8)
        obs(s, ok, f"candidate reported >=1 peer {dt:.1f}s after its enable")
        cand.stop()
        ok, dt = ref.wait(lambda st: st.get("peers", 1) == 0, 10)
        obs(s, ok, f"reference peer count returned to 0 {dt:.1f}s after candidate quit"
                   " (departure announcement or timeout)")
    finally:
        ref.stop()
        cand.stop()


def join(ref, cand, s):
    ref.send("enable")
    cand.send("enable")
    ok1, _ = ref.wait(lambda st: st.get("peers", 0) >= 1, 8)
    ok2, _ = cand.wait(lambda st: st.get("peers", 0) >= 1, 8)
    if not (ok1 and ok2):
        obs(s, False, "peers failed to join a common session (setup)")
        return False
    return True


def scenario_tempo_follow():
    s = "tempo-follow"
    ref, cand = make_reference(), make_candidate()
    try:
        if not join(ref, cand, s):
            return
        # Tempo deltas stay small (<= 6 bpm per change): a reference hut is
        # driven by single-bpm keypresses that it consumes at only a few
        # per second, so the time window covers stepping + adoption.
        cand.send("tempo 116")
        ok, dt = ref.wait(lambda st: abs(st.get("tempo", 0) - 116.0) < 0.01, 8)
        obs(s, ok, f"reference adopted candidate's tempo 116 bpm in {dt:.1f}s"
                   f" (reference reports {ref.latest.get('tempo')})")
        ref.send("tempo 121")
        ok, dt = cand.wait(lambda st: abs(st.get("tempo", 0) - 121.0) < 0.01, 8)
        obs(s, ok, f"candidate adopted reference's tempo 121 bpm in {dt:.1f}s"
                   f" (candidate reports {cand.latest.get('tempo')})")
    finally:
        ref.stop()
        cand.stop()


def scenario_start_stop():
    s = "start-stop"
    ref, cand = make_reference(), make_candidate()
    try:
        if not join(ref, cand, s):
            return
        ref.send("startstop-sync 1")
        cand.send("startstop-sync 1")
        time.sleep(1)
        cand.send("start")
        ok, dt = ref.wait(lambda st: st.get("playing") == 1, 5)
        obs(s, ok, f"reference started playing {dt:.1f}s after candidate start")
        cand.send("stop")
        ok, dt = ref.wait(lambda st: st.get("playing") == 0, 5)
        obs(s, ok, f"reference stopped {dt:.1f}s after candidate stop")
        ref.send("start")
        ok, dt = cand.wait(lambda st: st.get("playing") == 1, 5)
        obs(s, ok, f"candidate started playing {dt:.1f}s after reference start")
    finally:
        ref.stop()
        cand.stop()


def scenario_beat_alignment():
    s = "beat-alignment"
    ref, cand = make_reference(), make_candidate()
    try:
        if not join(ref, cand, s):
            return
        time.sleep(2)  # settle
        q = 4.0
        samples = []
        for _ in range(6):
            st1, t1 = ref.latest, ref.latest_t
            st2, t2 = cand.latest, cand.latest_t
            if not (st1 and st2 and "beat" in st1 and "beat" in st2):
                time.sleep(0.5)
                continue
            tempo = st1.get("tempo", 120.0)
            # compensate the candidate's beat for the sampling-time skew
            b2 = st2["beat"] + (t1 - t2) * tempo / 60.0
            diff = (st1["beat"] - b2) % q
            if diff > q / 2:
                diff -= q
            samples.append(abs(diff))
            time.sleep(0.5)
        if not samples:
            obs(s, False, "no concurrent beat reports from both peers")
            return
        best = min(samples)
        obs(s, best <= 0.3,
            f"phase difference at quantum {q:g}: best {best:.3f} beats over "
            f"{len(samples)} samples (tolerance 0.3)")
    finally:
        ref.stop()
        cand.stop()


def scenario_audio_stream():
    s = "audio-stream"
    if "audio" not in candidate_features():
        obs(s, None, "candidate does not declare the audio feature")
        return
    ref, cand = make_reference(audio=True, name="RefPub"), make_candidate(audio=True)
    try:
        if not join(ref, cand, s):
            return
        ref.send("audio-enable")
        cand.send("audio-enable")
        ok, dt = cand.wait(lambda st: st.get("channels", 0) >= 1, 8)
        obs(s, ok, f"candidate saw the reference's announced channel in {dt:.1f}s")
        ok2, dt = ref.wait(lambda st: st.get("channels", 0) >= 1, 8)
        obs(s, ok2, f"reference saw the candidate's announced channel in {dt:.1f}s")
        if ok:
            cand.send("audio-subscribe 0")
            okr, dt = cand.wait(lambda st: st.get("receiving") == 1, 12)
            obs(s, okr, f"candidate received streamed audio {dt:.1f}s after subscribing")
            cand.send("audio-unsubscribe")
        if ok2:
            ref.send("audio-subscribe 0")
            okr, dt = ref.wait(lambda st: st.get("receiving") == 1, 12)
            obs(s, okr, f"reference received streamed audio {dt:.1f}s after "
                        "subscribing to the candidate's channel")
            ref.send("audio-unsubscribe")
        cand.send("audio-disable")
        ok, dt = ref.wait(lambda st: st.get("channels", 1) == 0, 8)
        obs(s, ok, f"reference's channel list emptied {dt:.1f}s after candidate "
                   "withdrew (channel byes)")
    finally:
        ref.stop()
        cand.stop()


SCENARIOS = [
    scenario_discovery_join_leave,
    scenario_tempo_follow,
    scenario_start_stop,
    scenario_beat_alignment,
    scenario_audio_stream,
]


def main():
    if "REFERENCE_BIN_DIR" not in os.environ:
        print("REFERENCE_BIN_DIR not set (see conformance/README.md)", file=sys.stderr)
        return 2
    wanted = sys.argv[1:]
    for fn in SCENARIOS:
        name = fn.__name__.replace("scenario_", "").replace("_", "-")
        if wanted and name not in wanted:
            continue
        fn()
    if FAILED:
        print(f"\n{len(FAILED)} observation(s) FAILED:", file=sys.stderr)
        for f in FAILED:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nall observations passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
