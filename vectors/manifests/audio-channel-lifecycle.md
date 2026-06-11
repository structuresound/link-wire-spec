# Observed-fact manifest: `audio-channel-lifecycle.pcap`

- Link type: **EN10MB**
- Frames captured: **2919**, decoded protocol messages: **2919**
- Distinct peers (by NodeId): **3**
- Gateways per peer: **[1]** (distinct source IPs each NodeId transmits from)
    - `2b6d307053433b39` via ['127.0.0.1']
    - `3f667a683b374669` via ['127.0.0.1']
    - `4b48305b30312929` via ['127.0.0.1']
- Destination ports by protocol: {'discovery': [20808, 37659, 38602], 'sync': [35720, 57657], 'audio': [34751, 51311]}

## Message-type counts

- `audio/AudioBuffer`: 2098
- `audio/ChannelByes`: 1
- `audio/ChannelRequest`: 3
- `audio/PeerAnnouncement`: 132
- `audio/Pong`: 132
- `audio/StopChannelRequest`: 1
- `discovery/Alive`: 171
- `discovery/ByeBye`: 2
- `discovery/Response`: 171
- `sync/Ping`: 104
- `sync/Pong`: 104

## Discovery peer-state shapes

- entries ['tmln', 'sess', 'stst', 'mep4'] -> datagram sizes [107] bytes
- entries ['tmln', 'sess', 'stst', 'mep4', 'aep4'] -> datagram sizes [121] bytes
- timeline tempos seen (us/beat): [495868, 500000]; beatOrigin range (ubeats): [1998382, 29038996]
- start/stop isPlaying values seen: [0] (1 distinct states)

## Sync message shapes

- ['Ping', '__ht'] -> [25] bytes
- ['Pong', 'sess', '__gt', '__ht'] -> [57] bytes
- ['Ping', '__ht', '_pgt'] -> [41] bytes
- ['Pong', 'sess', '__gt', '__ht', '_pgt'] -> [73] bytes

## Audio

- groupIds seen: [0]
- channels announced: {'4270605271233878': 'A Sink', '7027443e657e465f': 'A Sink'}
- announcement entries ['sess', '__pi', 'auca', '__ht'] -> [97, 99] bytes
- AudioBuffers: 2098; `_abu` prefix ever present: **False**
  - codecs=[1] rates=[48000] channels=[1] chunkCounts=[1, 2]
  - numBytes range=[502, 502], always == trailing bytes: **True**
  - chunk tempo values (us/beat): [495868, 500000]
