# Observed-fact manifest: `multi-gateway-discovery.pcap`

- Link type: **LINUX_SLL2**
- Frames captured: **418**, decoded protocol messages: **418**
- Distinct peers (by NodeId): **2**
- Gateways per peer: **[2]** (distinct source IPs each NodeId transmits from)
    - `41684d28793c3a72` via ['127.0.0.1', '192.168.77.1']
    - `5d3628713b443555` via ['127.0.0.1', '192.168.77.1']
- Destination ports by protocol: {'discovery': [20808, 45567, 59282], 'sync': [43213, 55891]}

## Message-type counts

- `discovery/Alive`: 153
- `discovery/ByeBye`: 6
- `discovery/Response`: 51
- `sync/Ping`: 104
- `sync/Pong`: 104

## Discovery peer-state shapes

- entries ['tmln', 'sess', 'stst', 'mep4'] -> datagram sizes [107] bytes
- timeline tempos seen (us/beat): [500000]; beatOrigin range (ubeats): [1000554, 1007262]
- start/stop isPlaying values seen: [0] (1 distinct states)

## Sync message shapes

- ['Ping', '__ht'] -> [25] bytes
- ['Pong', 'sess', '__gt', '__ht'] -> [57] bytes
- ['Ping', '__ht', '_pgt'] -> [41] bytes
- ['Pong', 'sess', '__gt', '__ht', '_pgt'] -> [73] bytes
