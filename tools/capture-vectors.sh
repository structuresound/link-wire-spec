#!/usr/bin/env bash
# capture-vectors.sh — build the pinned Ableton Link reference implementation
# and record protocol test vectors (vectors/*.pcap) by running scripted
# loopback scenarios between reference peers.
#
# The reference source is cloned OUTSIDE the repository (default: /tmp) and is
# never vendored or redistributed; only packet captures of its runtime
# behavior are stored. See PROVENANCE.md.
#
# Requirements: git, cmake, g++, tcpdump, jackd (dummy backend) + libjack-dev.
# Must run as root or with CAP_NET_RAW/CAP_NET_ADMIN for tcpdump on loopback.
#
# Usage: tools/capture-vectors.sh [scenario ...]
#   scenarios: discovery-join-leave sync-tempo-change sync-start-stop
#              audio-channel-lifecycle discovery-ipv6   (default: all)
#
# License: MIT

set -euo pipefail
trap '' PIPE # writing to a peer that already quit must not kill the script

# Never leave reference peers or a tcpdump behind: a stray capture process
# writing into the same output file corrupts the vector.
cleanup() {
  local pid
  for pid in "${PEER_PID[@]:-}" "${TCPDUMP_PID:-}" "${JACK_PID:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PIN=$(tr -d '[:space:]' <"$REPO_DIR/LAST_REVIEWED_SHA")
WORK=${LINK_CAPTURE_WORK:-/tmp/link-wire-capture}
SRC="$WORK/link"
BIN="$SRC/build/bin"
OUT=${LINK_CAPTURE_OUT:-$REPO_DIR/vectors}
UPSTREAM_URL=${LINK_UPSTREAM_URL:-https://github.com/Ableton/link.git}

mkdir -p "$WORK" "$OUT"

log() { echo "[capture] $*" >&2; }

# ---------------------------------------------------------------- build

build_reference() {
  if [ ! -x "$BIN/LinkHutSilent" ] || [ ! -x "$BIN/LinkAudioHut" ]; then
    log "cloning reference at $PIN"
    if [ ! -d "$SRC/.git" ]; then
      git clone "$UPSTREAM_URL" "$SRC"
    fi
    git -C "$SRC" fetch origin "$PIN" || true
    git -C "$SRC" checkout --force "$PIN"
    git -C "$SRC" submodule update --init --recursive
    log "building LinkHutSilent + LinkAudioHut (JACK audio platform)"
    cmake -S "$SRC" -B "$SRC/build" -DCMAKE_BUILD_TYPE=Release \
      -DLINK_BUILD_JACK=ON -DLINK_BUILD_TESTS=OFF >/dev/null
    cmake --build "$SRC/build" --target LinkHutSilent LinkAudioHut \
      -j"$(nproc)" >/dev/null
  fi
  log "reference binaries ready: $BIN"
}

# ---------------------------------------------------------------- peers

# Peers are driven through named pipes; each key press is one byte on the
# pipe (the huts read unbuffered single characters; channel selection reads
# one full line).
declare -A PEER_FD PEER_PID

spawn() { # spawn NAME BINARY [ARGS...]
  local name=$1 binary=$2
  shift 2
  local fifo="$WORK/$name.in"
  rm -f "$fifo"
  mkfifo "$fifo"
  "$binary" "$@" <"$fifo" >"$WORK/$name.log" 2>&1 &
  PEER_PID[$name]=$!
  exec {fd}>"$fifo"
  PEER_FD[$name]=$fd
}

send() { # send NAME STRING
  printf '%s' "$2" >&"${PEER_FD[$1]}" 2>/dev/null || true
}

quit_all() {
  local name fd
  for name in "${!PEER_FD[@]}"; do
    if kill -0 "${PEER_PID[$name]}" 2>/dev/null; then
      send "$name" q
    fi
  done
  for name in "${!PEER_PID[@]}"; do
    wait "${PEER_PID[$name]}" 2>/dev/null || true
    fd=${PEER_FD[$name]}
    eval "exec $fd>&-" 2>/dev/null || true
  done
  PEER_FD=()
  PEER_PID=()
}

# ---------------------------------------------------------------- capture

TCPDUMP_PID=""

start_capture() { # start_capture FILE [IFACE [FILTER]]
  local file=$1 iface=${2:-lo} filter=${3:-"udp and not port 53 and not port 5353"}
  tcpdump -i "$iface" -w "$file" -U $filter >/dev/null 2>&1 &
  TCPDUMP_PID=$!
  sleep 1
}

stop_capture() {
  sleep 1
  kill "$TCPDUMP_PID" 2>/dev/null || true
  wait "$TCPDUMP_PID" 2>/dev/null || true
  TCPDUMP_PID=""
}

# ---------------------------------------------------------------- scenarios

# Two plain Link peers on loopback. B joins 3 s after A, leaves first (its
# ByeBye is on the wire), A keeps announcing alone afterwards.
scenario_discovery_join_leave() {
  start_capture "$OUT/discovery-join-leave.pcap"
  spawn a "$BIN/LinkHutSilent"
  sleep 0.5
  send a a # enable Link
  sleep 3
  spawn b "$BIN/LinkHutSilent"
  sleep 0.5
  send b a # enable Link: discovery, measurement, session merge
  sleep 4
  send b q # quit: ByeBye
  wait "${PEER_PID[b]}" 2>/dev/null || true
  sleep 2
  quit_all
  stop_capture
}

# Two synced peers; each changes tempo (one key = 1 bpm) while the other
# follows. Shows tmln entries with increasing beatOrigin priority stamps.
scenario_sync_tempo_change() {
  start_capture "$OUT/sync-tempo-change.pcap"
  spawn a "$BIN/LinkHutSilent"
  spawn b "$BIN/LinkHutSilent"
  sleep 0.5
  send a a
  send b a
  sleep 3 # discover + measure + settle at 120 bpm
  send a eeee # a: 120 -> 124 bpm
  sleep 2
  send b ww # b: 124 -> 122 bpm
  sleep 2
  quit_all
  stop_capture
}

# Two peers with start/stop sync enabled; transport started then stopped on
# one of them. Shows stst entries with ghost-time ordering timestamps.
scenario_sync_start_stop() {
  start_capture "$OUT/sync-start-stop.pcap"
  spawn a "$BIN/LinkHutSilent"
  spawn b "$BIN/LinkHutSilent"
  sleep 0.5
  send a a
  send b a
  sleep 3
  send a s # enable start/stop sync
  send b s
  sleep 1
  send a ' ' # start transport
  sleep 3
  send a ' ' # stop transport
  sleep 2
  quit_all
  stop_capture
}

# Two LinkAudio peers (JACK dummy backend): audio endpoints advertised in
# discovery, unicast PeerAnnouncements with channel lists and ping/pong,
# channel request, audio streaming, stop-request, channel byes.
scenario_audio_channel_lifecycle() {
  if ! command -v jackd >/dev/null; then
    log "SKIP audio-channel-lifecycle: jackd not installed"
    return
  fi
  JACK_NO_AUDIO_RESERVATION=1 jackd -r -d dummy -r 48000 -p 256 \
    >"$WORK/jackd.log" 2>&1 &
  JACK_PID=$!
  sleep 2

  start_capture "$OUT/audio-channel-lifecycle.pcap"
  spawn alice "$BIN/LinkAudioHut" Alice
  spawn bob "$BIN/LinkAudioHut" Bob
  sleep 1
  send alice a
  send bob a
  sleep 3 # Link session established
  send alice c # Alice publishes her sink channel
  send bob c # Bob announces too (audio endpoints both ways)
  sleep 3 # announcements + pings/pongs flow
  send alice ' ' # transport start: audible metronome in the stream
  sleep 1
  send bob o # Bob: create source...
  sleep 0.5
  send bob $'0\n' # ...for channel index 0 (Alice | A Sink)
  sleep 4 # ChannelRequest + AudioBuffer stream
  send bob o # Bob removes the source: StopChannelRequest
  sleep 1
  send alice c # Alice disables LinkAudio: ChannelByes
  sleep 1
  quit_all
  stop_capture

  kill "$JACK_PID" 2>/dev/null || true
  wait "$JACK_PID" 2>/dev/null || true
  JACK_PID=""
}

# IPv6 variant of discovery: requires a non-loopback interface with both an
# IPv4 and a link-local IPv6 address (the reference only uses link-local v6,
# and only on interfaces that also run v4). Skipped when unavailable.
scenario_discovery_ipv6() {
  local iface=""
  local candidate
  for candidate in $(ls /sys/class/net 2>/dev/null); do
    [ "$candidate" = lo ] && continue
    if ip -6 addr show dev "$candidate" scope link 2>/dev/null | grep -q fe80 \
      && ip -4 addr show dev "$candidate" 2>/dev/null | grep -q inet; then
      iface=$candidate
      break
    fi
  done
  if [ -z "$iface" ]; then
    log "SKIP discovery-ipv6: no interface with IPv4 + link-local IPv6"
    return
  fi
  start_capture "$OUT/discovery-ipv6.pcap" "$iface" "ip6 and udp"
  spawn a6 "$BIN/LinkHutSilent"
  spawn b6 "$BIN/LinkHutSilent"
  sleep 0.5
  send a6 a
  send b6 a
  sleep 5
  quit_all
  stop_capture
}

# ---------------------------------------------------------------- main

SCENARIOS=("$@")
if [ ${#SCENARIOS[@]} -eq 0 ]; then
  SCENARIOS=(discovery-join-leave sync-tempo-change sync-start-stop
    audio-channel-lifecycle discovery-ipv6)
fi

build_reference
for s in "${SCENARIOS[@]}"; do
  log "scenario: $s"
  "scenario_${s//-/_}"
done

log "captures written to $OUT:"
ls -la "$OUT"/*.pcap >&2 || true
