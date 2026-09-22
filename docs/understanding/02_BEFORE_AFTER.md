# 02 — Before / After

> `VERIFIED` unless noted. Diagrams: `diagrams/before-after.mmd`.

## Conceptually intended (this is NOT the final architecture)

A plain transport swap was the simplest mental model before inspecting the code:

```text
OLD:  capture → packetization → UDP transport → network → UDP receiver → reassembly → ffplay
NEW:  capture → packetization → ZMQ PDU → GNU Radio/SDR → ZMQ PDU → radio receiver → reassembly → ffplay
```

The actual implementation is close to that idea with three important nuances
(the code is the definitive truth):

1. The transport swap is **not hardwired** — it is a factory switch
   (`get_transport()` + `config.TRANSPORT`) `VERIFIED`
   (`transport/transport_factory.py:3-13`).
2. A **shared, extracted layer** (`transport/datagram.py`,
   `packets/reassembler.py`) is used by BOTH routes, so packetization → bytes
   → reconstitution are identical on UDP and radio `VERIFIED`.
3. ZMQ crosses a **GNU Radio PMT/PDU representation** of the same datagram, not
   raw UDP bytes `VERIFIED` (radio/pmt_codec.py:13-15).

## OLD route (baseline on `main`) — `VERIFIED`

```text
Camera /dev/video0
   │
   ▼
ffmpeg (libx264 ultrafast zerolatency, Annex B)        ffmpeg_video_source.py:7-16
   │
   ▼
NALU parser → classify priority                        packets/nalu_parser.py, priority_classifier.py
   │
   ▼
Packetizer  → NALUPacket fragments (≤1176 B payload)   packets/packetizer.py:31-68
   │
   ▼
PacketScheduler (priority queues)                      packets/packetScheduler.py
   │
   ▼
UdpTransport (hardcoded in capture.py:20)              transport/udp_transport.py:13-21
   │  datagram = VideoHeader(24B) + payload   (≤1200 B)
   ▼
UDP socket → 127.0.0.1:65432                            reciever_nalu.py:22-24
   │
   ▼
reciever_nalu.py: socket → split header/payload → reassemble (inline) → ffplay
```

## NEW route (integration on `blade_protocol_adaptation`) — `VERIFIED`

```text
Camera /dev/video0
   │
   ▼
ffmpeg → NALU parser → classify → Packetizer → Scheduler        (unchanged)
   │
   ▼
get_transport()  (config.TRANSPORT)                  transport/transport_factory.py:3-13
   │  "udp" ───────────────────────────────┐         (unchanged OLD route)
   │  "radio"                              │
   ▼                                      ▼
ZMQPduTransport (PUSH bind 5555)      UdpTransport (unchanged)
   │  build_datagram(packet)         transport/datagram.py:5-13
   ▼
encode_u8vector_pdu(datagram)     → GNU Radio PDU (cons(dict, u8vector))     radio/pmt_codec.py:13-15
   ▼
ZMQ PUSH → tcp://127.0.0.1:5555        radio/zmq_pdu_transport.py:25-29
   │
   ▼
[GNU Radio] tx_bladerf.grc: ZMQ PULL Message Source → PDU to Tagged Stream
   → GMSK Mod → BladeRF sink (2.45 GHz / 20 Msps)      radio/flowgraphs/tx_bladerf.grc  (reference)
   │   RF link
   ▼
[GNU Radio] rx_hackrf.grc: osmosdr source → GMSK Demod → Tagged Stream to PDU
   → ZMQ PUSH Message Sink → tcp://127.0.0.1:5556
   │
   ▼
radio/reciever_radio.py: ZMQPduReceiver (PULL connect 5556)   radio/zmq_pdu_receiver.py:56-84
   │  decode_pdu_data(frame) → datagram bytes                radio/pmt_codec.py:72-81
   │  parse_datagram → VideoHeader(24B) + payload            transport/datagram.py:15-19
   ▼
Reassembler.feed (shared, same as UDP receiver)   packets/reassembler.py:12-37
   │
   ▼
NALU → 00 00 00 01 + nalu → ffplay (+ reconstructed_rf file)   radio/zmq_pdu_receiver.py:64-78
```

## What actually changed, phrased as deltas

| Delta | Detail | Evidence |
|---|---|---|
| Transport is now pluggable | `UdpTransport` no longer hardcoded in `capture.py`; factory + `TRANSPORT` | `capture.py:5,20`, `transport_factory.py:3-13` |
| Datagram build/parse extracted | one `build_datagram`/`parse_datagram` used by UDP TX and both receivers | `transport/datagram.py:5-19` |
| Reassembly extracted | inline function + global dict → `Reassembler` class | `packets/reassembler.py:4-37`, `reciever_nalu.py:7,32` |
| A GNU Radio-facing package appeared | `radio/` with PMT codec, ZMQ TX/RX adapters, config, receiver script | `radio/*.py` |
| Reference flowgraphs added | TX BladeRF / RX HackRF as GNU Radio Companion sources | `radio/flowgraphs/*.grc` |
| New optional dependency | `pyzmq` required only when `TRANSPORT = "radio"` | `requirements-radio.txt` |
| Same wire bytes | the PMT payload == the UDP datagram bytes | `radio/zmq_pdu_transport.py:26`, `radio/pmt_codec.py` |

## Numbers that stay identical across routes `VERIFIED`

- Header: 24 bytes, `'!IIHHBBQH'` big-endian (`transport/video_header.py:15-30`).
- Ceiling: datagram ≤ 1200 B; max payload = 1176 B (`config.py:16-19`).
- Example: 3-byte payload → datagram 27 B → ZMQ frame 37 B
  (10-byte PMT prefix + 27 B datagram) (`test/test_zmq_pdu_transport.py:38-43`;
  the `XYZ` payload appears in the loopback test `test_zmq_loopback_integration.py:25`).

## Diagram

See `diagrams/before-after.mmd` for the Mermaid rendering of both routes side by
side. The `.grc`/SDR stages are drawn inside a "GNU Radio (external)" boundary
and labeled reference/UNPROVEN for the RF link itself.