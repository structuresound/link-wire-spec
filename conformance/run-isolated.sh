#!/usr/bin/env bash
# run-isolated.sh — run the conformance harness inside an isolated network
# namespace (loopback only), after building the pinned reference outside the
# repository. Starts a dummy-backend JACK server for the audio scenarios when
# jackd is available.
#
# Usage: conformance/run-isolated.sh [scenario ...]
#   (scenarios as listed by conformance/run.py; default: all)
#
# Env passthrough: CANDIDATE_CMD, CANDIDATE_AUDIO_CMD, CANDIDATE_FEATURES —
# see conformance/README.md. Requires root (netns + reference build deps).
#
# Optional: SHAPE="--delay 50 --jitter 10 [--loss 2] [--rate 512]" applies
# network impairment to all UDP inside the namespace via tools/udp-shaper.py
# (see "Impaired-network runs" in conformance/README.md).
# License: MIT

set -euo pipefail
export PATH="$PATH:/usr/sbin:/sbin"

REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

if [ "${1:-}" != "--inner" ]; then
  REFERENCE_BIN_DIR=$("$REPO_DIR/tools/build-reference.sh")
  export REFERENCE_BIN_DIR
  exec unshare --net "$BASH" "$0" --inner "$@"
fi
shift # --inner

ip link set lo up

JACK_PID=""
SHAPER_PID=""
cleanup() {
  [ -n "$JACK_PID" ] && kill "$JACK_PID" 2>/dev/null || true
  [ -n "$SHAPER_PID" ] && kill "$SHAPER_PID" 2>/dev/null || true
}
trap cleanup EXIT

if [ -n "${SHAPE:-}" ]; then
  iptables -A OUTPUT -o lo -p udp -j NFQUEUE --queue-num 1 --queue-bypass
  # shellcheck disable=SC2086
  python3 "$REPO_DIR/tools/udp-shaper.py" $SHAPE \
    >/tmp/conformance-shaper.log 2>&1 &
  SHAPER_PID=$!
  sleep 1
  echo "[conformance] shaping UDP: $SHAPE" >&2
fi

if command -v jackd >/dev/null; then
  JACK_NO_AUDIO_RESERVATION=1 jackd -r -d dummy -r 48000 -p 256 \
    >/tmp/conformance-jackd.log 2>&1 &
  JACK_PID=$!
  sleep 2
  export CONFORMANCE_AUDIO=1
else
  echo "[conformance] jackd not found: audio scenarios will be skipped" >&2
  export CONFORMANCE_AUDIO=0
fi

# No exec: the EXIT trap must fire afterwards to reap jackd and the shaper.
python3 "$REPO_DIR/conformance/run.py" "$@"
