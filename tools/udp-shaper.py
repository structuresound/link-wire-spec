#!/usr/bin/env python3
"""udp-shaper.py — userspace network-impairment shaper (netem stand-in).

Applies one-way delay, jitter, random loss, and/or a token-bucket rate limit
to UDP traffic via an NFQUEUE iptables target. Exists because container
kernels frequently ship without qdisc modules (`tc netem` unavailable) —
this needs only nfnetlink_queue support and the `NetfilterQueue` Python
package (pip). Used by conformance/run-isolated.sh when SHAPE is set, to
reproduce the operating-envelope observations in spec chapters 02 §5.1 and
03 §5.8.

Contains no protocol logic: it never constructs, parses, or inspects a
message beyond its byte length.

Setup (inside the target network namespace, as root):
  iptables -A OUTPUT -o lo -p udp -j NFQUEUE --queue-num 1 --queue-bypass
  udp-shaper.py --delay 50 --jitter 10 [--loss 2] [--rate 512] &

Options:
  --delay MS      base one-way delay (applied once per packet on OUTPUT)
  --jitter MS     uniform +/- jitter added to the delay (reorders, like netem)
  --loss PCT      random drop percentage
  --rate KBIT     token-bucket rate limit; queued while starved, dropped
                  when the backlog exceeds --limit bytes
  --limit BYTES   backlog cap when rate-limited (default 65536)
  --seed N        RNG seed (default 1; runs are reproducible)

License: MIT
"""
import argparse
import heapq
import random
import threading
import time

from netfilterqueue import NetfilterQueue

ap = argparse.ArgumentParser()
ap.add_argument("--delay", type=float, default=0.0)
ap.add_argument("--jitter", type=float, default=0.0)
ap.add_argument("--loss", type=float, default=0.0)
ap.add_argument("--rate", type=float, default=0.0, help="kbit/s, 0 = unlimited")
ap.add_argument("--limit", type=int, default=65536)
ap.add_argument("--seed", type=int, default=1)
args = ap.parse_args()

rng = random.Random(args.seed)
heap = []  # (release_time, seq, packet, length)
heap_lock = threading.Condition()
seq = 0

bucket = float(args.limit)  # token bucket in bytes
bucket_rate = args.rate * 1000.0 / 8.0  # bytes/s
bucket_t = time.monotonic()
queued_bytes = 0


def on_packet(pkt):
    global seq, queued_bytes
    if args.loss > 0 and rng.random() * 100.0 < args.loss:
        pkt.drop()
        return
    d = args.delay
    if args.jitter > 0:
        d += rng.uniform(-args.jitter, args.jitter)
    d = max(d, 0.0) / 1000.0
    ln = len(pkt.get_payload())
    with heap_lock:
        if args.rate > 0 and queued_bytes + ln > args.limit:
            pkt.drop()
            return
        queued_bytes += ln
        seq += 1
        heapq.heappush(heap, (time.monotonic() + d, seq, pkt, ln))
        heap_lock.notify()


def scheduler():
    global queued_bytes, bucket, bucket_t
    while True:
        with heap_lock:
            while not heap:
                heap_lock.wait()
            t, _, pkt, ln = heap[0]
            now = time.monotonic()
            if t > now:
                heap_lock.wait(min(t - now, 0.005))
                continue
            heapq.heappop(heap)
            queued_bytes -= ln
        if bucket_rate > 0:
            while True:
                now = time.monotonic()
                bucket = min(float(args.limit), bucket + (now - bucket_t) * bucket_rate)
                bucket_t = now
                if bucket >= ln:
                    bucket -= ln
                    break
                time.sleep((ln - bucket) / bucket_rate)
        pkt.accept()


threading.Thread(target=scheduler, daemon=True).start()

nfq = NetfilterQueue()
nfq.bind(1, on_packet, max_len=4096)
try:
    nfq.run()
except KeyboardInterrupt:
    pass
