# 07 — Module guide (real files only)

Purpose: quick orientation for every **real** source file in the repo (no tests, no plans). For flows, wire format and before/after, see `04_TX_FLOW.md`, `05_RX_FLOW.md`, `06_PACKET_AND_PDU_FORMAT.md`, `02_BEFORE_AFTER.md`.
Evidence legend: `VERIFIED` = this author read the cited `file:line` on the current tree · `INFERRED` · `UNPROVEN`.
Current selector: `config.py:13` `TRANSPORT = "radio"` (working tree; the committed default is `"udp"`, see note in §Config).

---

## Index

| File | Layer | One-liner | Delta vs UDP baseline |
|---|---|---|---|
| `capture.py` | entry | TX orchestration loop | loop body identical; `get_transport()` seam flipped (`:20`) |
| `reciever_nalu.py` | entry | UDP RX loop (baseline) | unchanged |
| `radio/reciever_radio.py` | entry | radio RX entry → `main()` | new |
| `config.py` | config | all tunables + derived sizes | `TRANSPORT` switch added |
| `radio/config_radio.py` | config | ZMQ endpoints/timeouts | new |
| `ffmpeg_video_source.py` | source | ffmpeg child + buffered chunks | unchanged |
| `packets/nalu_parser.py` | packets | Annex-B start-code parser | unchanged |
| `packets/priority_classifier.py` | packets | `Priority` enum + maps | unchanged |
| `packets/packetizer.py` | packets | NALU → `NALUPacket` fragments | unchanged |
| `packets/packetScheduler.py` | packets | 4-priority deques | unchanged |
| `packets/reassembler.py` | packets | fragment reassembly | unchanged; used by both receivers |
| `transport/transport.py` | transport | `Transport` ABC | existed pre-branch, unchanged |
| `transport/udp_transport.py` | transport | UDP `send_packet` | unchanged |
| `transport/datagram.py` | transport | `build_datagram` / `parse_datagram` | unchanged; radio reuses |
| `transport/video_header.py` | transport | 24-B `VideoHeader` struct | unchanged |
| `transport/transport_factory.py` | transport | `get_transport()` selector | new |
| `transport/sender_nalu.py` | transport | legacy sender (all commented out) | dead code |
| `radio/zmq_pdu_transport.py` | radio | `ZMQPduTransport` (PUSH) | new |
| `radio/zmq_pdu_receiver.py` | radio | `ZMQPduReceiver` + loop + `main` | new |
| `radio/pmt_codec.py` | radio | PMT encode/decode codec | new |
| `radio/flowgraphs/tx_bladerf.grc` | radio | TX flowgraph (GNU Radio) | new (XML ref) |
| `radio/flowgraphs/rx_hackrf.grc` | radio | RX flowgraph (GNU Radio) | new (XML ref) |
| `metrics/sender_metrics.py` | metrics | TX counters/bitrates | unchanged |
| `metrics/reciever_metrics.py` | metrics | RX counters | unchanged; radio RX does not use it |
| `radio/__init__.py` | pkg | empty | new |

---

## Entry points

### `capture.py`
- **Why/what:** TX pipeline driver — read camera bytes, extract NALUs, classify, packetize, schedule, send (`capture.py:30-56`). Runs forever; stops only on `KeyboardInterrupt` (`:59`).
- **Key code:** module-level `transport = get_transport()` (`:20`), `Paketizer()` (`:21`), `PacketScheduler()` (`:22`); loop: `source.read_chunk()` (`:31`) → `source.obtain_nalus_from_chunk` (`:32`) → `nalu_type`/`nalu_type_name` (`:36-37`) → `obtain_classification_nalu` (`:38`) → `logicPacket.packetize` (`:45`) → `schedule.enqueue` (`:47`) → `schedule.dequeue` per NALU (`:48-49`) → `transport.send_packet` (`:54`) → `sender.record(packet, sent_data_size)` (`:56`).
- **I/O:** in: stdin/ffmpeg (implicit); out: ZMQ 5555 (radio) or UDP 65432 (udp); prints `SenderMetrics.summary()` at exit (`:62`).
- **Deps:** `nalu_parser`, `packetizer`, `ffmpeg_video_source`, `transport_factory`, `priority_classifier`, `packetScheduler`, `sender_metrics`, `config` (`:1-9`).
- **Evidence:** `VERIFIED` (read); full trace in `04_TX_FLOW.md` Stages 0–9.
- **Notes:** `send_packet` return value (datagram length) is the only metric input (`:54-56`); there is no explicit end-of-stream packet (comment `:63-72`).

### `reciever_nalu.py`
- **Why/what:** baseline UDP receiver — bind 65432, reassemble, play via ffplay, dump `reconstructed2` on a 5 s socket timeout (`:43-81`).
- **Key code:** `socket.bind((SERVER_IP, SERVER_PORT))` (`:23`), `settimeout(5.0)` (`:24`), `recvfrom(UDP_SAFE_PAYLOAD)` (`:45`), `obtain_header_video` manual 24-B slice (`:35-40,56`), `reassembler.feed` (`:63`), ffplay stdin (`:66-68`), file `reconstructed2` (`:78-80`).
- **Deps:** `video_header`, `reciever_metrics`, `nalu_parser`, `config`, `reassembler` (`:1-7`).
- **Evidence:** `VERIFIED`.

### `radio/reciever_radio.py`
- **Why/what:** 3-line launcher: `from radio.zmq_pdu_receiver import main; main()` (`:1-4`).
- **Evidence:** `VERIFIED`.

---

## Config

### `config.py`
- **Key code:** `DEBUG=False` (`:5`); `LECTURE_SIZE=4096` (`:8`); UDP `SERVER_IP='127.0.0.1'`, `SERVER_PORT=65432` (`:11-12`); **`TRANSPORT="radio"`** (`:13`, comment documents both modes + `requirements-radio.txt`); derived sizes `REAL_HEADER_SIZE=24`, `UDP_SAFE_PAYLOAD=1200`, `SIZE_MAX_PACKET=1176` (`:16-19`); priority value lists `CRITICAL_VALUES/HIGH_VALUES/NORMAL_VALUES/LOW_VALUES` (`:22-25`).
- **Evidence:** `VERIFIED`. **Divergence flag:** the committed default is `"udp"`; the working tree has `"radio"`. The runtime value decides the wire for `capture.py` but **not** for `reciever_nalu.py` (UDP receiver always binds 65432) — so launching the wrong receiver for the current mode silently produces no data. `INFERRED` consequence.
- Note: `import struct` (`:3`) is unused in this file as of this tree.

### `radio/config_radio.py`
- **Key code:** `ZMQ_TX_ENDPOINT="tcp://127.0.0.1:5555"` (`:1`), `ZMQ_RX_ENDPOINT="tcp://127.0.0.1:5556"` (`:2`), `ZMQ_TX_BIND=True` (`:3`), `ZMQ_RX_CONNECT=True` (`:4`), `ZMQ_RCVTIMEO_MS=5000` (`:5`).
- **Role split (TX):** Python binds 5555, flowgraph connects. (RX): flowgraph binds 5556, Python connects. `VERIFIED` (`zmq_pdu_transport.py:18-23`, `zmq_pdu_receiver.py:21-27`).

---

## Source / capture

### `ffmpeg_video_source.py`
- **Why/what:** owns the ffmpeg child (`:20`) producing Annex-B H.264 on stdout; buffers chunked reads; NALU-safe chunking.
- **Key code:** cmd list (`:7-16`); `read_chunk` protocol: stdout fetch + `read(LECTURE_SIZE)` + `None` on empty (`:26-37`); `obtain_nalus_from_chunk` appends → `extract_nalus_chunk` → keeps tail via `stream_buffer[-remain_buffer:]` (`:39-48`); `close()` (`:50-51`).
- **Evidence:** `VERIFIED`.
- **Gotcha (inherited, unchanged):** `close()` does `self.process.terminate` — a bound method fetch, never invoked (missing `()`), `:51`. `VERIFIED`.

---

## Packets layer («packets/»)

### `packets/nalu_parser.py`
- **Key code:** `START_CODE_3`/`START_CODE_4` (`:5-6`); module-level `nal_units` (`:7`) — unused by current paths `INFERRED`; `recover_start_positions` scan `while i < len(data)-3` (`:15-30`); legacy `extract_nalus` (`:32-51`); `extract_nalus_chunk` — needs ≥2 start codes (`:59-60`), holds back last NALU (`:75-78`), returns `(list, remaining)` (`:79`); `nalu_type` = `bytes(nalu)[0] & 0x1F` (`:82-85`); `nalu_type_name` dict (`:87-95`).
- **I/O:** `bytes` → `(list[bytes], int)`.
- **Gotcha:** empty NALU (two adjacent start codes) → `IndexError` at `:85`. Unchanged.

### `packets/priority_classifier.py`
- **Key code:** `Priority(IntEnum)` 0..3 = CRITICAL/HIGH/NORMAL/LOW (`:4-8`); `obtain_classification_nalu` maps via `config` lists, default NORMAL (`:10-22`).
- **Note:** `priority` is serialized as 1 byte in `VideoHeader` (`video_header.py:11,22`) — IntEnum packs as its int value, roundtrips via `struct.unpack` as `int` (not `Priority`) `INFERRED`; downstream only compares against `Priority.X`, and `Priority(1)==1` is true, so behavior holds. `VERIFIED` equivalence, `INFERRED` on intent.

### `packets/packetizer.py`
- **Key code:** `NALUPacket` dataclass (`:6-16`); `Paketizer.__init__` state `packet_sequence=0`, `nalu_id=0` (`:21-23`); `packetize` splits at `SIZE_MAX_PACKET` (`:41-43`), `fragment_count=len(fragments)` (`:46`), `nalu_id += 1` once (`:49`), `time.monotonic_ns()` once (`:50`), `packet_sequence += 1` per fragment, never reset (`:54`), builds `NALUPacket`s (`:57-66`); legacy `update_flag` (`:71-87`, unused).
- **I/O:** `(nalu, nalu_type, priority) → list[NALUPacket]`.
- **Evidence:** `VERIFIED` (see `test_datagram.py`/`test_zmq_pdu_transport.py` for the 27-B example).

### `packets/packetScheduler.py`
- **Key code:** four `deque[list[NALUPacket]]` (`:9-13`); `enqueue` routes on `packets[0].priority`, unknown → NORMAL (`:15-30`); `dequeue` strict CRITICAL→HIGH→NORMAL→LOW or `None` (`:32-42`); `has_packets` (`:44-54`).
- **Important cadence detail:** units are **whole fragment-lists per NALU**, so a NALU's fragments are never interleaved with another NALU at this layer. `capture.py` enqueues+dequeues once per processed NALU (`capture.py:45-49`). `VERIFIED`.

### `packets/reassembler.py`
- **Key code:** `pending_nalus: dict[str, {...}]` (`:5-6`, actually keyed by `nalu_id` — comment field name aside); `pending_count` (`:8-10`); `feed` validations → `None` (count ≤ 0 `:17-18`, index out of range `:19-20`, `payload_size != len(payload)` `:21-22`, mismatched `fragment_count` `:28-29`), then store `fragments[index] = payload` (duplicate index overwrites, `:31`), complete when `len==count` is joined in index order and deleted (`:33-36`).
- **Limitation:** no eviction; lost fragment → entry leaks forever. `VERIFIED` (no cleanup code); consequence `INFERRED`.

---

## Transport layer («transport/»)

### `transport/transport.py`
- **Why/what:** `Transport(ABC)` with `send_packet(NALUPacket) -> int` and `close()` (`:4-12`). Existed on `main` before the branch; unchanged. `VERIFIED`.

### `transport/video_header.py`
- **Key code:** `VideoHeader` dataclass, 8 fields = 24 B total (`:5-13`); `to_bytes` = `struct.pack('!IIHHBBQH', …)` BE (`:15-25`); `from_byte` unpack mirror (`:26-30`).
- **Evidence:** `VERIFIED` — see `06_PACKET_AND_PDU_FORMAT.md` §1/§6.

### `transport/datagram.py`
- **Key code:** `build_datagram` = header + payload, rejects `> UDP_SAFE_PAYLOAD` with Spanish `ValueError` (`:5-13`); `parse_datagram` rejects `< REAL_HEADER_SIZE` and splits at 24 (`:15-19`).
- **Note:** `parse_datagram` does not verify `payload_size` vs `len(payload)` — Reassembler does. `VERIFIED`.

### `transport/udp_transport.py`
- **Key code:** `UdpTransport(Transport)`; socket UDP (`:10-11`); `send_packet` = `build_datagram` → optional DEBUG header print (`:15-19`) → `sendto((SERVER_IP, SERVER_PORT))` (`:20`) → returns `len(data_to_send)` (`:21`); legacy `send_single_header` (`:23-31`); `close` (`:33-34`).
- **Evidence:** `VERIFIED`.

### `transport/transport_factory.py`
- **Key code:** `get_transport()` reads `config.TRANSPORT` (`:4`); `"radio"` → lazy `import radio.zmq_pdu_transport` with `RuntimeError` + install hint on missing pyzmq (`:5-12`); anything else → `UdpTransport()` (`:13`).
- **Note:** `import transport.udp_transport` at module top (`:1`) pulls in `config`. Unknown transport strings silently default to UDP (`INFERRED` as intended).

### `transport/sender_nalu.py`
- **Why/what:** legacy hand-rolled sender; **entire body commented out** (`:1-44`). Dead code — indicates the old pre-abstraction wire design. Do not rely on it. `VERIFIED`.

---

## Radio layer («radio/»)

### `radio/zmq_pdu_transport.py`
- **Key code:** pyzmq-tolerant import (`zmq = None` on ImportError `:1-4`); `ZMQPduTransport(Transport)` with injectable endpoint/context/socket/bind (`:12-23`) — default PUSH + **bind** (`:19-21`); `send_packet` = `build_datagram` → `encode_u8vector_pdu` → `socket.send(frame)` → return `len(datagram)` (`:25-29`); `close` linger 0 + context term (only if owned) (`:31-37`).
- **Evidence:** `VERIFIED` (tests inject fakes; loopback test in `test_zmq_loopback_integration.py`).

### `radio/zmq_pdu_receiver.py`
- **Key code:** `TIMEOUT_EXCEPTION = getattr(zmq, "Again", TimeoutError)` (`:12`); `ZMQPduReceiver` default PULL + **connect** + `RCVTIMEO` (`:14-27`); `recv_timeout` → `None` on timeout else `decode_pdu_data(frame)` (`:29-34`); `run_recv_loop(rx, reassembler, on_nalu, on_timeout)` (`:44-54`); `main` sets up ffplay (`:56-62`), `on_nalu` writes start code + NALU to stdin (`:64-68`), `on_timeout` closes, terminates, writes `reconstructed_rf` (`:70-78`), `rx.close()` in `finally` (`:80-84`).
- **Gotcha:** `PmtDecodeError`/`ValueError` are not caught in `run_recv_loop` (`:46-54`) — one malformed frame crashes the loop. `VERIFIED`.

### `radio/pmt_codec.py`
- **Key code:** PMT tags `PST_*` (`:3-5`); `PmtDecodeError(ValueError)` (`:8-9`); `_MAX_DEPTH=64` (`:11`) — off-plan guard; `encode_u8vector_pdu` = `07 06 | 0a 00 | u32 len | 01 00 | payload` (`:13-15`); strict `_read_exact` (`:17-21`); recursive `_parse` (`:23-70`) — full-format decode (NULL, TRUE/FALSE, SYMBOL, INT32/INT64/UINT64/DOUBLE, PAIR/DICT with depth guard `:44-49`, u8vector `:50-59`, TUPLE/VECTOR `:60-69`); `decode_pdu_data` requires full consumption + walks cdr chain to a final `bytes` (`:72-81`).
- **Evidence:** `VERIFIED` (`test_pmt_codec.py`).
- **Note:** encode path only covers `cons(nil, u8vector)`; the `_parse` decoder is more general. The emitted car is `PST_NULL` (`06`), not `PST_DICT` — README's `cons(dict, u8vector)` wording is looser; code wins.

### `radio/flowgraphs/tx_bladerf.grc` (reference XML)
- **Chain:** `zeromq_pull_msg_source` connect 5555 (`:55-81`) → `blks2.pdu_to_tagged_stream` byte/`packet_len` (`:82-96`) → `digital.gmsk_mod` sps 8 (`:97-123`) → `bladerf_sink` 20 Msps / 2.45 GHz / gain 40 (`:124-142`); connections `:143-160`.
- **Evidence:** block graph `VERIFIED` as XML (only well-formedness tested, `test_flowgraphs.py:6-10`); end-to-end RF `UNPROVEN` (`README_FLOWGRAPHS.md:72-81`).

### `radio/flowgraphs/rx_hackrf.grc` (reference XML)
- **Chain:** `osmosdr_source` hackrf 20 Msps / 2.45 GHz (`:55-85`) → `digital.gmsk_demod` sps 8 (`:86-124`) → `blocks.tagged_stream_to_pdu` byte/`packet_len` (`:125-139`) → `zeromq_push_msg_sink` **bind** 5556 (`:140-166`); connections `:167-184`.
- **Evidence:** same split as TX.

---

## Metrics («metrics/»)

### `metrics/sender_metrics.py`
- **Key code:** `SenderMetrics` counters (`:8-29`); `record(packet, sent_data_size)` — negative size ignored (`:31-32`), counts packets/payload/wire bytes, NALUs when `fragment_index == 0` (`:45-46`), fragmented count (`:47-49`), priority/type tallies (`:52-55`), bitrates over `elapsed_seconds` (`:58-61`); `summary()` Spanish printout (`:63-77`).
- **Evidence:** `VERIFIED`. Used only by `capture.py`.

### `metrics/reciever_metrics.py`
- **Key code:** `RecieverMetrics` with sequence/duplicate/out-of-order tracking via `unique_packets_recieved` set (`:8-36`); `record(header, size_header_recieved, size_video_recieved)` (`:38-87`); loss/completeness estimate in `calculate_differences` (`:89-95`); `summary` (`:97-115`).
- **Evidence:** `VERIFIED`. Used only by `reciever_nalu.py` — **not** present on the radio RX path. `VERIFIED`.

---

## Cross-cutting notes

1. **Two wire realities, one ceiling:** both transports go through `build_datagram`, so the 24+1176=1200 bound holds in both modes; PMT prefix only exists over ZMQ. `VERIFIED`.
2. **Config divergence:** uncommitted `config.py:13 = "radio"` vs committed `"udp"` — the repo's *defaults doc* and *live runtime* differ at the moment these docs were written. Radio is the mode being integrated. `VERIFIED`.
3. **Not covered here:** tests (`test/`), plans (`PLAN_RADIO_ZMQ.md`, `.superpowers/`), `requirements*.txt`, `radio/flowgraphs/README_FLOWGRAPHS.md`, other root docs. `scheduler_isp`-style naming typos (e.g. `paketizer`/`reciever`) are repo conventions, preserved.
4. **Dead/legacy code:** `transport/sender_nalu.py` (fully commented), `packetizer.update_flag` (`packetizer.py:71-87`), `nalu_parser.extract_nalus` (`nalu_parser.py:32-51`), `UdpTransport.send_single_header` (`udp_transport.py:23-31`).