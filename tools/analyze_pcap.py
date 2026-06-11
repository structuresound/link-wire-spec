#!/usr/bin/env python3
"""analyze_pcap.py — decode Ableton Link wire protocols from a capture and
emit an auto-derived manifest of OBSERVED facts.

This tool exists to enforce one rule: every observable claim in the spec and
the vector docs is generated from the bytes of a capture, never narrated from
intent. It decodes the three protocol families by frame magic, dumps every
field, and summarizes what a capture actually contains (topology, message-type
counts, sizes, payload-entry sets, audio-buffer parameters).

It reads only packet bytes — no reference source is involved. Output is safe to
quote in released artifacts (it contains no reference file/class/symbol names).

Usage:
  analyze_pcap.py CAPTURE.pcap [--manifest] [--dump TYPE] [--json]
    (default)     human-readable manifest of observed facts
    --dump all    per-message field decode (all protocols)
    --dump audio  per-message field decode (one protocol family)
    --json        machine-readable manifest

License: MIT
"""
import sys
import struct
import json
import argparse
from collections import Counter, defaultdict

# ---- pcap container ---------------------------------------------------------

LINKTYPES = {0: "NULL/BSD-loopback", 1: "EN10MB", 113: "LINUX_SLL", 276: "LINUX_SLL2"}


def read_pcap(path):
    data = open(path, "rb").read()
    magic = data[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"):
        le = magic == b"\xd4\xc3\xb2\xa1"
    else:
        raise ValueError(f"not a pcap file: {path}")
    endian = "<" if le else ">"
    linktype = struct.unpack(endian + "I", data[20:24])[0]
    off, pkts = 24, []
    while off + 16 <= len(data):
        ts, tu, caplen, length = struct.unpack(endian + "IIII", data[off : off + 16])
        if caplen > 262144 or off + 16 + caplen > len(data):
            break  # truncated/corrupt trailer — stop cleanly
        pkts.append((ts + tu / 1e6, data[off + 16 : off + 16 + caplen]))
        off += 16 + caplen
    return linktype, pkts


def l3(frame, linktype):
    """Return (src_ip, dst_ip, l4proto, l4bytes) or None."""
    if linktype == 1:  # Ethernet
        if len(frame) < 14:
            return None
        et = struct.unpack(">H", frame[12:14])[0]
        ip = frame[14:]
    elif linktype == 0:  # BSD loopback: 4-byte family
        fam = struct.unpack("<I", frame[:4])[0]
        ip = frame[4:]
        et = 0x0800 if fam == 2 else (0x86DD if fam in (24, 28, 30) else 0)
    elif linktype in (113, 276):  # Linux cooked
        hdr = 16 if linktype == 113 else 20
        et = struct.unpack(">H", frame[14:16] if linktype == 113 else frame[0:2])[0]
        ip = frame[hdr:]
    else:
        return None
    if et == 0x0800:  # IPv4
        if len(ip) < 20 or (ip[0] >> 4) != 4:
            return None
        ihl = (ip[0] & 0xF) * 4
        proto = ip[9]
        src = ".".join(str(b) for b in ip[12:16])
        dst = ".".join(str(b) for b in ip[16:20])
        return src, dst, proto, ip[ihl:]
    if et == 0x86DD:  # IPv6
        if len(ip) < 40:
            return None
        proto = ip[6]
        src = ip[8:24].hex(":", 2) if hasattr(bytes, "hex") else ip[8:24].hex()
        dst = ip[24:40].hex()
        return src, dst, proto, ip[40:]
    return None


def udp(l4):
    if len(l4) < 8:
        return None
    sp, dp, ln, _ = struct.unpack(">HHHH", l4[:8])
    return sp, dp, l4[8:]


# ---- payload-entry container (Chapter 0 §4.5) -------------------------------

def parse_entries(buf):
    """Decode a tagged key/size/value payload container. Returns list of
    (fourcc:str, size:int, value:bytes); stops on a length that overruns."""
    out, i = [], 0
    while i + 8 <= len(buf):
        key = buf[i : i + 4]
        size = struct.unpack(">I", buf[i + 4 : i + 8])[0]
        if i + 8 + size > len(buf):
            out.append((key.decode("latin1"), size, None))  # overrun marker
            break
        out.append((key.decode("latin1"), size, buf[i + 8 : i + 8 + size]))
        i += 8 + size
    return out


def dec_endpoint4(v):
    if len(v) != 6:
        return {"raw": v.hex()}
    return {"addr": ".".join(str(b) for b in v[:4]), "port": struct.unpack(">H", v[4:6])[0]}


def dec_endpoint6(v):
    if len(v) != 18:
        return {"raw": v.hex()}
    return {"addr": v[:16].hex(), "port": struct.unpack(">H", v[16:18])[0]}


def dec_tmln(v):
    if len(v) != 24:
        return {"raw": v.hex()}
    tempo, beat, time = struct.unpack(">qqq", v)
    return {"tempo_us_per_beat": tempo, "beatOrigin_ubeats": beat, "timeOrigin_us": time,
            "bpm_approx": round(60e6 / tempo, 3) if tempo else None}


def dec_stst(v):
    if len(v) != 17:
        return {"raw": v.hex()}
    playing = v[0]
    beats, ts = struct.unpack(">qq", v[1:17])
    return {"isPlaying": playing, "beats_ubeats": beats, "timestamp_us": ts}


def dec_i64(v):
    return {"i64": struct.unpack(">q", v)[0]} if len(v) == 8 else {"raw": v.hex()}


def dec_id(v):
    return {"id": v.hex()} if len(v) == 8 else {"raw": v.hex()}


def dec_pi(v):  # peer info: length-prefixed string
    if len(v) >= 4:
        n = struct.unpack(">I", v[:4])[0]
        return {"name_len": n, "name": v[4 : 4 + n].decode("latin1", "replace")}
    return {"raw": v.hex()}


def dec_auca(v):  # channel announcements: u32 count, then [str name][8-byte id]*
    if len(v) < 4:
        return {"raw": v.hex()}
    n = struct.unpack(">I", v[:4])[0]
    chans, i = [], 4
    for _ in range(n):
        if i + 4 > len(v):
            break
        ln = struct.unpack(">I", v[i : i + 4])[0]
        name = v[i + 4 : i + 4 + ln].decode("latin1", "replace")
        cid = v[i + 4 + ln : i + 12 + ln]
        chans.append({"name": name, "id": cid.hex()})
        i += 12 + ln
    return {"count": n, "channels": chans}


def dec_aucb(v):  # channel byes: u32 count, then 8-byte ids
    if len(v) < 4:
        return {"raw": v.hex()}
    n = struct.unpack(">I", v[:4])[0]
    ids = [v[4 + 8 * k : 12 + 8 * k].hex() for k in range(n)]
    return {"count": n, "ids": ids}


ENTRY_DECODERS = {
    "tmln": dec_tmln, "sess": dec_id, "stst": dec_stst,
    "mep4": dec_endpoint4, "mep6": dec_endpoint6,
    "aep4": dec_endpoint4, "aep6": dec_endpoint6,
    "__ht": dec_i64, "__gt": dec_i64, "_pgt": dec_i64,
    "__pi": dec_pi, "auca": dec_auca, "aucb": dec_aucb, "chid": dec_id,
}

MAGIC = {
    b"_asdp_v\x01": "discovery",
    b"_link_v\x01": "sync",
    b"chnnlsv\x01": "audio",
}
DISC_TYPES = {0: "Invalid", 1: "Alive", 2: "Response", 3: "ByeBye"}
SYNC_TYPES = {1: "Ping", 2: "Pong"}
AUDIO_TYPES = {0: "Invalid", 1: "PeerAnnouncement", 2: "ChannelByes", 3: "Pong",
               4: "ChannelRequest", 5: "StopChannelRequest", 6: "AudioBuffer"}
ABU_FOURCC = bytes.fromhex("5f616275")  # '_abu'


def classify(pl):
    return MAGIC.get(pl[:8])


def decode_msg(pl, proto):
    """Decode one protocol message into a structured dict (header + payload)."""
    m = {"proto": proto, "len": len(pl)}
    if proto == "sync":
        m["type"] = pl[8]
        m["type_name"] = SYNC_TYPES.get(pl[8], f"unknown({pl[8]})")
        m["entries"] = _entries(pl[9:])
        return m
    # discovery & audio share the 20-byte header layout
    m["type"] = pl[8]
    m["ttl"] = pl[9]
    m["groupId"] = struct.unpack(">H", pl[10:12])[0]
    m["nodeId"] = pl[12:20].hex()
    body = pl[20:]
    if proto == "discovery":
        m["type_name"] = DISC_TYPES.get(pl[8], f"unknown({pl[8]})")
        m["entries"] = _entries(body)
    else:  # audio
        m["type_name"] = AUDIO_TYPES.get(pl[8], f"unknown({pl[8]})")
        if pl[8] == 6:  # AudioBuffer: bare structure, no container
            m["abu_prefix_present"] = body[:4] == ABU_FOURCC
            m["audiobuffer"] = _audiobuffer(body)
        else:
            m["entries"] = _entries(body)
    return m


def _entries(body):
    res = []
    for key, size, val in parse_entries(body):
        d = {"key": key, "size": size}
        if val is None:
            d["OVERRUN"] = True
        elif key in ENTRY_DECODERS:
            d["value"] = ENTRY_DECODERS[key](val)
        else:
            d["raw"] = val.hex()
        res.append(d)
    return res


def _audiobuffer(body):
    if len(body) < 20:
        return {"truncated": True}
    cid = body[:8].hex()
    sess = body[8:16].hex()
    n = struct.unpack(">I", body[16:20])[0]
    chunks, pos = [], 20
    for _ in range(n):
        if pos + 26 > len(body):
            break
        count = struct.unpack(">Q", body[pos : pos + 8])[0]
        nframes = struct.unpack(">H", body[pos + 8 : pos + 10])[0]
        beats = struct.unpack(">q", body[pos + 10 : pos + 18])[0]
        tempo = struct.unpack(">q", body[pos + 18 : pos + 26])[0]
        chunks.append({"count": count, "numFrames": nframes,
                       "beginBeats_ubeats": beats, "tempo_us_per_beat": tempo})
        pos += 26
    trailer = {}
    if pos + 8 <= len(body):
        trailer = {
            "codec": body[pos],
            "sampleRate": struct.unpack(">I", body[pos + 1 : pos + 5])[0],
            "numChannels": body[pos + 5],
            "numBytes": struct.unpack(">H", body[pos + 6 : pos + 8])[0],
        }
        trailer["sample_bytes_remaining"] = len(body) - (pos + 8)
        trailer["numBytes_matches_remaining"] = (
            trailer["numBytes"] == trailer["sample_bytes_remaining"]
        )
        total_frames = sum(c["numFrames"] for c in chunks)
        trailer["total_frames"] = total_frames
    return {"channelId": cid, "sessionId": sess, "chunkCount": n,
            "chunks": chunks, **trailer}


# ---- manifest ---------------------------------------------------------------

def build_manifest(path):
    linktype, pkts = read_pcap(path)
    msgs = []
    topo = defaultdict(lambda: {"src": set(), "dst": set()})  # proto -> ip sets
    gateways = defaultdict(set)  # nodeId -> set(src_ip) (one gw per src ip)
    ports = defaultdict(set)  # proto -> set(dst_port)
    for ts, frame in pkts:
        r = l3(frame, linktype)
        if not r:
            continue
        src, dst, proto_num, l4 = r
        if proto_num != 17:
            continue
        u = udp(l4)
        if not u:
            continue
        sp, dp, pl = u
        proto = classify(pl)
        if not proto:
            continue
        m = decode_msg(pl, proto)
        m.update({"ts": ts, "src": f"{src}:{sp}", "dst": f"{dst}:{dp}"})
        msgs.append(m)
        topo[proto]["src"].add(src)
        topo[proto]["dst"].add(dst)
        ports[proto].add(dp)
        if "nodeId" in m:
            gateways[m["nodeId"]].add(src)

    type_counts = Counter((m["proto"], m.get("type_name")) for m in msgs)
    peers = sorted(gateways.keys())

    man = {
        "file": path,
        "linktype": LINKTYPES.get(linktype, str(linktype)),
        "frames_total": len(pkts),
        "protocol_messages": len(msgs),
        "peers_by_nodeId": {
            nid: {"gateways": sorted(gateways[nid])} for nid in peers
        },
        "gateways_per_peer": {nid: len(gateways[nid]) for nid in peers},
        "destination_ports": {p: sorted(ports[p]) for p in ports},
        "message_type_counts": {
            f"{proto}/{name}": c for (proto, name), c in sorted(type_counts.items())
        },
    }

    # discovery: distinct entry-key sets and datagram sizes per set
    disc = [m for m in msgs if m["proto"] == "discovery" and m["type"] in (1, 2)]
    disc_sets = defaultdict(set)
    for m in disc:
        keys = tuple(e["key"] for e in m.get("entries", []))
        disc_sets[keys].add(m["len"])
    man["discovery_peerstate"] = [
        {"entry_keys": list(k), "datagram_sizes": sorted(v)}
        for k, v in disc_sets.items()
    ]

    # sync: ping/pong sizes and entry-key sets
    sync_sets = defaultdict(set)
    for m in (m for m in msgs if m["proto"] == "sync"):
        keys = (m["type_name"],) + tuple(e["key"] for e in m.get("entries", []))
        sync_sets[keys].add(m["len"])
    man["sync_messages"] = [
        {"shape": list(k), "datagram_sizes": sorted(v)} for k, v in sync_sets.items()
    ]

    # audio: announcement entry sets, channels seen, audiobuffer params
    abufs = [m["audiobuffer"] for m in msgs
             if m["proto"] == "audio" and m["type"] == 6 and "audiobuffer" in m]
    man["audio_buffer"] = {
        "count": len(abufs),
        "abu_prefix_ever_present": any(
            m.get("abu_prefix_present") for m in msgs
            if m["proto"] == "audio" and m["type"] == 6
        ),
        "codecs": sorted({a.get("codec") for a in abufs if "codec" in a}),
        "sample_rates": sorted({a.get("sampleRate") for a in abufs if "sampleRate" in a}),
        "num_channels": sorted({a.get("numChannels") for a in abufs if "numChannels" in a}),
        "chunk_counts": sorted({a.get("chunkCount") for a in abufs}),
        "numBytes_range": (
            [min(a["numBytes"] for a in abufs if "numBytes" in a),
             max(a["numBytes"] for a in abufs if "numBytes" in a)]
            if any("numBytes" in a for a in abufs) else []
        ),
        "numBytes_always_matches_remaining": all(
            a.get("numBytes_matches_remaining", True) for a in abufs
        ),
        "tempo_values_us_per_beat": sorted(
            {c["tempo_us_per_beat"] for a in abufs for c in a.get("chunks", [])}
        ),
    }
    announce = [m for m in msgs if m["proto"] == "audio" and m["type"] == 1]
    ann_sets = defaultdict(set)
    chans = {}
    for m in announce:
        ann_sets[tuple(e["key"] for e in m.get("entries", []))].add(m["len"])
        for e in m.get("entries", []):
            if e["key"] == "auca" and "value" in e:
                for ch in e["value"].get("channels", []):
                    chans[ch["id"]] = ch["name"]
    man["audio_announcements"] = [
        {"entry_keys": list(k), "datagram_sizes": sorted(v)} for k, v in ann_sets.items()
    ]
    man["audio_channels_announced"] = chans
    man["audio_groupIds"] = sorted(
        {m["groupId"] for m in msgs if m["proto"] == "audio"}
    )
    return man, msgs


def print_manifest_md(man):
    p = print
    p(f"# Observed-fact manifest: `{man['file']}`\n")
    p(f"- Link type: **{man['linktype']}**")
    p(f"- Frames captured: **{man['frames_total']}**, "
      f"decoded protocol messages: **{man['protocol_messages']}**")
    p(f"- Distinct peers (by NodeId): **{len(man['peers_by_nodeId'])}**")
    p(f"- Gateways per peer: "
      f"**{sorted(set(man['gateways_per_peer'].values())) or ['n/a']}** "
      f"(distinct source IPs each NodeId transmits from)")
    for nid, info in man["peers_by_nodeId"].items():
        p(f"    - `{nid}` via {info['gateways']}")
    p(f"- Destination ports by protocol: {man['destination_ports']}\n")
    p("## Message-type counts\n")
    for k, c in man["message_type_counts"].items():
        p(f"- `{k}`: {c}")
    p("\n## Discovery peer-state shapes\n")
    for s in man["discovery_peerstate"]:
        p(f"- entries {s['entry_keys']} -> datagram sizes {s['datagram_sizes']} bytes")
    p("\n## Sync message shapes\n")
    for s in man["sync_messages"]:
        p(f"- {s['shape']} -> {s['datagram_sizes']} bytes")
    if man["message_type_counts"].get("audio/AudioBuffer") or man["audio_announcements"]:
        ab = man["audio_buffer"]
        p("\n## Audio\n")
        p(f"- groupIds seen: {man['audio_groupIds']}")
        p(f"- channels announced: {man['audio_channels_announced']}")
        for s in man["audio_announcements"]:
            p(f"- announcement entries {s['entry_keys']} -> {s['datagram_sizes']} bytes")
        p(f"- AudioBuffers: {ab['count']}; `_abu` prefix ever present: "
          f"**{ab['abu_prefix_ever_present']}**")
        p(f"  - codecs={ab['codecs']} rates={ab['sample_rates']} "
          f"channels={ab['num_channels']} chunkCounts={ab['chunk_counts']}")
        p(f"  - numBytes range={ab['numBytes_range']}, "
          f"always == trailing bytes: **{ab['numBytes_always_matches_remaining']}**")
        p(f"  - chunk tempo values (us/beat): {ab['tempo_values_us_per_beat']}")


def print_dump(msgs, which):
    for m in msgs:
        if which != "all" and m["proto"] != which:
            continue
        head = f"{m['ts']:.6f} {m['src']} > {m['dst']} {m['proto']}/{m.get('type_name')}"
        extra = {k: v for k, v in m.items()
                 if k not in ("ts", "src", "dst", "proto", "type_name", "type")}
        print(head)
        print("    " + json.dumps(extra, default=str))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--dump", choices=["all", "discovery", "sync", "audio"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    man, msgs = build_manifest(args.pcap)
    if args.dump:
        print_dump(msgs, args.dump)
    elif args.json:
        print(json.dumps(man, indent=2, default=str))
    else:
        print_manifest_md(man)


if __name__ == "__main__":
    main()
