# 06 — Packet and PDU format (the wire contract)

Scope: datagram (`VideoHeader` + payload) and its PMT/PDU wrapper for `TRANSPORT="radio"`. The UDP path uses the datagram alone.
Evidence legend: `VERIFIED` / `INFERRED` / `UNPROVEN`; every numeric claim is listed in §6.

## 1. `VideoHeader` — 24-byte field table

Struct: `struct.pack('!IIHHBBQH', …)` — `!` = network byte order (big-endian) for every field (`transport/video_header.py:15-25`; unpack mirror `:26-30`).

Example row values are the representative unit from `test/test_zmq_pdu_transport.py:38-40` (layout proven byte-exact by `test/test_datagram.py:13-17`).

| Offset | Size | Field | Format / bytes | Example value (hex) |
|-------:|-----:|-------|----------------|---------------------|
| 0 | 4 | `packet_sequence` | `I` — u32 BE | `00 00 00 01` |
| 4 | 4 | `nalu_id` | `I` — u32 BE | `00 00 00 01` |
| 8 | 2 | `fragment_index` | `H` — u16 BE | `00 00` |
| 10 | 2 | `fragment_count` | `H` — u16 BE | `00 01` |
| 12 | 1 | `nal_type` | `B` — u8 | `05` |
| 13 | 1 | `priority` | `B` — u8 (`Priority` IntEnum: 0 CRITICAL … 3 LOW, `priority_classifier.py:4-8`) | `01` (HIGH) |
| 14 | 8 | `timestamp_ns` | `Q` — u64 BE | `00 00 00 00 00 00 00 00` |
| 22 | 2 | `payload_size` | `H` — u16 BE | `00 03` |
| **Total** | **24** | | `!IIHHBBQH` | |

Field semantics: `packet_sequence` global per-fragment counter, `nalu_id` per-NALU counter (both from `packetizer.py:49,54`); `timestamp_ns` = `time.monotonic_ns()` at packetization (`packetizer.py:50`); `payload_size` = `len(payload)` at build time (`datagram.py:8`).

## 2. Datagram ceiling derivation

All three constants live together (`config.py:15-19`):

```python
header_for_calculate_size = VideoHeader(0,0,0,0,0,Priority.CRITICAL,0,0)
REAL_HEADER_SIZE = len(header_for_calculate_size.to_bytes())   # 4+4+2+2+1+1+8+2 = 24
UDP_SAFE_PAYLOAD = 1200
SIZE_MAX_PACKET = UDP_SAFE_PAYLOAD - REAL_HEADER_SIZE          # 1200 - 24 = 1176
```

- **Why 24:** computed at import time by packing an all-zero header with the same struct — never hand-maintained (`config.py:16-17`). `VERIFIED`.
- **Why 1200:** the literal is the configured ceiling; `build_datagram` rejects anything strictly larger (`datagram.py:10-12`). The *rationale* (conservative headroom under a 1500-B Ethernet MTU / ~1472-B UDP payload) is **not stated in the repo** → `INFERRED`. The nearby comment `# SimpleRtp` (`config.py:15`) names the block only. `VERIFIED` value, `INFERRED` reason.
- **How 1176 is used:** `Paketizer` fragments at exactly `SIZE_MAX_PACKET` (`packetizer.py:41-43`), so a full fragment yields `24 + 1176 = 1200` = ceiling, accepted; one byte more raises (`test_datagram.py:31-37`, `test_zmq_pdu_transport.py:45-51`). Both transports enforce the same check because both call `build_datagram`. `VERIFIED`.

## 3. PMT/PDU wrap

Encoder (`radio/pmt_codec.py:13-15`):

```
frame = 07 06 | 0a 00 | <len>u32BE | 01 00 | datagram
        └─┬─┘  └─┬─┘   └───┬────┘  └─┬─┘
        PAIR   uniform    length   npad=1,
        + NIL  vector     of the    pad byte 00
        (car)  (u8)       datagram
```

- Prefix = **10 bytes**: `07 06 0a 00 <len BE u32> 01 00`.
- `total frame = 10 + datagram_len`; length field = `len(datagram)` (excludes the prefix itself).
- Byte semantics `VERIFIED` from `_parse`: `07`=PST_PAIR, `06`=PST_NULL (car = nil meta — **not** a `PST_DICT 0x09` object), `0a`=PST_UNIFORM_VECTOR, `00`=UVI_U8, then u32-BE length, `npad=0x01`, one pad byte `00`, then payload (`pmt_codec.py:3-6,44-59`). The README's `cons(dict, u8vector)` wording (`README_FLOWGRAPHS.md:61-70`) is looser than the bytes; code wins.
- Roundtrips and boundaries tested: empty payload → exactly the 10-byte prefix (`test_pmt_codec.py:5-7`), 1200-byte payload → prefix `07060a00000004b00100` + 1200 = 1210 (`:9-12`), arbitrary roundtrip (`:14-16`).

### Hexdump — the 27-byte example (frame = 37 bytes) `VERIFIED`

```
Offset  Hex                                            Decoded
0000    07                                              PST_PAIR
0001    06                                              car = PST_NULL (nil metadata)
0002    0a                                              PST_UNIFORM_VECTOR
0003    00                                              subtype UVI_U8
0004    00 00 00 1b                                     length = 27 (BE u32)
0008    01                                              npad = 1
0009    00                                              pad byte
000A    00 00 00 01                                     VideoHeader.packet_sequence = 1
000E    00 00 00 01                                     VideoHeader.nalu_id = 1
0012    00 00                                           VideoHeader.fragment_index = 0
0014    00 01                                           VideoHeader.fragment_count = 1
0016    05                                              VideoHeader.nal_type = 5 (IDR)
0017    01                                              VideoHeader.priority = 1 (HIGH)
0018    00 00 00 00 00 00 00 00                         VideoHeader.timestamp_ns = 0
0020    00 03                                           VideoHeader.payload_size = 3
0022    01 02 03                                        payload
      ── 37 bytes total = 10 + 27 ──
```

One-line form:

```
07060a000000001b0100000000010000000100000001050100000000000000000003010203   # 37 B
```

Evidence: prefix/length math (`test_pmt_codec.py`), `send_packet` returns 27 while the sent frame is `encode_u8vector_pdu(build_datagram(packet))` (`test_zmq_pdu_transport.py:41-43`), header bytes (`test_datagram.py:13-17`).

## 4. GNU Radio side: what consumes it

- The flowgraph's `ZMQ PULL Message Source` receives the serialized PMT on `tcp://127.0.0.1:5555` in **connect** mode (`tx_bladerf.grc:55-81`); `capture.py`/`ZMQPduTransport` is the **bind** side (`zmq_pdu_transport.py:20-21`, `config_radio.py:1,3`) — roles documented at `README_FLOWGRAPHS.md:36-37`.
- Intended compatibility contract: `pmt::serialize_str(cons(dict, u8vector))` (`README_FLOWGRAPHS.md:59-70`, flowgraph description `tx_bladerf.grc:20`). What the Python side actually emits is `cons(nil, u8vector)` (§3) — same PDU *shape* (pair with u8vector cdr), car differs from the README's wording.
- `blks2.pdu_to_tagged_stream` (Type `byte`, Len Tag Key `packet_len`) turns the PDU into a byte stream tagged with its length (`tx_bladerf.grc:82-96`); `digital.gmsk_mod` modulates (`:97-123`); the `bladerf_sink` transmits (`:124-142`).
- **The flowgraph never parses `VideoHeader`**: the datagram travels opaquely from ZMQ message to RF bytes (`INFERRED` from the absence of any parsing block in `tx_bladerf.grc`; block list `VERIFIED`).
- Acceptance of *our exact bytes* by GNU Radio's ZMQ/PDU blocks, and everything after GMSK, is **`UNPROVEN`** — the only evidence is the manual checklist `radio/flowgraphs/README_FLOWGRAPHS.md:72-81`; tests only assert XML well-formedness (`test/test_flowgraphs.py:6-10`).
- RX mirror: `blocks.tagged_stream_to_pdu` → `ZMQ PUSH Message Sink` bind 5556 (`rx_hackrf.grc:125-166`), consumed by `decode_pdu_data` (§3 encoder run in reverse, `pmt_codec.py:72-81`).

## 5. ASCII box diagrams

```
DATAGRAM  (24 + M bytes, M ≤ 1176, total ≤ 1200)
┌──────────────────────────────────────────────┬─────────────────────────────┐
│ VideoHeader — 24 bytes (struct !IIHHBBQH)    │ Payload — M bytes           │
├────┬────┬─────┬─────┬────┬─────┬────────┬────┤│ (H.264 fragment,           │
│seq │ id │ idx │ cnt │t(1)│pri(1)│ ts(8)  │psz ││  raw NALU bytes,           │
│ 4  │ 4  │ 2   │ 2   │  B │  B  │  Q     │ 2  ││  no start code)            │
└────┴────┴─────┴─────┴────┴─────┴────────┴────┘└─────────────────────────────┘
offset 0                               23      24                        24+M ≤ 1200

PDU FRAME  (10 + 24 + M bytes)   — what ZMQ PUSH sends on 5555
┌───────────────────────────────────────────────────────────────────────────────┐
│ PMT prefix — 10 bytes                       │ datagram (above)               │
│ 07 06 │ 0a 00 │ <len u32 BE> │ 01 00        │ 24-byte VideoHeader + payload  │
│ PAIR  │ u8vec │ = 24+M       │ npad, pad    │ ≤ 1200 bytes                   │
└───────────────────────────────────────────┴───────────────────────────────────┘
        len field counts ONLY the datagram          total = 10 + datagram_len

ZMQ MESSAGE  = one PDU frame per socket.send() call (zmq_pdu_transport.py:28)
UDP DATAGRAM = the datagram alone (no prefix), sent via sendto (udp_transport.py:14,20)
```

## 6. Evidence table for every numeric claim

| # | Claim | Value | Evidence | Tag |
|---|-------|-------|----------|-----|
| 1 | Header size | 24 bytes | `video_header.py:15-25`; computed `config.py:16-17`; byte-exact test `test_datagram.py:13-17` | `VERIFIED` |
| 2 | Struct format | `!IIHHBBQH` (4+4+2+2+1+1+8+2) | `video_header.py:16,29` | `VERIFIED` |
| 3 | `UDP_SAFE_PAYLOAD` | 1200 | `config.py:18`; ceiling check `datagram.py:10-12` | `VERIFIED` |
| 4 | `SIZE_MAX_PACKET` | 1176 = 1200 − 24 | `config.py:19`; fragmenting `packetizer.py:41-43` | `VERIFIED` |
| 5 | 1176 payload → 1200 datagram OK; 1177 raises | 1200 / `ValueError` | `test_datagram.py:31-37`; `test_zmq_pdu_transport.py:45-51` | `VERIFIED` |
| 6 | Rationale for choosing 1200 | MTU headroom | no code comment | `INFERRED` |
| 7 | Example datagram length | 27 = 24 + 3 | `test_zmq_pdu_transport.py:42`; loopback `test_zmq_loopback_integration.py:26` | `VERIFIED` |
| 8 | PMT prefix length | 10 bytes | `pmt_codec.py:13-15`; empty-payload test `test_pmt_codec.py:5-7` | `VERIFIED` |
| 9 | Example frame length | 37 = 10 + 27 | `test_zmq_pdu_transport.py:41-43` (sent==27, frame==encode(...)); prefix math `test_pmt_codec.py:5-12` | `VERIFIED` |
| 10 | Length field counts only the datagram | = `len(datagram)`, excludes prefix | `pmt_codec.py:14`; empty payload → exactly the 10-B prefix `test_pmt_codec.py:5-7` | `VERIFIED` |
| 11 | Max datagram (1176 payload) → frame | 1210 = 10 + 1200 | `test_pmt_codec.py:9-12` | `VERIFIED` |
| 12 | Example one-line frame hex | `07060a000000001b01 00 …03010203`, 74 hex chars | rows 1,7–9; hexdump §3 | `VERIFIED` |
| 13 | PDU car is `PST_NULL` (nil), not a dict | `06` | `pmt_codec.py:3-6,50-59` (code wins over `README_FLOWGRAPHS.md:61-70`) | `VERIFIED` |
| 14 | Flowgraph never parses `VideoHeader` | opaquely passes bytes | no header-parsing block in `tx_bladerf.grc:55-142` | `INFERRED` |
| 15 | GNU Radio accepts these exact PDU bytes end-to-end | n/a | manual checklist only `README_FLOWGRAPHS.md:72-81`; tests assert XML only `test_flowgraphs.py:6-10` | `UNPROVEN` |
| 16 | RX decode is the exact reverse | 10-B prefix stripped, datagram returned | `pmt_codec.py:72-81`; roundtrip `test_pmt_codec.py:14-16`; loopback `test_zmq_loopback_integration.py:19-32` | `VERIFIED` |