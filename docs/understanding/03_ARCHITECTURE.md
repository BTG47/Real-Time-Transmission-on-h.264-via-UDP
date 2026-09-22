# 03 — Architecture (C4 view)

> Scope: this repository (branch `blade_protocol_adaptation`, working tree with
> uncommitted `TRANSPORT = "radio"`). Every claim is tagged:
> `VERIFIED` (read from code/test), `INFERRED`, `PLAN_ONLY` (only in
> `PLAN_RADIO_ZMQ.md`), `UNPROVEN` (no evidence). Rule: **the code is the truth**;
> the `.grc` files are reference artifacts.

## 1. System boundary

**In scope (in this repo):** the Python H.264 real-time streaming prototype:
capture/send pipeline (`capture.py`), ffmpeg source (`ffmpeg_video_source.py`),
NALU processing (`packets/`), transport abstraction (`transport/`), radio path
(`radio/`), metrics (`metrics/`) and configuration (`config.py`). Both receivers
(`reciever_nalu.py`, `radio/reciever_radio.py`) belong to the system.

**External (runtime dependencies, outside the repo):**

| Entity | Role | Evidence |
|---|---|---|
| Camera `/dev/video0` (v4l2) | Raw video source | `VERIFIED` ffmpeg_video_source.py:8-10 |
| **ffmpeg** binary (subprocess) | Encodes H.264 (libx264, ultrafast, zerolatency) to a pipe | `VERIFIED` ffmpeg_video_source.py:7-16 |
| **GNU Radio runtime** 3.10+ | Runs the flowgraphs (not installed here) | `VERIFIED` README_FLOWGRAPHS.md:41-47; `import gnuradio` fails in this environment |
| **BladeRF / HackRF (SDR)** | RF interface | `PLAN_ONLY` / `UNPROVEN` (described only by `.grc`) |
| **ffplay** (subprocess) | Plays the received H.264 | `VERIFIED` reciever_nalu.py:13-20, radio/zmq_pdu_receiver.py:57-60 |
| **UDP network** (loopback) | Legacy path medium | `VERIFIED` config.py:11-12, reciever_nalu.py:22-24 |

Boundary note: ffmpeg and ffplay are external binaries but are **spawned and
driven by this repo's code**; their subprocesses are part of system behavior,
while the camera and the screen/terminal are external actors.

## 2. Containers (deployables)

| Container | Entry point | Responsibility | Evidence |
|---|---|---|---|
| Sender | `capture.py` | Capture → parse → classify → packetize → schedule → send loop | `VERIFIED` capture.py:26-57 |
| UDP receiver | `reciever_nalu.py` | UDP socket → parse datagram → `Reassembler` → ffplay | `VERIFIED` reciever_nalu.py:22-81 |
| Radio receiver | `radio/reciever_radio.py` | `main()` of `zmq_pdu_receiver`: PULL → PMT → datagram → reassembler → ffplay | `VERIFIED` radio/reciever_radio.py:1-4, radio/zmq_pdu_receiver.py:56-84 |
| GNU Radio TX flowgraph | `radio/flowgraphs/tx_bladerf.grc` | ZMQ → PDU → GMSK → BladeRF (**reference** artifact) | `VERIFIED` tx_bladerf.grc:56-160 |
| GNU Radio RX flowgraph | `radio/flowgraphs/rx_hackrf.grc` | HackRF → GMSK → PDU → ZMQ (**reference** artifact) | `VERIFIED` rx_hackrf.grc:56-184 |

A single Python runtime hosts the sender and both receivers; they do not share a
process (each is an independent interpreter) `VERIFIED` (separate entry points).

## 3. Sender components (component view)

Emission pipeline, in order (all `VERIFIED` unless noted):

```
Camera (/dev/video0)
  → ffmpeg libx264 (pipe)               ffmpeg_video_source.py:7-16
  → read_chunk (4096 B)                 ffmpeg_video_source.py:26-37, config.py:8
  → extract_nalus_chunk (+remainder buffer) ffmpeg_video_source.py:39-48, packets/nalu_parser.py:53-79
  → nalu_type / name                    packets/nalu_parser.py:82-95
  → obtain_classification_nalu          packets/priority_classifier.py:10-22 (+config.py:22-25)
  → Paketizer.packetize (fragments ≤1176 B)  packets/packetizer.py:31-68
  → PacketScheduler (4 priority queues) packets/packetScheduler.py:15-42
  → transport.send_packet              capture.py:54 (via get_transport())
  → SenderMetrics.record                metrics/sender_metrics.py:30-61
```

- `NALUPacket` (logical pre-network packet) carries `packet_sequence`,
  `nalu_id`, `fragment_index`, `fragment_count`, `nal_type`, `priority`,
  `timestamp_ns`, `payload` `VERIFIED` packets/packetizer.py:7-16.
- Priorities: CRITICAL = SPS/PPS (types 7,8) → HIGH = IDR (5) → NORMAL (1)/other
  → LOW = SEI (6) `VERIFIED` config.py:22-25.
- The classifier imports `config` **inside** the function (avoids a circular
  import with `config.py → priority_classifier`) `VERIFIED`
  packets/priority_classifier.py:11.

## 4. Transport abstraction (the seam)

`transport/transport.py` defines the ABC:

```python
class Transport(ABC):
    @abstractmethod
    def send_packet(self, packet: NALUPacket) -> int: ...
    @abstractmethod
    def close(self) -> None: ...
```
`VERIFIED` transport/transport.py:4-12.

- `transport_factory.get_transport()` selects per `config.TRANSPORT` `VERIFIED`
  (transport/transport_factory.py:3-13):
  - `"radio"` → `ZMQPduTransport` (ImportError → `RuntimeError` pointing at
    `requirements-radio.txt`).
  - anything else → `UdpTransport()`.
- Both implement `Transport` `VERIFIED`: `UdpTransport`
  (transport/udp_transport.py:8-34), `ZMQPduTransport`
  (radio/zmq_pdu_transport.py:11-37).
- Datagram construction is **shared** in `transport/datagram.py`
  (`build_datagram`/`parse_datagram`) `VERIFIED` transport/datagram.py:5-19; used
  by UDP, radio TX, UDP receiver and radio receiver.

### Wire format (shared across routes)

- `VideoHeader` of **24 bytes**, big-endian `struct.pack('!IIHHBBQH', …)` =
  `packet_sequence:4, nalu_id:4, fragment_index:2, fragment_count:2, nal_type:1,
  priority:1, timestamp_ns:8, payload_size:2` `VERIFIED`
  transport/video_header.py:15-30.
- Datagram = header + payload. Ceiling **1200 B** (`UDP_SAFE_PAYLOAD`); max
  payload **1176 B** (`SIZE_MAX_PACKET`); `build_datagram` raises `ValueError`
  when exceeded `VERIFIED` config.py:16-19, transport/datagram.py:5-13.

## 5. Old route — UDP (baseline on `main`)

TX: `capture.py:54` → `UdpTransport.send_packet` → `build_datagram` →
`sendto((SERVER_IP, SERVER_PORT))` to `127.0.0.1:65432` `VERIFIED`
transport/udp_transport.py:13-21, config.py:11-12.

RX: `reciever_nalu.py` creates a UDP socket, **binds** `127.0.0.1:65432`
(`VERIFIED` :22-24), `recvfrom(UDP_SAFE_PAYLOAD)` (:45), splits header
(`obtain_header_video`, :35-40), records metrics, feeds `Reassembler.feed`
(:63); when a NALU completes it writes it to ffplay's stdin with the *start code*
`00 00 00 01` (:66-68) and also to `reconstructed2` (:78-80).

`Reassembler` tolerates out-of-order fragments, duplicates and interleaving keyed
by `nalu_id`; on completion it rebuilds joining `fragments[index]` in order
`VERIFIED` packets/reassembler.py:12-37.

## 6. New route — GNU Radio over ZMQ PDU

Radio TX: `capture.py:54` → `ZMQPduTransport.send_packet`
(radio/zmq_pdu_transport.py:25-29):

1. `build_datagram(packet)` → same 24 B + payload datagram (wire intact).
2. `encode_u8vector_pdu(datagram)` → serialized **PMT/PDU**
   `pmt::serialize_str(cons(dict, u8vector))` `VERIFIED` radio/pmt_codec.py:13-15,
   README_FLOWGRAPHS.md:59-70. Byte prefix `07 06 0a 00 <len:u32 BE> 01 00`
   + payload `VERIFIED` test/test_pmt_codec.py:5-12.
3. Sends over a **ZMQ PUSH socket that binds** `tcp://127.0.0.1:5555`
   `VERIFIED` radio/config_radio.py:1-3, radio/zmq_pdu_transport.py:19-23.

Radio RX: `ZMQPduReceiver` opens **ZMQ PULL that connects** to
`tcp://127.0.0.1:5556` (`VERIFIED` radio/config_radio.py:2,4,
radio/zmq_pdu_receiver.py:22-27). Loop `run_recv_loop`
(radio/zmq_pdu_receiver.py:44-54): `recv_timeout` → `decode_pdu_data`
(pmt_codec.py:72-81) → `parse_datagram` → `Reassembler.feed` → `on_nalu` (writes
to ffplay with start codes and to `reconstructed_rf`). `reciever_radio.py` is the
entry point `VERIFIED`.

**Endpoints and roles (important; corrected in commit `1abeb05`):**

| Port | Who binds | Who connects | `VERIFIED` |
|---|---|---|---|
| 5555 (TX) | Python `ZMQPduTransport` (PUSH) config_radio.py:3 | flowgraph `tx_bladerf.grc` (ZMQ PULL, mode=connect) tx_bladerf.grc:70-72 | yes |
| 5556 (RX) | flowgraph `rx_hackrf.grc` (ZMQ PUSH, mode=bind) rx_hackrf.grc:154-157 | Python `ZMQPduReceiver` (PULL) config_radio.py:4 | yes |

### GNU Radio as an external subsystem

The actual block chains in the `.grc` files are (`VERIFIED` from the XML):

TX `tx_bladerf.grc` (description :19-21):
```
ZMQ PULL Message Source   (tcp://127.0.0.1:5555, timeout=100, mode=connect)
  → PDU to Tagged Stream  (byte, len_tag_key=packet_len)   :83-96
  → GMSK Mod              (samples/symbol=8, gain=1.0)      :98-123
  → BladeRF sink          (20e6 sps, 2.45 GHz, gain 40)     :125-142
```
RX `rx_hackrf.grc` (:19-21):
```
osmosdr source (hackrf, complex, 20e6, 2.45 GHz)            :56-85
  → GMSK Demod           (samples/symbol=8)                 :87-124
  → Tagged Stream to PDU (byte, packet_len)                 :126-139
  → ZMQ PUSH Message Sink (tcp://127.0.0.1:5556, bind)      :141-166
```

The RF link (2.45 GHz / 20 Msps GMSK between BladeRF and HackRF) is only
described by these reference artifacts and a manual checklist `UNPROVEN`
README_FLOWGRAPHS.md:72-81. The `.grc` files pass a **well-formed XML** test
(`VERIFIED` test/test_flowgraphs.py:6-11), but that does not prove the RF link
(`UNPROVEN`).

## 7. Configuration and working-tree divergence

`config.py:13` is the switch:

```python
TRANSPORT = "radio"   # "udp" para el baseline UDP; "radio" para GNU Radio vía ZMQ
```
`VERIFIED` config.py:13. The committed value on `main`/branch was `"udp"`; the
current working tree has **uncommitted** `TRANSPORT = "radio"` `VERIFIED` (see
`git diff config.py`; active branch `blade_protocol_adaptation`). Consequence: if
`capture.py` were launched now it would use the radio path; to run the baseline
you must set `"udp"` again.

## 8. Metrics

- Sender: `SenderMetrics.record` accumulates payload/wire bytes, bitrates,
  packets, NALUs, fragmented count, per-priority and per-NALU-type counters;
  `summary()` prints on exit `VERIFIED` metrics/sender_metrics.py:30-77.
- Receiver: `RecieverMetrics.record` measures out-of-order sequences, duplicates
  (sequence set), reconstructed/incomplete NALUs and bitrates `VERIFIED`
  metrics/reciever_metrics.py:38-114.
- No RF/GNU-Radio-layer metrics exist (`UNPROVEN`); only Python end-to-end ones.

## 9. Assumptions and inferences

- `INFERRED`: sending PDUs over a PUSH/TCP ZMQ socket delivers complete messages
  (PDU = 1 message); `Reassembler` assumes whole frames (`VERIFIED` in the
  loopback, see §11).
- `VERIFIED` (design inference): the wire `07 06 0a 00 <len> 01 00` was rebuilt
  from the implementation and is consistent with the GNU Radio
  `cons(dict, u8vector)` format `VERIFIED` pmt_codec.py:13-15, test_pmt_codec.py.
- `INFERRED`: `ffmpeg -tune zerolatency` is chosen to minimize encoder latency for
  real-time streaming (design intent, not measured here).
- `VERIFIED` (currently dead code): `packets/packetizer.py:71-87` (`update_flag`,
  flags 0-4 semantics documented) has **no callers** (grep);
  `UdpTransport.send_single_header` (transport/udp_transport.py:23-31) is only
  referenced commented-out in capture.py:65; `transport/sender_nalu.py` is fully
  commented.
- `INFERRED`: reconstruction is keyed on `fragment_index`/`fragment_count`, not
  on the flags; the flags are an inactive earlier design
  (packets/reassembler.py:12-37).

## 10. Open questions

1. Does TX PUSH (bind 5555) + flowgraph PULL (connect) start in the right order
   on real hardware? README_FLOWGRAPHS.md:52-57 give a suggested order
   (bind before connect) `VERIFIED` as repo text; actual hardware startup
   `UNPROVEN`.
2. Does the H.264 payload actually survive GMSK without desync at 20 Msps? Only
   a manual checklist exists → `UNPROVEN`.
3. Is there re-framing or loss in the `.grc` when the SDR has no signal? No
   evidence.
4. Are `reconstructed2` / `reconstructed_rf` written as debug aids or as
   deliverables?
5. Is the working-tree `TRANSPORT = "radio"` divergence intentional (current
   state) or accidental?

## 11. Verification in this environment

- Full suite: **42 tests, OK** (`python3 -m unittest discover -s test`),
  including PMT round-trip, ZMQ inproc TX→RX→Reassembler loopback
  (test_zmq_loopback_integration.py:19-51) and well-formed `.grc` XML —
  `VERIFIED` (executed, pyzmq 27.2).
- GNU Radio **not installed** in this environment (`import gnuradio` raises
  ImportError) → flowgraphs validated only as XML `UNPROVEN` for runtime.
- `requirements-radio.txt` = `pyzmq>=25.0` `VERIFIED`.

## Diagrams

- `diagrams/system-context.mmd` — C4 system context.
- `diagrams/module-dependencies.mmd` — Python module dependency graph (the
  `Transport` ABC is the seam; yellow = seam, blue = radio path).