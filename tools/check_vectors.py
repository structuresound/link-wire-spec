#!/usr/bin/env python3
"""check_vectors.py — structural assertions on captured test vectors.

A capture is only a valid vector if it actually demonstrates what its scenario
claims. This checker decodes each pcap (via analyze_pcap) and asserts the
presence and shape of the protocol events the scenario exists to show; a
scenario that silently failed (peer never joined, subscription never made)
fails here instead of shipping a hollow vector.

Assertions are structural — message types, entry shapes, field invariants —
never identifier values or timing, which vary per run.

Usage: check_vectors.py [VECTORS_DIR]      (default: repo's vectors/)
Exit nonzero on any failure. License: MIT
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_pcap import build_manifest  # noqa: E402

FAILURES = []


def check(name, cond, desc):
    status = "ok" if cond else "FAIL"
    print(f"  [{status}] {desc}")
    if not cond:
        FAILURES.append(f"{name}: {desc}")


def counts(man):
    return man["message_type_counts"]


def single_gateway(man):
    return set(man["gateways_per_peer"].values()) <= {1}


def check_discovery_join_leave(man):
    c = counts(man)
    check("join-leave", c.get("discovery/Alive", 0) >= 20, "Alive messages present (>=20)")
    check("join-leave", c.get("discovery/Response", 0) >= 1, "unicast Response present")
    check("join-leave", c.get("discovery/ByeBye", 0) >= 1, "ByeBye present")
    check("join-leave", c.get("sync/Ping", 0) >= 50 and c.get("sync/Pong", 0) >= 50,
          "measurement ping/pong chain present (>=50 each)")
    shapes = {tuple(s["entry_keys"]) for s in man["discovery_peerstate"]}
    check("join-leave", ("tmln", "sess", "stst", "mep4") in shapes,
          "peer-state entries tmln,sess,stst,mep4 observed")
    sizes = {z for s in man["discovery_peerstate"] for z in s["datagram_sizes"]}
    check("join-leave", 107 in sizes, "107-byte plain peer-state datagram observed")
    ping_shapes = {tuple(s["shape"]) for s in man["sync_messages"]}
    check("join-leave", ("Ping", "__ht") in ping_shapes, "initial Ping {__ht} observed")
    check("join-leave", ("Ping", "__ht", "_pgt") in ping_shapes,
          "steady-state Ping {__ht,_pgt} observed")
    check("join-leave", ("Pong", "sess", "__gt", "__ht", "_pgt") in ping_shapes,
          "Pong {sess,__gt} + echoed {__ht,_pgt} observed")
    check("join-leave", single_gateway(man), "every peer on exactly one gateway")


def check_sync_tempo_change(man):
    t = man["discovery_tmln"]
    check("tempo", len(t["distinct_tempos_us_per_beat"]) >= 3,
          f"≥3 distinct tempos gossiped (saw {t['distinct_tempos_us_per_beat']})")
    check("tempo", t["beatOrigin_max_ubeats"] > t["beatOrigin_min_ubeats"],
          "beatOrigin increased across timeline changes")
    check("tempo", single_gateway(man), "every peer on exactly one gateway")


def check_sync_start_stop(man):
    s = man["discovery_stst"]
    check("startstop", set(s["isPlaying_values_seen"]) >= {0, 1},
          f"both playing and stopped states gossiped (saw {s['isPlaying_values_seen']})")
    check("startstop", s["distinct_states"] >= 3,
          "≥3 distinct (isPlaying, timestamp) states (initial, start, stop)")
    check("startstop", single_gateway(man), "every peer on exactly one gateway")


def check_audio_channel_lifecycle(man):
    c = counts(man)
    shapes = {tuple(s["entry_keys"]) for s in man["discovery_peerstate"]}
    check("audio", any("aep4" in s for s in shapes),
          "audio endpoint (aep4) advertised in discovery")
    check("audio", c.get("audio/PeerAnnouncement", 0) >= 10, "PeerAnnouncements present")
    check("audio", c.get("audio/Pong", 0) >= 10, "audio Pongs present")
    check("audio", c.get("audio/ChannelRequest", 0) >= 2,
          "ChannelRequest re-sent (keepalive by repetition, >=2)")
    check("audio", c.get("audio/StopChannelRequest", 0) >= 1, "StopChannelRequest present")
    check("audio", c.get("audio/ChannelByes", 0) >= 1, "ChannelByes present")
    ab = man["audio_buffer"]
    check("audio", ab["count"] >= 100, f"AudioBuffer stream present ({ab['count']})")
    check("audio", ab["abu_prefix_ever_present"] is False,
          "no _abu wrapper before AudioBuffer structure")
    check("audio", ab["codecs"] == [1], f"codec PCM i16 only (saw {ab['codecs']})")
    check("audio", ab["numBytes_always_matches_remaining"],
          "numBytes always equals trailing sample bytes")
    check("audio", len(ab["tempo_values_us_per_beat"]) >= 2,
          f"≥2 chunk tempos (mid-stream tempo change; saw "
          f"{ab['tempo_values_us_per_beat']})")
    check("audio", man["audio_groupIds"] == [0], "groupId always 0")
    check("audio", len(man["audio_channels_announced"]) >= 1, "channel announced via auca")
    check("audio", single_gateway(man), "every peer on exactly one gateway")


def check_multi_gateway_discovery(man):
    gw = man["gateways_per_peer"]
    check("multigw", any(v >= 2 for v in gw.values()),
          f"at least one peer announces from 2+ gateways (saw {gw})")
    shapes = {tuple(s["entry_keys"]) for s in man["discovery_peerstate"]}
    check("multigw", ("tmln", "sess", "stst", "mep4") in shapes,
          "peer-state entries present on multi-gateway capture")


CHECKS = {
    "discovery-join-leave.pcap": check_discovery_join_leave,
    "sync-tempo-change.pcap": check_sync_tempo_change,
    "sync-start-stop.pcap": check_sync_start_stop,
    "audio-channel-lifecycle.pcap": check_audio_channel_lifecycle,
    "multi-gateway-discovery.pcap": check_multi_gateway_discovery,
}


def main():
    vdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vectors")
    seen = 0
    for fname, fn in CHECKS.items():
        path = os.path.join(vdir, fname)
        if not os.path.exists(path):
            print(f"{fname}: not present, skipping")
            continue
        seen += 1
        print(f"{fname}:")
        man, _ = build_manifest(path)
        fn(man)
    if seen == 0:
        print("no vectors found", file=sys.stderr)
        return 1
    if FAILURES:
        print(f"\n{len(FAILURES)} assertion(s) failed:", file=sys.stderr)
        for f in FAILURES:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"\nall structural assertions passed across {seen} vector(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
