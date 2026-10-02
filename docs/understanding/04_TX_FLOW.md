# 04 — TX Flow: one NALU from `capture.py` to the BladeRF

Scope: `TRANSPORT="radio"` (`config.py:13`). Traces ONE representative unit end-to-end, plus the fragment/sequence math for larger NALUs.
Evidence legend: `VERIFIED` = read from current code or passing test · `INFERRED` = derived from architecture/naming · `UNPROVEN` = no evidence (hardware/RF claims live here).

**Representative unit** (byte-anchored, taken from a passing test, `test/test_zmq_pdu_transport.py:38-40`):

```
NALUPacket(packet_sequence=1, nalu_id=1, fragment_index=0, fragment_count=1,
           nal_type=5, priority=Priority.HIGH, timestamp_ns=0, payload=b"\x01\x02\x03")
```

It is a single-fragment IDR payload (3 bytes) chosen so the same 27-byte datagram can be followed through every document in this series. Real NALUs are much larger and fragment (see "Sequence math" below).

---

## Stage 0 — Capture entry (wiring)

INPUT: process start (module import of `capture.py`)
PROCESS: `transport = get_transport()` selects the transport from `config.TRANSPORT` (`capture.py:20`); `Paketizer()` and `PacketScheduler()` instances are created (`capture.py:21-22`); `FfmpegVideoSource()` and `SenderMetrics()` start inside `try` (`capture.py:26-28`).
OUTPUT: one live transport (here `ZMQPduTransport`, PUSH bound to `tcp://127.0.0.1:5555`), one packetizer with `packet_sequence=0, nalu_id=0`, one scheduler with four empty deques, one ffmpeg child process. `VERIFIED` `capture.py:20-28`, `transport/transport_factory.py:3-13`, `radio/zmq_pdu_transport.py:18-23`.

Startup order outside this file (reference procedure): Python RX → RX flowgraph (bind 5556) → TX flowgraph (connect 5555) → `capture.py` (`radio/flowgraphs/README_FLOWGRAPHS.md:54-57`). `INFERRED` as the intended order; actually running it on hardware is `UNPROVEN` (`README_FLOWGRAPHS.md:72-81`).

## Stage 1 — ffmpeg video source

INPUT: `/dev/video0` (V4L2 camera) as raw video.
PROCESS: spawns
`ffmpeg -hide_banner -f v4l2 -i /dev/video0 -c:v libx264 -preset ultrafast -tune zerolatency -f h264 pipe:1`
(`ffmpeg_video_source.py:7-16`) — Annex-B H.264 elementary stream on stdout. The main loop calls `read_chunk()` which reads up to `LECTURE_SIZE = 4096` bytes per call (`config.py:8`, `ffmpeg_video_source.py:26-37`).
OUTPUT: a `bytes` chunk of ≤4096 B (or `None` if the pipe is empty, `ffmpeg_video_source.py:33-35`). `VERIFIED`.

Failure paths: empty pipe → `read_chunk` returns `None` → `obtain_nalus_from_chunk(None)` returns `None` (`ffmpeg_video_source.py:40-41`) → the `for` loop body in `capture.py` is skipped, so nothing is dequeued while the loop keeps spinning (`capture.py:30-34`). `close()` calls `self.process.terminate` without `()`, i.e. it only fetches the bound method and never invokes it (`ffmpeg_video_source.py:51`) — `VERIFIED` from code that the process is not explicitly terminated.

## Stage 2 — NALU extraction

INPUT: the 4096-B chunk appended to `FfmpegVideoSource.stream_buffer` (`ffmpeg_video_source.py:43`).
PROCESS (`packets/nalu_parser.py`):
1. `recover_start_positions` scans for 4-byte `00 00 00 01` then 3-byte `00 00 01` start codes (`nalu_parser.py:15-30`).
2. `extract_nalus_chunk` requires **at least 2 start codes** to emit anything (`nalu_parser.py:59-60`); it emits every NALU delimited *between* start codes and **holds back the last one** (from its start code to end-of-buffer) so a NALU split across chunk reads is never emitted truncated (`nalu_parser.py:64-79`, holdback at `:75-78`).
3. `FfmpegVideoSource` re-seats the buffer on the held-back tail: `stream_buffer = stream_buffer[-remain_buffer:]` (`ffmpeg_video_source.py:44-46`).
OUTPUT: `list[bytes]` of NALU bodies **without** start codes; leftover bytes stay buffered.

Concrete example (`VERIFIED` from the algorithm):

```
INPUT    stream_buffer =
         00 00 00 01 67 <SPS…> 00 00 00 01 68 <PPS…> 00 00 00 01 65 <IDR partial…>
PROCESS  starts = [(0,4), (11,4), (21,4)]  →  NALU0 = 67…, NALU1 = 68…, last start (21) held back
OUTPUT   nalus = [b"\x67…", b"\x68…"];  remain = len(buffer) - 21  → tail "00 00 00 01 65…" kept
```

Assumption/edge: the scan loop runs `while i < len(data) - 3` (`nalu_parser.py:20`), so a start code occupying exactly the final 3 bytes is only seen after more data arrives — harmless because of the holdback. `INFERRED`.

## Stage 3 — Classification

INPUT: one NALU `bytes`.
PROCESS: `nalu_type(nalu)` = `nalu[0] & 0x1F` (`nalu_parser.py:82-85`); for a typical IDR first byte `0x65` → type `5`, name `"IDR slice"` (`nalu_parser.py:87-95`); `obtain_classification_nalu(5)` → `Priority.HIGH` because `HIGH_VALUES = [5]` (`packets/priority_classifier.py:10-22`, `config.py:23`). Full mapping (`config.py:22-25`): CRITICAL = SPS(7)/PPS(8), HIGH = IDR(5), NORMAL = non-IDR(1) and default, LOW = SEI(6).
OUTPUT: `(numeric_type_nalu=5, nalu_name="IDR slice", priority=Priority.HIGH, nalu_size=len(nalu))` consumed at `capture.py:36-39`. `VERIFIED`.

Failure path: an empty NALU (two adjacent start codes) makes `nalu_hashable[0]` raise `IndexError` (`nalu_parser.py:85`). Scenario `INFERRED`, the unguarded index `VERIFIED`.

## Stage 4 — Packetization (`Paketizer.packetize`)

INPUT: `(nalu: bytes, nalu_type: int, priority: Priority)`.
PROCESS (`packets/packetizer.py:31-68`):
- Split with `range(0, len(nalu), SIZE_MAX_PACKET)` and slice `nalu[offset:SIZE_MAX_PACKET + offset]` (`:41-43`) — `SIZE_MAX_PACKET = 1176` from config (`packetizer.py:2`).
- `fragment_count = len(fragments)` (`:46`); `self.nalu_id += 1` once per NALU (`:49`); `nalu_time = time.monotonic_ns()` once per NALU (`:50`); `self.packet_sequence += 1` **per fragment**, globally, never reset (`:54`, field comment `:9`).
- Build one `NALUPacket` per fragment (`:57-66`), dataclass fields `packetizer.py:7-16`.
OUTPUT: `list[NALUPacket]`, one entry per fragment, all sharing `nalu_id`, `nal_type`, `priority`, `timestamp_ns`.

Sequence math, worked example (3000-byte IDR NALU, prior state `packet_sequence=41`, `nalu_id=9`) `INFERRED` from the code, arithmetic `VERIFIED`:

```
offsets 0, 1176, 2352      →  fragments of 1176, 1176, 648 bytes   (fragment_count = 3)
nalu_id 9 → 10             →  all three packets carry nalu_id = 10
packet_sequence 41 → 42, 43, 44   (one increment per fragment, idx 0,1,2)
timestamp_ns identical for all three (single time.monotonic_ns() call)
```

Our representative unit is the already-small case: `fragment_count=1`, `fragment_index=0`, `packet_sequence=1`, `nalu_id=1`. `VERIFIED` `test/test_zmq_pdu_transport.py:38-40`.

## Stage 5 — Scheduling (`PacketScheduler`)

INPUT: `list[NALUPacket]` (one whole NALU's fragments arrive as one list).
PROCESS: `enqueue` appends the whole list to the deque of `packets[0].priority` — CRITICAL/HIGH/NORMAL/LOW (`packetScheduler.py:15-30`); `dequeue` pops from the highest non-empty queue in order CRITICAL → HIGH → NORMAL → LOW (`:32-42`); `has_packets` (`:44-54`).
OUTPUT: the next list to send, or `None` if all queues are empty.
Caller cadence `VERIFIED`: `capture.py` enqueues then dequeues **once per NALU processed** (`capture.py:45-49`), so at most one fragment-list leaves the scheduler per loop iteration — backlogged lower-priority lists wait behind higher-priority ones; a growing backlog is possible `INFERRED`.

## Stage 6 — Transport selection (`get_transport`)

INPUT: `config.TRANSPORT` string.
PROCESS (`transport/transport_factory.py:3-13`): `"radio"` → lazy-import `ZMQPduTransport` (missing `pyzmq` → `RuntimeError` with the Spanish install hint, `:8-11`); anything else → `UdpTransport()` (`:13`).
OUTPUT: a `Transport` implementing `send_packet(NALUPacket) -> int` and `close()` (`transport/transport.py:4-12`).
Current config: `TRANSPORT = "radio"` (`config.py:13`). `VERIFIED` (`test/test_transport_factory.py` covers all three branches).

## Stage 7 — Datagram creation (`build_datagram`)

INPUT: `NALUPacket`.
PROCESS (`transport/datagram.py:5-13`):
1. `VideoHeader(packet_sequence, nalu_id, fragment_index, fragment_count, nal_type, priority, timestamp_ns, len(payload))` (`:6-8`).
2. `header.to_bytes()` — `struct.pack('!IIHHBBQH', …)` = 24 bytes, network byte order (`video_header.py:15-25`).
3. `data = header + payload`; `len(data) > UDP_SAFE_PAYLOAD(1200)` → `ValueError` (`:10-12`).
OUTPUT for the representative unit (27 bytes) `VERIFIED` (`test/test_datagram.py:13-17` layout, `test/test_zmq_pdu_transport.py:42` length):

```
INPUT    NALUPacket(seq=1, id=1, idx=0, cnt=1, type=5, HIGH, ts=0, payload=b"\x01\x02\x03")
PROCESS  header = 00 00 00 01 | 00 00 00 01 | 00 00 | 00 01 | 05 | 01
                   | 00 00 00 00 00 00 00 00 | 00 03        (24 B)
         data   = header + 01 02 03;  len = 27 ≤ 1200
OUTPUT   datagram =
  00000001 00000001 0000 0001 05 01 0000000000000000 0003 010203   # 27 bytes
```

Max-size boundary: payload 1176 → 1200 B allowed (`test_datagram.py:31-33`); payload 1177 → `ValueError` (`test_datagram.py:35-37`, `test/test_zmq_pdu_transport.py:45-51`). `VERIFIED`.

## Stage 8 — PMT encoding (`encode_u8vector_pdu`)

INPUT: 27-byte datagram.
PROCESS (`radio/pmt_codec.py:13-15`): `b"\x07\x06" + b"\x0a\x00" + struct.pack(">I", len(payload)) + b"\x01\x00" + payload`.
OUTPUT: 37-byte frame `VERIFIED` (frame == `encode_u8vector_pdu(build_datagram(packet))` with returned length 27, `test/test_zmq_pdu_transport.py:41-43`; 10-byte-prefix math `test/test_pmt_codec.py:5-12`, roundtrip `:14-16`, wiring `radio/zmq_pdu_transport.py:27`):

```
07 06 0a 00 00 00 00 1b 01 00   +   00000001 00000001 0000 0001 05 01 0000000000000000 0003 010203
└──────── 10-byte prefix ───────┘   └────────────────────── 27-byte datagram ──────────────────────┘
                     length field 0x0000001b = 27 = len(datagram)
```

Field semantics `VERIFIED` from `_parse`: `07`=PST_PAIR, `06`=PST_NULL (car = nil metadata), `0A`=uniform vector, `00`=u8 subtype, u32-BE length, `01`=npad, `00`=pad byte, then the datagram bytes (`pmt_codec.py:3-5`, `:50-59`). Note: the car is **nil**, not a dict object — the flowgraph README describes the wire as `cons(dict, u8vector)` (`README_FLOWGRAPHS.md:61-70`); code wins: the emitted car is `PST_NULL`. Whether GNU Radio accepts this exact frame is `UNPROVEN` (manual checklist only, `README_FLOWGRAPHS.md:72-81`).

## Stage 9 — ZMQ PUSH behavior (`ZMQPduTransport`)

INPUT: `NALUPacket`; endpoint `tcp://127.0.0.1:5555`, `ZMQ_TX_BIND = True` (`radio/config_radio.py:1,3`).
PROCESS (`radio/zmq_pdu_transport.py`): constructor creates a `zmq.PUSH` socket and **binds** (because `ZMQ_TX_BIND`), `:18-23`; `send_packet` = `build_datagram` → `encode_u8vector_pdu` → `socket.send(frame)` → **returns `len(datagram)`** (not the frame length), `:25-29`. `close()` closes with linger 0 and terminates an owned context (`:31-37`).
OUTPUT: one ZMQ message = the 37-byte PMT frame on 5555; caller sees `27`, which `capture.py` feeds to metrics (`capture.py:54-56`).
Push semantics: precisely — ZMQ PUSH fair-queues to connected PULL peers; if no peer is connected, messages **queue in the socket** until HWM (default unbound here, `hwm=-1` in the flowgraph is the flowgraph side). No peer connected → `send` still succeeds (queues) `INFERRED` from ZMQ semantics; not exercised by tests (tests inject fakes, `test/test_zmq_pdu_transport.py:10-29`).
`VERIFIED`: frame content + returned 27 (`test/test_zmq_pdu_transport.py:41-43`), bind on 5555 (`:59-67`), full TX→RX roundtrip over `inproc://` (`test/test_zmq_loopback_integration.py:19-32`).

## Stage 10 — GNU Radio entry point (`tx_bladerf.grc`)

INPUT: serialized PMT frames on `tcp://127.0.0.1:5555`.
PROCESS (reference artifact, XML only — no generated Python checked in):
1. `zeromq_pull_msg_source`, address `tcp://127.0.0.1:5555`, `mode=connect`, timeout 100 (`tx_bladerf.grc:55-81`).
2. `blks2.pdu_to_tagged_stream`, Type `byte`, Len Tag Key `packet_len` (`:82-96`).
3. `digital.gmsk_mod`, `samples_per_symbol=8`, `gain=1.0`, `bt=0.3` (`:97-123`).
4. `bladerf_sink`, `sample_rate=20e6`, `center_freq=2.45e9`, `gain=40` (`:124-142`).
Connections `out→in`, `0→0`, `0→0` (`:143-160`).
OUTPUT: GMSK IQ samples to the BladeRF. The flowgraph treats the datagram **opaquely** — it never parses `VideoHeader`.
Evidence status: block graph and parameters `VERIFIED` as XML content (only XML well-formedness is tested, `test/test_flowgraphs.py:6-10`); modulating/transmitting/receiving correctly is `UNPROVEN` — hardware checklist at `radio/flowgraphs/README_FLOWGRAPHS.md:72-81`.

---

## Key-module walkthrough (12 questions)

Abbreviations: caller/deps cite `file:line`. Q12 delta is vs. the pre-GNU-Radio UDP-only baseline (`UdpTransport` + `reciever_nalu.py`).

### M1 — `capture.py` entry + loop
1. **Why:** orchestrate capture → packetize → schedule → send.
2. **Problem:** glue camera bytes to a `Transport`.
3. **Who calls it:** process entry (`python capture.py`), `README_FLOWGRAPHS.md:57`.
4. **Calls:** `get_transport` (`:20`), `FfmpegVideoSource` (`:27`), `nalu_type/nalu_type_name` (`:36-37`), `obtain_classification_nalu` (`:38`), `Paketizer.packetize` (`:45`), `PacketScheduler.enqueue/dequeue/has_packets` (`:47-49`), `transport.send_packet` (`:54`), `SenderMetrics.record` (`:56`).
5. **Receives:** nothing (script); ffmpeg supplies chunks.
6. **Returns:** nothing; on `KeyboardInterrupt` prints metrics summary (`:59-62`).
7. **State:** module-level transport/packetizer/scheduler; loop is infinite.
8. **Assumptions:** ffmpeg alive; one `dequeue` per processed NALU (`:47-56`); `DEBUG=False` (`config.py:5`).
9. **Fails:** pipe EOF → `None` chunks, spin with dequeues stalled (Stage 1); `ValueError` from `build_datagram` propagates uncaught.
10. **Example:** Stage 0–9 trace above.
11. **E2E:** the TX entry; every outbound unit passes here.
12. **Delta:** only line 20/54 changed meaning — the `Transport` abstraction means the loop body is identical to the UDP era; only `get_transport()` output differs (`transport_factory.py:3-13`). `VERIFIED`.

### M2 — `FfmpegVideoSource`
1. **Why:** own the ffmpeg child and its Annex-B byte stream.
2. **Problem:** turn `/dev/video0` into parseable byte chunks.
3. **Callers:** `capture.py:27,31-32,75`.
4. **Calls:** `subprocess.Popen(cmd…)` (`ffmpeg_video_source.py:20`), `stdout.read` (`:32`), `extract_nalus_chunk` (`:44`).
5. **Receives:** none; config `LECTURE_SIZE=4096` (`config.py:8`).
6. **Returns:** `read_chunk` → `bytes | None` (`:26-37`); `obtain_nalus_from_chunk` → `list[bytes] | None` (`:39-48`).
7. **State:** `process`, `stream_buffer` (carry-over tail), `remain_buffer`, `stdout`.
8. **Assumptions:** at least 2 start codes before any NALU is emitted (parser holdback); NALUs < chunk size for progress.
9. **Fails:** `RuntimeError` if stdout missing (`:29-30`); `None` chunk on EOF; `close()` does not actually terminate (`:51`, missing `()`).
10. **Example:** Stage 2 INPUT/OUTPUT.
11. **E2E:** supplies every NALU to the loop.
12. **Delta:** unchanged from baseline (imports only `LECTURE_SIZE` + parser). `VERIFIED`.

### M3 — `packets/nalu_parser.py` (`extract_nalus_chunk`, `nalu_type`)
1. **Why:** split Annex-B into NALUs without truncating across chunk boundaries.
2. **Problem:** start-code framing with a safe holdback.
3. **Callers:** `FfmpegVideoSource.obtain_nalus_from_chunk` (`ffmpeg_video_source.py:44`); `capture.py` imports `nalu_type/nalu_type_name` (`capture.py:2`); `reciever_nalu.py` imports names too (`reciever_nalu.py:5`).
4. **Calls:** `recover_start_positions` (`nalu_parser.py:15-30`).
5. **Receives:** `data: bytes` (buffer).
6. **Returns:** `(list[bytes], remaining_buffer:int)` (`:53-79`); `nalu_type` → `int 0..31` (`:82-85`); `nalu_type_name` → `str` (`:87-95`).
7. **State:** none in functions (a module-level `nal_units = []` at `:7` is unused by these paths).
8. **Assumptions:** ≥2 starts to emit; last NALU always held; scan stops at `len-3` (`:20`).
9. **Fails:** empty NALU → `IndexError` in `nalu_type` (`:85`); never raises otherwise.
10. **Example:** Stage 2.
11. **E2E:** every TX (and UDP RX metrics) NALU crosses here.
12. **Delta:** unchanged from baseline. `VERIFIED`.

### M4 — `Paketizer.packetize` / `NALUPacket`
1. **Why:** fragment NALUs to fit the 1200-B ceiling and stamp routing metadata.
2. **Problem:** map one NALU → N wire-ready packets with shared identity.
3. **Callers:** `capture.py:45`.
4. **Calls:** `SIZE_MAX_PACKET` (`packetizer.py:2`), `time.monotonic_ns` (`:50`).
5. **Receives:** `(nalu: bytes, nalu_type: int, priority: Priority)`.
6. **Returns:** `list[NALUPacket]` (`:31-68`); dataclass fields `:7-16`.
7. **State:** `packet_sequence` (global, never resets, `:9,22,54`), `nalu_id` (`:49`); per-NALU fields are computed, not stored (comments `:24-29`).
8. **Assumptions:** `len(nalu) > 0` (empty → empty list, `:41` loop); `payload_size` fits u16 (guaranteed by 1176 cap).
9. **Fails:** none internally; oversized fragments impossible by construction.
10. **Example:** Stage 4 (3000-B → 3 packets) and the 3-B representative unit.
11. **E2E:** producer of every unit sent on the wire.
12. **Delta:** unchanged from baseline. `VERIFIED`.

### M5 — `PacketScheduler`
1. **Why:** prioritize by NALU relevance before sending.
2. **Problem:** four priority deques, strict priority pop.
3. **Callers:** `capture.py:47-49`.
4. **Calls:** `collections.deque`, `Priority` (`packetScheduler.py:4-7`).
5. **Receives:** `list[NALUPacket]` per enqueue (`:15`).
6. **Returns:** `dequeue` → `list[NALUPacket] | None` (`:32-42`); `has_packets` → `bool` (`:44-54`).
7. **State:** four deques of whole-NALU lists (`:10-13`).
8. **Assumptions:** all fragments of a NALU share one priority (true — set per NALU, `packetizer.py:62`); list order inside a queue is FIFO.
9. **Fails:** empty list ignored (`:16-17`); unknown priority falls into NORMAL (`:29-30`).
10. **Example:** enqueue `[NALUPacket type=5 HIGH]` → lands in `highQueue` (`:23-24`); if `criticalQueue` empty, it is the next pop (`:35-36`).
11. **E2E:** ordering point between packetizer and transport.
12. **Delta:** unchanged from baseline. `VERIFIED`.

### M6 — `get_transport`
1. **Why:** one seam between app and wire (UDP vs radio).
2. **Problem:** select/configure the `Transport` implementation.
3. **Callers:** `capture.py:20`.
4. **Calls:** `config.TRANSPORT` (`transport_factory.py:4`), lazy import `radio.zmq_pdu_transport` (`:7`), `UdpTransport()` (`:13`).
5. **Receives:** none (reads config).
6. **Returns:** `ZMQPduTransport()` or `UdpTransport()` (`:3-13`).
7. **State:** none (fresh instance per call).
8. **Assumptions:** `TRANSPORT=="radio"` ⇒ pyzmq installed, else `RuntimeError` (`:8-11`).
9. **Fails:** that `RuntimeError`; unknown strings silently fall through to UDP (`:13`) `INFERRED` as intentional default.
10. **Example:** `"radio"` → PUSH socket bound to 5555 (Stage 9).
11. **E2E:** step that flips the whole pipeline between architectures.
12. **Delta:** this module *is* the delta — it did not exist before the transport abstraction. `VERIFIED` (`test/test_transport_factory.py:7-29`).

### M7 — `build_datagram` / `VideoHeader`
1. **Why:** canonical wire image shared by both transports and both receivers.
2. **Problem:** serialize metadata + payload under a size ceiling.
3. **Callers:** `ZMQPduTransport.send_packet` (`zmq_pdu_transport.py:26`), `UdpTransport.send_packet` (`udp_transport.py:14`); `parse_datagram` is the RX mirror (`datagram.py:15-19`).
4. **Calls:** `VideoHeader.to_bytes` (`video_header.py:15-25`), `config.UDP_SAFE_PAYLOAD/REAL_HEADER_SIZE` (`datagram.py:1`).
5. **Receives:** `NALUPacket`.
6. **Returns:** `bytes` ≤ 1200 (`:5-13`).
7. **State:** none (pure).
8. **Assumptions:** payload ≤ 1176 (else `ValueError`, `:10-12`); `payload_size` field mirrors `len(payload)` (`:8`).
9. **Fails:** `ValueError` too big (`:11-12`); `struct.error` unreachable under the cap.
10. **Example:** Stage 7 (27-byte output).
11. **E2E:** the unit that crosses the SDR boundary opaquely.
12. **Delta:** unchanged from baseline; the radio transport reuses it verbatim. `VERIFIED` (`test/test_datagram.py`).

### M8 — `encode_u8vector_pdu`
1. **Why:** wrap a datagram as the PMT PDU GNU Radio's ZMQ blocks exchange.
2. **Problem:** produce `pmt::serialize_str(cons(meta, u8vector))`-compatible bytes.
3. **Callers:** `ZMQPduTransport.send_packet` (`zmq_pdu_transport.py:27`); roundtripped by `decode_pdu_data` in tests.
4. **Calls:** `struct.pack` only (`pmt_codec.py:14`).
5. **Receives:** `payload: bytes` (the datagram).
6. **Returns:** `10 + len(payload)` bytes (`:13-15`).
7. **State:** none.
8. **Assumptions:** payload length < 2³² (u32 BE length).
9. **Fails:** none on encode (decode-side errors are `PmtDecodeError`, `:8-9`).
10. **Example:** Stage 8 (37-byte frame).
11. **E2E:** last Python byte-level step before ZMQ.
12. **Delta:** new in the radio integration (UDP never needed PMT). `VERIFIED` (`test/test_pmt_codec.py:5-16`).

### M9 — `ZMQPduTransport`
1. **Why:** `Transport` implementation over ZMQ PUSH.
2. **Problem:** hand each frame to GNU Radio with zero knowledge of RF.
3. **Callers:** `capture.py` via factory (`capture.py:20,54`).
4. **Calls:** `build_datagram` (`:26`), `encode_u8vector_pdu` (`:27`), `zmq.Context/socket/send` (`:15,19,28`).
5. **Receives:** `NALUPacket`; config endpoint/bind (`config_radio.py:1,3`).
6. **Returns:** `int = len(datagram)` (`:29`) — deliberately the datagram size, matching `UdpTransport.send_packet` (`udp_transport.py:21`).
7. **State:** context, socket (owned flags), endpoint (`:13-17`).
8. **Assumptions:** peer PULL connects (or messages buffer); `ZMQ_TX_BIND=True` → this side binds 5555 (`:20-21`).
9. **Fails:** `ImportError` at module import if no pyzmq (caught by factory, `transport_factory.py:8-11`); `ValueError` if datagram > 1200 propagates before any send (`test/test_zmq_pdu_transport.py:45-51`).
10. **Example:** Stages 7–9; test asserts sent frame == `encode_u8vector_pdu(build_datagram(packet))` and returned 27 (`:41-43`).
11. **E2E:** TX-side wire owner for `TRANSPORT="radio"`.
12. **Delta:** new module; interface-compatible replacement for `UdpTransport`. `VERIFIED`.

### M10 — `tx_bladerf.grc` (GNU Radio TX entry)
1. **Why:** turn PDU bytes into RF with an SDR.
2. **Problem:** ZMQ PDU → tagged stream → GMSK → BladeRF.
3. **Who calls it:** GRC/grcc (`run_command {python} -u {filename}`, `tx_bladerf.grc:43-44`); started per `README_FLOWGRAPHS.md:56`.
4. **Calls:** GNU Radio blocks (`zeromq_pull_msg_source` `:55-81`, `blks2_pdu_to_tagged_stream` `:82-96`, `digital_gmsk_mod` `:97-123`, `bladerf_sink` `:124-142`).
5. **Receives:** serialized PMT PDU messages on 5555 (connect mode).
6. **Returns:** n/a (signal out); `gr-bladeRF` sink consumes samples.
7. **State:** block parameters as in the XML (sps=8, 20 Msps, 2.45 GHz, gain 40).
8. **Assumptions:** gr-zeromq + gr-bladeRF installed (`README_FLOWGRAPHS.md:43-47`); `packet_len` tag from the PDU block (`:93-94`).
9. **Fails:** missing blocks ⇒ grcc load errors; runtime/RF failures unknown.
10. **Example:** 37-byte frame → PDU → 37-byte tagged stream → GMSK (`UNPROVEN` past the message port).
11. **E2E:** first RF-side stage of TX.
12. **Delta:** entirely new (baseline had no GNU Radio). Structure `VERIFIED` as XML (only well-formedness tested, `test_flowgraphs.py:6-10`); behavior `UNPROVEN` (`README_FLOWGRAPHS.md:72-81`).

---

## End-to-end mini-sequence

```
NALUPacket (seq=1, id=1, idx=0, cnt=1, type=5, HIGH, ts=0, payload=b"\x01\x02\x03")
   → (build_datagram)                transport/datagram.py:5-13
datagram  27 B = VideoHeader(24 B) + 01 02 03
   → (encode_u8vector_pdu)           radio/pmt_codec.py:13-15
frame     37 B = 07 06 0a 00 00 00 00 1b 01 00 + datagram
   → PUSH 5555                       radio/zmq_pdu_transport.py:25-29  (bind tcp://127.0.0.1:5555)
   → flowgraph                       tx_bladerf.grc: ZMQ PULL Message Source (connect 5555)
                                     → PDU to Tagged Stream (byte/packet_len) → GMSK Mod (sps 8)
                                     → BladeRF sink (20 Msps, 2.45 GHz)   [RF link UNPROVEN]
```

Roundtrip proof of the Python half: `test/test_zmq_loopback_integration.py:19-32` sends this packet over `inproc://` and parses back `payload == b"XYZ"` with the same sizes.

## What changes when `TRANSPORT="udp"`

Nothing changes before or inside `send_packet`: `get_transport()` returns `UdpTransport` instead of `ZMQPduTransport` (`transport/transport_factory.py:13`), and `UdpTransport.send_packet` calls the **same** `build_datagram` (`udp_transport.py:14`) — identical 24+payload bytes — then `socket.sendto(data_to_send, (SERVER_IP, SERVER_PORT))` to `127.0.0.1:65432` (`udp_transport.py:20`, `config.py:11-12`), returning `len(data_to_send)` (`:21`), the same contract `capture.py:54-56` relies on. No PMT prefix, no ZMQ, no flowgraph; the receiver becomes `reciever_nalu.py` binding that UDP port (`reciever_nalu.py:22-24`). The 1200-B ceiling and `SIZE_MAX_PACKET=1176` still apply because both live in the shared packetizer/datagram layers (`config.py:16-19`, `datagram.py:10-12`). `VERIFIED`.
