#!/usr/bin/env python3
"""hut_adapter.py — drive a reference Link peer (LinkHutSilent / LinkAudioHut)
through the conformance candidate contract (CANDIDATE-CONTRACT.md).

The adapter translates contract commands into the keystrokes the hut binaries
accept, and parses their printed status into contract `status` lines. Both the
key bindings and the status format are the programs' own runtime interface
(printed by their usage text at startup); no protocol logic is involved —
this file never constructs or parses a network message.

Used two ways by the harness:
  - as the driver for reference peers, and
  - as the default stand-in candidate (self-test mode: reference vs reference).

Usage:
  hut_adapter.py --binary PATH [--audio] [--name NAME]

License: MIT
"""
import argparse
import os
import re
import subprocess
import sys
import threading
import time

# Status-line patterns for the huts' periodic state printout (one line per
# refresh, carriage-return separated). Fields per the binaries' own header
# line: LinkHutSilent prints
#   enabled | num peers | quantum | start stop sync | tempo | beats | metro
# and LinkAudioHut prints
#   enabled [au] | num peers | start stop sync | source (buffered)| tempo | beats | metro
RE_PLAIN = re.compile(
    r"^(yes|no)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*(yes|no)\s+\[(playing|stopped)\]"
    r"\s*\|\s*([\d.]+)\s*\|\s*(-?[\d.]+)\s*\|"
)
RE_AUDIO = re.compile(
    r"^(yes|no)\s*\[(yes|no)\]\s*\|\s*(\d+)\s*\|\s*(yes|no)\s+\[(playing|stopped)\]"
    r"\s*\|\s*(yes|no)\s*\(\s*([\d.]+)s\)\|\s*([\d.]+)\s*\|\s*(-?[\d.]+)\s*\|"
)


class HutAdapter:
    def __init__(self, binary, audio=False, name="adapter"):
        self.audio = audio
        argv = [binary] + ([name] if audio else [])
        self.proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0)
        self.lock = threading.Lock()
        # tracked state, parsed from the hut's own printout
        self.state = None  # dict once first status line parsed
        self.channels = 0  # audio mode: channels currently listed by the hut
        self.ready_emitted = False
        self.last_emit = 0.0
        self.awaiting_index_prompt = False
        self.pending_subscribe = None

    # ---- hut input -----------------------------------------------------

    def keys(self, s):
        try:
            self.proc.stdin.write(s.encode())
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass

    # ---- hut output parsing --------------------------------------------

    def pump(self):
        """Read hut stdout, splitting on CR/LF; parse status and channel
        lists; emit contract lines."""
        buf = b""
        channel_block = None
        while True:
            chunk = self.proc.stdout.read(256)
            if not chunk:
                break
            buf += chunk
            while True:
                # split on either line ending; huts refresh with '\r'
                idx_r = buf.find(b"\r")
                idx_n = buf.find(b"\n")
                idx = min(x for x in (idx_r, idx_n) if x >= 0) if (
                    idx_r >= 0 or idx_n >= 0) else -1
                if idx < 0:
                    break
                line = buf[:idx].decode("latin1")
                buf = buf[idx + 1:]
                channel_block = self.handle_line(line.strip(), channel_block)
            # the channel-index prompt has no trailing newline; detect in buf
            if self.pending_subscribe is not None and b"Enter channel index" in buf:
                self.keys(f"{self.pending_subscribe}\n")
                self.pending_subscribe = None
                buf = b""

    def handle_line(self, line, channel_block):
        # channel list block (audio): "LinkAudio Peers:" then "peer | name" rows
        if self.audio:
            if "LinkAudio Peers:" in line or "Select channel index:" in line:
                return []
            if channel_block is not None:
                if " | " in line and not line.startswith("enabled"):
                    channel_block.append(line)
                    return channel_block
                # block ended (blank line or header)
                self.channels = len(channel_block)
                return None

        m = RE_AUDIO.match(line) if self.audio else RE_PLAIN.match(line)
        if m:
            g = m.groups()
            if self.audio:
                st = {"enabled": g[0] == "yes", "audio": g[1] == "yes",
                      "peers": int(g[2]), "quantum": 4.0,
                      "startstop_sync": g[3] == "yes",
                      "playing": g[4] == "playing", "source": g[5] == "yes",
                      "buffered": float(g[6]), "tempo": float(g[7]),
                      "beat": float(g[8])}
            else:
                st = {"enabled": g[0] == "yes", "peers": int(g[1]),
                      "quantum": float(g[2]), "startstop_sync": g[3] == "yes",
                      "playing": g[4] == "playing", "tempo": float(g[5]),
                      "beat": float(g[6])}
            with self.lock:
                self.state = st
            self.emit_status()
        return channel_block

    # ---- contract output ------------------------------------------------

    def emit(self, line):
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def emit_status(self, force=False):
        now = time.monotonic()
        if not self.ready_emitted:
            self.ready_emitted = True
            self.emit("ready")
        if not force and now - self.last_emit < 0.25:
            return
        self.last_emit = now
        st = self.state
        extra = ""
        if self.audio:
            receiving = 1 if (st["source"] and st["buffered"] > 0) else 0
            extra = (f" audio={int(st['audio'])} channels={self.channels}"
                     f" receiving={receiving} publishing={int(st['audio'])}")
        self.emit(
            f"status peers={st['peers']} tempo={st['tempo']:.2f}"
            f" playing={int(st['playing'])} beat={st['beat']:.2f}"
            f" quantum={st['quantum']:g} ts={time.time():.3f}" + extra)

    # ---- contract commands ----------------------------------------------

    def wait_state(self, timeout=5.0):
        t0 = time.monotonic()
        while self.state is None and time.monotonic() - t0 < timeout:
            time.sleep(0.02)
        return self.state

    def command(self, line):
        parts = line.split()
        if not parts:
            return True
        cmd, args = parts[0], parts[1:]
        st = self.wait_state() or {}
        if cmd == "quit":
            self.keys("q")
            return False
        if cmd == "enable":
            if not st.get("enabled"):
                self.keys("a")
        elif cmd == "disable":
            if st.get("enabled"):
                self.keys("a")
        elif cmd == "tempo" and args:
            # the huts step tempo by 1 bpm per keypress
            target = round(float(args[0]))
            current = round(st.get("tempo", 120.0))
            delta = target - current
            self.keys("e" * delta if delta > 0 else "w" * (-delta))
        elif cmd == "start":
            if not st.get("playing"):
                self.keys(" ")
        elif cmd == "stop":
            if st.get("playing"):
                self.keys(" ")
        elif cmd == "startstop-sync" and args:
            want = args[0] == "1"
            if st.get("startstop_sync") != want:
                self.keys("s")
        elif cmd == "audio-enable" and self.audio:
            if not st.get("audio"):
                self.keys("c")
        elif cmd == "audio-disable" and self.audio:
            if st.get("audio"):
                self.keys("c")
        elif cmd == "audio-subscribe" and self.audio and args:
            if not st.get("source"):
                self.pending_subscribe = int(args[0])
                self.keys("o")
        elif cmd == "audio-unsubscribe" and self.audio:
            if st.get("source"):
                self.keys("o")
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--audio", action="store_true")
    ap.add_argument("--name", default="adapter")
    args = ap.parse_args()

    adapter = HutAdapter(args.binary, audio=args.audio, name=args.name)
    t = threading.Thread(target=adapter.pump, daemon=True)
    t.start()

    try:
        for line in sys.stdin:
            if not adapter.command(line.strip()):
                break
    except KeyboardInterrupt:
        adapter.keys("q")
    adapter.proc.wait(timeout=5)


if __name__ == "__main__":
    main()
