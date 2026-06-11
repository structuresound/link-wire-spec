#!/usr/bin/env bash
# capture-vectors.sh — build the pinned Ableton Link reference implementation
# and record protocol test vectors (vectors/*.pcap) by running scripted
# scenarios between reference peers.
#
# Each scenario runs inside an isolated network namespace so the topology is
# controlled and documented, not inherited from the host: the default
# environment is loopback-only (every peer has exactly one gateway), and the
# multi-gateway scenario adds a second interface deliberately. After capture,
# tools/analyze_pcap.py generates an observed-fact manifest per vector and
# tools/check_vectors.py asserts each capture structurally contains the
# events its scenario exists to demonstrate — a silently failed scenario
# fails the run instead of shipping a hollow vector.
#
# The reference source is cloned OUTSIDE the repository (default: /tmp) and
# is never vendored or redistributed; only packet captures of its runtime
# behavior are stored. See PROVENANCE.md.
#
# Requirements: git, cmake, g++, tcpdump, iproute2, unshare (util-linux),
# python3, jackd (dummy backend) + libjack-dev. Run as root (or with
# CAP_NET_ADMIN + CAP_NET_RAW).
#
# Usage: tools/capture-vectors.sh [scenario ...]
#   scenarios: discovery-join-leave sync-tempo-change sync-start-stop
#              audio-channel-lifecycle multi-gateway-discovery
#              discovery-ipv6                          (default: all)
#
# License: MIT

set -euo pipefail
trap '' PIPE # writing to a peer that already quit must not kill the script
export PATH="$PATH:/usr/sbin:/sbin"

REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PIN=$(tr -d '[:space:]' <"$REPO_DIR/LAST_REVIEWED_SHA")
WORK=${LINK_CAPTURE_WORK:-/tmp/link-wire-capture}
SRC="$WORK/link"
BIN="$SRC/build/bin"
OUT=${LINK_CAPTURE_OUT:-$REPO_DIR/vectors}
UPSTREAM_URL=${LINK_UPSTREAM_URL:-https://github.com/Ableton/link.git}

log() { echo "[capture] $*" >&2; }

# ---------------------------------------------------------------- build

build_reference() {
  BIN=$(LINK_CAPTURE_WORK="$WORK" LINK_UPSTREAM_URL="$UPSTREAM_URL" \
    "$REPO_DIR/tools/build-reference.sh")
}

# ---------------------------------------------------------------- peers

# Peers are driven through named pipes; each key press is one byte on the
# pipe (the huts read unbuffered single characters; channel selection reads
# one full line).
declare -A PEER_FD PEER_PID
TCPDUMP_PID=""
JACK_PID=""

cleanup() {
  local pid
  for pid in "${PEER_PID[@]:-}" "${TCPDUMP_PID:-}" "${JACK_PID:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

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

start_capture() { # start_capture FILE [IFACE [FILTER]]
  local file=$1 iface=${2:-lo} filter=${3:-udp}
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

start_jack() {
  JACK_NO_AUDIO_RESERVATION=1 jackd -r -d dummy -r 48000 -p 256 \
    >"$WORK/jackd.log" 2>&1 &
  JACK_PID=$!
  sleep 2
}

stop_jack() {
  kill "$JACK_PID" 2>/dev/null || true
  wait "$JACK_PID" 2>/dev/null || true
  JACK_PID=""
}

# ---------------------------------------------------------------- scenarios
# All scenario functions run INSIDE an isolated network namespace with lo up
# (see inner_main). Default topology: loopback only -> one gateway per peer.

# Two plain Link peers. B joins 3 s after A, leaves first (its ByeBye is on
# the wire); A then re-founds a session alone (observable as a fresh NodeId)
# and keeps announcing.
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
# channel request + its 5 s keepalive repetitions, audio streaming including
# a mid-stream tempo change, stop-request, channel byes.
scenario_audio_channel_lifecycle() {
  if ! command -v jackd >/dev/null; then
    log "SKIP audio-channel-lifecycle: jackd not installed"
    return
  fi
  start_jack
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
  sleep 6 # stream; first request keepalive at +5 s
  send alice e # tempo change while streaming (new tempo in chunks)
  sleep 5 # stream at new tempo; second keepalive at +10 s
  send bob o # Bob removes the source: StopChannelRequest
  sleep 1
  send alice c # Alice disables LinkAudio: ChannelByes
  sleep 1
  quit_all
  stop_capture
  stop_jack
}

# Two peers, each running on TWO gateways: loopback plus a second interface
# added inside the namespace. Shows per-gateway announcement (each NodeId
# transmits from both source addresses, each advertising a gateway-specific
# measurement endpoint).
scenario_multi_gateway_discovery() {
  # veth pair: bringing both ends up gives gw1 carrier (IFF_RUNNING), which
  # the reference's interface scanner requires
  ip link add gw1 type veth peer name gw1p 2>/dev/null \
    || { log "SKIP multi-gateway-discovery: cannot create veth interface"; return; }
  ip addr add 192.168.77.1/24 dev gw1
  ip link set gw1 up
  ip link set gw1p up
  start_capture "$OUT/multi-gateway-discovery.pcap" any
  spawn a "$BIN/LinkHutSilent"
  spawn b "$BIN/LinkHutSilent"
  sleep 0.5
  send a a
  send b a
  sleep 6
  quit_all
  stop_capture
  ip link delete gw1 2>/dev/null || true
}

# IPv6 variant of discovery: requires kernel IPv6 plus an interface with
# both an IPv4 and a link-local IPv6 address (the reference only uses
# link-local v6, and only on interfaces that also run v4). Skipped when
# unavailable.
scenario_discovery_ipv6() {
  if [ ! -e /proc/net/if_inet6 ]; then
    log "SKIP discovery-ipv6: kernel IPv6 not available"
    return
  fi
  ip link add gw6 type veth peer name gw6p 2>/dev/null \
    || { log "SKIP discovery-ipv6: cannot create veth interface"; return; }
  ip addr add 192.168.78.1/24 dev gw6
  ip link set gw6 up
  ip link set gw6p up
  sleep 1 # let the kernel assign the link-local v6 address
  if ! ip -6 addr show dev gw6 scope link | grep -q fe80; then
    log "SKIP discovery-ipv6: no link-local IPv6 on test interface"
    ip link delete gw6 2>/dev/null || true
    return
  fi
  start_capture "$OUT/discovery-ipv6.pcap" any "ip6 and udp"
  spawn a6 "$BIN/LinkHutSilent"
  spawn b6 "$BIN/LinkHutSilent"
  sleep 0.5
  send a6 a
  send b6 a
  sleep 6
  quit_all
  stop_capture
  ip link delete gw6 2>/dev/null || true
}

# ---------------------------------------------------------------- netns glue

ALL_SCENARIOS=(discovery-join-leave sync-tempo-change sync-start-stop
  audio-channel-lifecycle multi-gateway-discovery discovery-ipv6)

inner_main() { # runs inside `unshare --net`
  local s=$1
  ip link set lo up
  "scenario_${s//-/_}"
}

outer_main() {
  local scenarios=("$@")
  [ ${#scenarios[@]} -eq 0 ] && scenarios=("${ALL_SCENARIOS[@]}")

  mkdir -p "$WORK" "$OUT"
  build_reference

  for s in "${scenarios[@]}"; do
    log "scenario: $s (isolated netns)"
    unshare --net "$BASH" "$0" --inner "$s"
  done

  log "generating observed-fact manifests"
  mkdir -p "$OUT/manifests"
  for f in "$OUT"/*.pcap; do
    [ -e "$f" ] || continue
    python3 "$REPO_DIR/tools/analyze_pcap.py" "$f" \
      >"$OUT/manifests/$(basename "${f%.pcap}").md"
  done

  log "running structural assertions"
  python3 "$REPO_DIR/tools/check_vectors.py" "$OUT"

  log "captures written to $OUT:"
  ls -la "$OUT"/*.pcap >&2 || true
}

if [ "${1:-}" = "--inner" ]; then
  shift
  inner_main "$@"
else
  outer_main "$@"
fi
