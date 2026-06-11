# Observed-fact manifest: `sync-start-stop.pcap`

- Link type: **EN10MB**
- Frames captured: **363**, decoded protocol messages: **363**
- Distinct peers (by NodeId): **3**
- Gateways per peer: **[1]** (distinct source IPs each NodeId transmits from)
    - `2d7629642b242627` via ['127.0.0.1']
    - `3833783e483a5d5c` via ['127.0.0.1']
    - `433b772b6423615b` via ['127.0.0.1']
- Destination ports by protocol: {'discovery': [20808, 36941, 45556], 'sync': [35462, 56326]}

## Message-type counts

- `discovery/Alive`: 77
- `discovery/ByeBye`: 2
- `discovery/Response`: 76
- `sync/Ping`: 104
- `sync/Pong`: 104

## Discovery peer-state shapes

- entries ['tmln', 'sess', 'stst', 'mep4'] -> datagram sizes [107] bytes
- timeline tempos seen (us/beat): [500000]; beatOrigin range (ubeats): [1000144, 19022334]
- start/stop isPlaying values seen: [0, 1] (3 distinct states)

## Sync message shapes

- ['Ping', '__ht'] -> [25] bytes
- ['Pong', 'sess', '__gt', '__ht'] -> [57] bytes
- ['Ping', '__ht', '_pgt'] -> [41] bytes
- ['Pong', 'sess', '__gt', '__ht', '_pgt'] -> [73] bytes
