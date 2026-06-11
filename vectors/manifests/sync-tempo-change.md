# Observed-fact manifest: `sync-tempo-change.pcap`

- Link type: **EN10MB**
- Frames captured: **344**, decoded protocol messages: **344**
- Distinct peers (by NodeId): **2**
- Gateways per peer: **[1]** (distinct source IPs each NodeId transmits from)
    - `3a222d7934583c2a` via ['127.0.0.1']
    - `5840706a4d546f64` via ['127.0.0.1']
- Destination ports by protocol: {'discovery': [20808, 33835, 57068], 'sync': [45545, 59318]}

## Message-type counts

- `discovery/Alive`: 67
- `discovery/ByeBye`: 2
- `discovery/Response`: 67
- `sync/Ping`: 104
- `sync/Pong`: 104

## Discovery peer-state shapes

- entries ['tmln', 'sess', 'stst', 'mep4'] -> datagram sizes [107] bytes
- timeline tempos seen (us/beat): [483871, 487805, 491803, 495868, 500000]; beatOrigin range (ubeats): [1000178, 11141773]
- start/stop isPlaying values seen: [0] (1 distinct states)

## Sync message shapes

- ['Ping', '__ht'] -> [25] bytes
- ['Pong', 'sess', '__gt', '__ht'] -> [57] bytes
- ['Ping', '__ht', '_pgt'] -> [41] bytes
- ['Pong', 'sess', '__gt', '__ht', '_pgt'] -> [73] bytes
