#!/usr/bin/env bash
# build-reference.sh — clone and build the pinned Ableton Link reference
# implementation OUTSIDE the repository (never vendored; see PROVENANCE.md).
# Shared by the capture rig (tools/capture-vectors.sh) and the conformance
# harness (conformance/).
#
# Env:
#   LINK_CAPTURE_WORK  work dir for the clone/build (default /tmp/link-wire-capture)
#   LINK_UPSTREAM_URL  upstream git URL (default github.com/Ableton/link)
#
# Prints the binary directory on stdout. License: MIT

set -euo pipefail

REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PIN=$(tr -d '[:space:]' <"$REPO_DIR/LAST_REVIEWED_SHA")
WORK=${LINK_CAPTURE_WORK:-/tmp/link-wire-capture}
SRC="$WORK/link"
BIN="$SRC/build/bin"
UPSTREAM_URL=${LINK_UPSTREAM_URL:-https://github.com/Ableton/link.git}

if [ ! -x "$BIN/LinkHutSilent" ] || [ ! -x "$BIN/LinkAudioHut" ]; then
  echo "[build-reference] cloning reference at $PIN" >&2
  mkdir -p "$WORK"
  if [ ! -d "$SRC/.git" ]; then
    git clone "$UPSTREAM_URL" "$SRC" >&2
  fi
  git -C "$SRC" fetch origin "$PIN" >&2 || true
  git -C "$SRC" checkout --force "$PIN" >&2
  git -C "$SRC" submodule update --init --recursive >&2
  echo "[build-reference] building LinkHutSilent + LinkAudioHut (JACK audio platform)" >&2
  cmake -S "$SRC" -B "$SRC/build" -DCMAKE_BUILD_TYPE=Release \
    -DLINK_BUILD_JACK=ON -DLINK_BUILD_TESTS=OFF >/dev/null
  cmake --build "$SRC/build" --target LinkHutSilent LinkAudioHut \
    -j"$(nproc)" >/dev/null
fi
echo "[build-reference] binaries ready: $BIN" >&2
echo "$BIN"
