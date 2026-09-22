# 01 — Change Summary

> Scope: the GNU Radio / ZMQ PDU integration on branch `blade_protocol_adaptation`
> relative to the UDP baseline on `main` (merge-base `e1fead5`).
> Evidence classes: `VERIFIED` (code/test), `INFERRED`, `PLAN_ONLY`, `UNPROVEN`.

## What the system did before (baseline on `main`)

A single-path H.264 real-time streaming prototype over UDP `VERIFIED`:

```
Camera (/dev/video0)
  → ffmpeg (libx264, ultrafast, zerolatency)      ffmpeg_video_source.py:7-16
  → chunk read (4096 B) + NALU extraction      ffmpeg_video_source.py:26-48 / packets/nalu_parser.py
  → NALU type + priority classification        packets/priority_classifier.py
  → fragmentation into NALUPacket             packets/packetizer.py:31-68
  → priority scheduling                       packets/packetScheduler.py
  → UdpTransport (hardcoded)                  capture.py:20 (`transport = UdpTransport()`)
  → UDP datagram (24 B VideoHeader + payload) transport/udp_transport.py
  → localhost / network (127.0.0.1:65432)
  → reciever_nalu.py: UDP socket → inline header parse → inline reassembly → ffplay
```

Key properties of the baseline `VERIFIED` (all still hold):

- Custom binary `VideoHeader` of **24 bytes**, big-endian struct `'!IIHHBBQH'`
  (`transport/video_header.py:15-30`).
- Datagram ceiling **1200 bytes** (`UDP_SAFE_PAYLOAD`), max payload **1176 bytes**
  (`config.py:16-19`).
- Transport abstraction **already existed**: `Transport` ABC with
  `send_packet(NALUPacket) -> int` and `close()` (`transport/transport.py`);
  `UdpTransport` implemented it.
- H.264 Annex B framing with `00 00 00 01` start codes in the receiver before
  feeding ffplay (`reciever_nalu.py:67`).

## What problem the integration addresses

The baseline could only transmit over a UDP network. The project wanted to carry
the same video datagrams over a **radio link (IQ / SDR) via GNU Radio**. GNU
Radio consumes and produces messages as **PDUs** (`pmt::cons(dict, u8vector)`
between GNU Radio blocks), commonly exchanged with the outside world over ZMQ.
To send the H.264 datagrams over the air, Python had to:

1. keep the exact same datagram format (24 B header + payload ≤ 1200 B) `VERIFIED`;
2. wrap that datagram in the GNU Radio PMT serialization so `ZMQ PULL/PUSH
   Message Source/Sink` blocks accept it `VERIFIED` (README_FLOWGRAPHS.md:59-70);
3. expose a switch so the app can use either UDP or the radio path without
   touching the pipeline `VERIFIED` (transport_factory.py, config.py:13).

## Major components added `VERIFIED` (all in commit range `19d88c8..1abeb05`)

| Component | Responsibility |
|---|---|
| `transport/datagram.py` | Shared `build_datagram` / `parse_datagram` (24 B + ≤1200 B), DRY across UDP and radio |
| `packets/reassembler.py` | Shared `Reassembler.feed` (out-of-order, duplicates, interleaved NALUs; handoff cases A–F) |
| `transport/transport_factory.py` | `get_transport()` → `UdpTransport` or `ZMQPduTransport` per `config.TRANSPORT` |
| `radio/` package | Isolated GNU Radio-facing modules |
| `radio/config_radio.py` | Endpoints `tcp://127.0.0.1:5555` (TX) / `:5556` (RX), bind/connect roles, RX timeout |
| `radio/pmt_codec.py` | GNU Radio **PMT** codec, bit-compatible with `pmt::serialize_str(cons(dict,u8vector))` |
| `radio/zmq_pdu_transport.py` | `ZMQPduTransport(Transport)`: PUSH bind 5555, sends `encode_u8vector_pdu(build_datagram(packet))` |
| `radio/zmq_pdu_receiver.py` | `ZMQPduReceiver`: PULL connect 5556, decode PDU → parse datagram → `Reassembler` → ffplay |
| `radio/reciever_radio.py` | Executable RX entry point (≈ `reciever_nalu.py` for the radio path) |
| `radio/flowgraphs/tx_bladerf.grc`, `rx_hackrf.grc`, `README_FLOWGRAPHS.md` | **Reference** GNU Radio flowgraphs (BladeRF TX / HackRF RX) + manual hardware checklist |
| `requirements-radio.txt` | `pyzmq>=25.0` (radio path only) |

## Existing components refactored (behavior preserved) `VERIFIED`

| Component | Change |
|---|---|
| `transport/udp_transport.py` | `send_packet` now delegates to `build_datagram` (keeps DEBUG print + `ValueError`) |
| `reciever_nalu.py` | Inline reassembly (`extract_nalu_from_incoming_byte`) and global `pending_nalus` replaced by shared `Reassembler` |
| `capture.py` | `UdpTransport()` → `get_transport()` factory call |
| `config.py` | Added `TRANSPORT` constant (committed default `"udp"`) |
| `README.md` | Added "Modo radio (GNU Radio + SDR)" section |

## What remained compatible / unchanged `VERIFIED`

- `transport/transport.py` ABC — unchanged between `main` and branch.
- The 24-byte header contract and the 1200-byte ceiling — unchanged.
- The TX pipeline (capture → parse → classify → packetize → schedule) — unchanged.
- ffplay invocation, start-code framing, metrics recording — unchanged.
- UDP route fully intact: with `TRANSPORT = "udp"`, behavior is identical.

## New dependencies `VERIFIED`

| Dependency | Where | Purpose |
|---|---|---|
| `pyzmq>=25.0` | `requirements-radio.txt` | ZMQ PUSH/PULL sockets for the radio path only |
| GNU Radio 3.10+ (system) | `radio/flowgraphs/README_FLOWGRAPHS.md:41-47` | Runtime for the `.grc` flowgraphs (not installed in this environment) |
| gr-bladeRF (TX), gr-osmosdr (RX) | same | SDR hardware drivers for the reference flowgraphs |

## Before / After table

| Area | Before | After | Reason |
|---|---|---|---|
| Datagram construction | Inlined per transport (`udp_transport.py`) | Shared `transport/datagram.py` | DRY; radio transport needs the same bytes |
| Header parsing | Inlined in `reciever_nalu.py` | Shared `parse_datagram` + `Reassembler` | Radio RX reuses identical logic |
| Reassembly | `reciever_nalu.py` local function + global dict | `packets/reassembler.py` (class, per-instance) | Extract shared component; testable in isolation |
| Transport selection | Hardcoded `UdpTransport()` in `capture.py` | `get_transport()` factory (config.TRANSPORT) | Plug-in UDP or radio without pipeline changes |
| Radio/SDR integration | None | `radio/` package + ZMQ PDU + reference `.grc` flowgraphs | Transmit video datagrams over GNU Radio/SDR |
| ZMQ | None | PUSH/PULL on 5555/5556, GNU Radio PMT PDU wire | GNU Radio message exchange protocol |
| Wire compatibility | UDP socket | Same 24 B + ≤1200 B bytes, wrapped in GNU Radio PDU | Keep the binary contract intact across media |
| Dependency footprint | stdlib only | + pyzmq for radio path; GNU Radio/SDR are external | SDR link requires GNU Radio stack |
| Default transport | UDP (implicit) | `TRANSPORT = "udp"` committed; **working tree currently `"radio"`** (uncommitted) | Radio becomes the primary mode going forward; UDP remains the fallback/nominal default |

## Key facts for the reader

- The GNU Radio integration lives **entirely in the `radio/` package** plus the
  factory/datagram/reassembler refactors; `main` is untouched `VERIFIED`.
- ZMQ carries the **PMT-serialized PDU**, whose payload is the **same datagram**
  Python would send over UDP `VERIFIED` (transport/datagram.py:5-19,
  radio/zmq_pdu_transport.py:25-29).
- The SDR link itself (BladeRF TX / HackRF RX) is described only by reference
  `.grc` files; it is **not proven by tests** in this repository
  `PLAN_ONLY`/`UNPROVEN` (radio/flowgraphs/README_FLOWGRAPHS.md:72-81).