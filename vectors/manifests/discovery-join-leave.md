# Observed-fact manifest: `discovery-join-leave.pcap`

- Link type: **EN10MB**
- Frames captured: **302**, decoded protocol messages: **302**
- Distinct peers (by NodeId): **3**
- Gateways per peer: **[1]** (distinct source IPs each NodeId transmits from)
    - `457a3b5f4c6e7b4c` via ['127.0.0.1']
    - `633e262161542163` via ['127.0.0.1']
    - `6841524e5a542331` via ['127.0.0.1']
- Destination ports by protocol: {'discovery': [20808, 47239, 60739], 'sync': [42802, 51606]}

## Message-type counts

- `discovery/Alive`: 58
- `discovery/ByeBye`: 2
- `discovery/Response`: 34
- `sync/Ping`: 104
- `sync/Pong`: 104

## Discovery peer-state shapes

- entries ['tmln', 'sess', 'stst', 'mep4'] -> datagram sizes [107] bytes
- timeline tempos seen (us/beat): [500000]; beatOrigin range (ubeats): [999822, 16034038]
- start/stop isPlaying values seen: [0] (1 distinct states)

## Sync message shapes

- ['Ping', '__ht'] -> [25] bytes
- ['Pong', 'sess', '__gt', '__ht'] -> [57] bytes
- ['Ping', '__ht', '_pgt'] -> [41] bytes
- ['Pong', 'sess', '__gt', '__ht', '_pgt'] -> [73] bytes
