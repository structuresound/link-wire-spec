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
cleanup() { [ -n "$JACK_PID" ] && kill "$JACK_PID" 2>/dev/null || true; }
trap cleanup EXIT

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

exec python3 "$REPO_DIR/conformance/run.py" "$@"
