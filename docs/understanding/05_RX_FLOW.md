# 05 — RX Flow: one unit from GNU Radio/ZMQ back to ffplay

Scope: radio path (`radio/reciever_radio.py` → `radio/zmq_pdu_receiver.py`), with the UDP receiver as contrast.
Evidence legend: `VERIFIED` / `INFERRED` / `UNPROVEN` as in `04_TX_FLOW.md`. The RF half is a reference artifact: hardware checklist `radio/flowgraphs/README_FLOWGRAPHS.md:72-81`, so anything past the ZMQ message boundary is `UNPROVEN`.

The reverse example of 04/06 is used throughout:

```
frame (37 B) = 07 06 0a 00 00 00 00 1b 01 00 + datagram(27 B)
```

## Stage 1 — RX flowgraph (`rx_hackrf.grc`)

INPUT: RF at 2.45 GHz / 20 Msps (assumed GMSK, matching TX) `UNPROVEN`.
PROCESS (reference XML):
1. `osmosdr_source`, `type=complex`, `args=hackrf`, `sample_rate=20e6`, `freq=2.45e9`, `bandwidth=20e6` (`rx_hackrf.grc:55-85`).
2. `digital.gmsk_demod`, `samples_per_symbol=8` (`:86-124`).
3. `blocks.tagged_stream_to_pdu`, Type `byte`, Len Tag Key `packet_len` (`:125-139`).
4. `zeromq_push_msg_sink`, address `tcp://127.0.0.1:5556`, **mode=bind**, timeout 100 (`:140-166`); connections `:167-184`.
OUTPUT: serialized PMT PDU pushed on 5556.
Evidence: block graph `VERIFIED` as XML (only well-formedness tested, `test/test_flowgraphs.py:6-10`); demodulation correctness `UNPROVEN`.

## Stage 2 — ZMQ handoff: PUSH 5556 → PULL connect

INPUT: the 37-byte frame in the flowgraph's PUSH sink.
PROCESS: the Python receiver creates a `zmq.PULL` socket and **connects** to `ZMQ_RX_ENDPOINT` because `ZMQ_RX_CONNECT = True` (`radio/zmq_pdu_receiver.py:21-27`, `radio/config_radio.py:2,4`), then sets `zmq.RCVTIMEO = ZMQ_RCVTIMEO_MS = 5000` (`zmq_pdu_receiver.py:27`, `config_radio.py:5`).
OUTPUT: frames delivered to `recv()`; role split documented at `README_FLOWGRAPHS.md:36-39` (flowgraph binds, Python connects). `VERIFIED` from code + grc; live 5556 traffic `UNPROVEN`.

## Stage 3 — `recv_timeout`

INPUT: nothing (blocking call with 5000 ms timeout).
PROCESS (`radio/zmq_pdu_receiver.py:29-34`): `frame = self._socket.recv()`; on timeout (`zmq.Again`, aliased `TIMEOUT_EXCEPTION`, `:12`) → return `None`; otherwise `return decode_pdu_data(frame)`.
OUTPUT: `bytes` datagram (27 B in the example) or `None`. `VERIFIED` (`test/test_zmq_pdu_receiver.py:29-35`).

## Stage 4 — `decode_pdu_data` (PMT → datagram)

INPUT: 37-byte serialized PMT frame.
PROCESS (`radio/pmt_codec.py:72-81`):
1. `_parse(frame)` recursively decodes the PMT (`:23-70`): `07` PAIR → car `06` = `None`, cdr = uniform vector (`0a 00`, u32-BE length, npad `01`, pad `00`, then `length` bytes) (`:50-59`).
2. Trailing bytes after a complete message → `PmtDecodeError("datos extra…")` (`:74-75`); truncated input → `PmtDecodeError` from `_read_exact` (`:17-21`); unknown tag → `PmtDecodeError` (`:70`); nesting > 64 → `PmtDecodeError` (`:44-46`, `_MAX_DEPTH` `:11`).
3. **Caveat (pair walk):** `node = value; while isinstance(node, tuple) and len(node) == 2: node = node[1]` (`:76-78`) — it walks cdr links until it finds a non-pair; if that final node is not `bytes` → `PmtDecodeError("el cdr final del PDU no es un u8vector")` (`:79-80`). Unbalanced/non-pair structures therefore raise rather than return partial data `VERIFIED` (`test/test_pmt_codec.py:23-42` covers truncated, unknown tag, non-u8 cdr, extra bytes, depth).
OUTPUT: the raw 27-byte datagram. Roundtrip with the TX encoder is tested (`test_pmt_codec.py:14-16`).

## Stage 5 — `parse_datagram`

INPUT: 27-byte datagram.
PROCESS (`transport/datagram.py:15-19`): `len(data) < REAL_HEADER_SIZE(24)` → `ValueError("Datagrama demasiado corto…")` (`:16-17`); else `VideoHeader.from_byte(data[:24])` (`video_header.py:26-30`, struct `!IIHHBBQH`) and payload `data[24:]`.
OUTPUT: `(VideoHeader, bytes)`.

```
INPUT    00000001 00000001 0000 0001 05 01 0000000000000000 0003 010203   # 27 B
PROCESS  split at offset 24
OUTPUT   header = VideoHeader(seq=1, id=1, idx=0, cnt=1, type=5, HIGH, ts=0, payload_size=3)
         payload = 01 02 03
```

Note: `parse_datagram` does **not** compare `payload_size` with `len(payload)` — the Reassembler does (`reassembler.py:21-22`). Short-input `ValueError` tested (`test/test_datagram.py:39-41`), header roundtrip (`:19-29`). `VERIFIED`.

## Stage 6 — `Reassembler.feed`

INPUT: `(VideoHeader, payload)`.
PROCESS (`packets/reassembler.py:12-37`), validation first (`:17-23` + `:28-29`), each returning `None` without state changes:
| Check | Condition | Evidence |
|---|---|---|
| count sanity | `count <= 0` → `None` | `:17-18`, `test_reassembler.py:70-73` |
| index range | `not 0 <= index < count` → `None` | `:19-20`, test `:75-78` |
| size match | `header.payload_size != len(payload)` → `None` | `:21-22`, test `:80-83` |
| count consistency | existing entry with different `fragment_count` → `None` | `:28-29`, test `:85-89` |

Then: create-or-reuse `pending_nalus[nalu_id] = {fragment_count, fragments}` (`:24-27`); store `fragments[index] = payload` — a duplicate index overwrites (idempotent; `test_reassembler.py:48-54`) (`:31`); when `len(fragments) == fragment_count`, join **in index order** `b"".join(fragments[i] for i in range(count))`, delete the entry, return the NALU (`:33-36`).
OUTPUT: complete NALU `bytes` or `None`. Out-of-order and interleaved NALUs handled (`test_reassembler.py:31-46,62-68`); a lost fragment leaves the entry pending forever — no eviction/timeout exists (`pending_nalus` only grows, `:24-27`), so permanent loss leaks entries `INFERRED` from the absence of cleanup code.

Reverse example (single fragment, our unit):

```
INPUT    header(id=1, idx=0, cnt=1, payload_size=3), payload = 01 02 03
PROCESS  validations pass → entry created → fragments={0: 010203} → len==count
OUTPUT   b"\x01\x02\x03"   (entry deleted)
```

Multi-fragment example (test): frames for `(idx=0,cnt=2,payload=AAA)` then `(idx=1,cnt=2,payload=BBB)` → `b"AAABBB"` (`test/test_zmq_pdu_receiver.py:37-47`).

## Stage 7 — `run_recv_loop` → `on_nalu` → ffplay

INPUT: `rx`, `reassembler`, callbacks.
PROCESS (`radio/zmq_pdu_receiver.py:44-54`): loop `datagram = rx.recv_timeout()`; `None` → `on_timeout()`, return if it answers `True` (`:47-50`); else `parse_datagram` (`:51`), `reassembler.feed` (`:52`), and `on_nalu(final_nalu)` when complete (`:53-54`).
`on_nalu` (`:64-68`): append to `video` list and `ffplay_process.stdin.write(b"\x00\x00\x00\x01" + nalu_bytes); flush`.
OUTPUT: Annex-B bytes into `ffplay -fflags nobuffer -flags low_delay -framedrop -f h264 -` stdin (`:57-62`). For our unit: stdin receives `00 00 00 01 01 02 03`. `VERIFIED` (`test_zmq_pdu_receiver.py:37-47` asserts `[b"AAABBB"]` through the loop).

## Stage 8 — `on_timeout` (5 s) → shutdown + storage

INPUT: no PDU for `ZMQ_RCVTIMEO_MS = 5000` ms (`config_radio.py:5`, applied `zmq_pdu_receiver.py:27`).
PROCESS (`:70-78`): print `"Tiempo de espera agotado, fin de recepción"`, close ffplay stdin, `terminate()` ffplay, write every buffered NALU (with `00 00 00 01` start codes) to file `reconstructed_rf`, return `True` → `run_recv_loop` exits (`:48-49`); `rx.close()` in `finally` (`:83-84`).
OUTPUT: playable `reconstructed_rf` file; process ends.
Behavior note: **any** 5-second gap in PDU arrival ends reception (the timeout is the only stop condition; there is no explicit end-of-stream packet) `VERIFIED` from code (`:29-34`, `:47-49`, `:70-78`) — consequences for a bursty link `INFERRED`.

Entry point: `radio/reciever_radio.py:1-4` just calls `main()`.

---

## Key-module walkthrough (12 questions)

### M1 — `rx_hackrf.grc`
1. **Why:** receive/demodulate the TX signal and republish bytes over ZMQ.
2. **Problem:** RF → PMT PDU bridge for the Python app.
3. **Who calls it:** GRC/grcc manual start (`README_FLOWGRAPHS.md:55`).
4. **Calls:** osmosdr, GMSK demod, tagged-stream→PDU, ZMQ PUSH sink (`rx_hackrf.grc:55-166`).
5. **Receives:** complex IQ (external, `UNPROVEN`).
6. **Returns:** n/a; emits PDUs on 5556 (bind).
7. **State:** XML params (20 Msps, 2.45 GHz, sps 8).
8. **Assumptions:** TX parameters match (sps 8, same center freq); gr-osmosdr installed.
9. **Fails:** missing hardware/blocks (unknown); only XML well-formedness tested.
10. **Example:** Stage 1.
11. **E2E:** RF entry of RX.
12. **Delta:** new (baseline had no SDR). Structure `VERIFIED`, behavior `UNPROVEN`.

### M2 — `ZMQPduReceiver`
1. **Why:** Python-side `Transport` analogue for inbound PDUs.
2. **Problem:** receive one frame, decode to a datagram, with timeout.
3. **Callers:** `run_recv_loop` (`zmq_pdu_receiver.py:46`), `main` (`:80-82`), loopback test.
4. **Calls:** `zmq.PULL connect` + `RCVTIMEO` (`:21-27`), `socket.recv` (`:31`), `decode_pdu_data` (`:34`).
5. **Receives:** endpoint/context/socket overrides (tests inject fakes).
6. **Returns:** `Optional[bytes]` — datagram or `None` on timeout (`:29-34`).
7. **State:** context, socket, endpoint (`:15-20`).
8. **Assumptions:** flowgraph already bound 5556; 5000 ms idle = end of stream.
9. **Fails:** `PmtDecodeError` propagates out of `recv_timeout` (not caught, `:34`) → crashes `run_recv_loop`; timeout → `None` (handled).
10. **Example:** Stage 3; fake-socket tests `test_zmq_pdu_receiver.py:29-35`.
11. **E2E:** RX wire owner for `TRANSPORT="radio"`.
12. **Delta:** new; mirrors `ZMQPduTransport`. `VERIFIED`.

### M3 — `decode_pdu_data`
1. **Why:** PMT bytes → raw datagram.
2. **Problem:** minimal mirror of `pmt::deserialize_str` for the PDU shape we emit.
3. **Callers:** `ZMQPduReceiver.recv_timeout` (`zmq_pdu_receiver.py:34`).
4. **Calls:** `_parse`/`_read_exact` (`pmt_codec.py:17-70`).
5. **Receives:** full frame `bytes`.
6. **Returns:** `bytes` (u8vector contents) (`:72-81`).
7. **State:** none (depth counter is call-local, `_MAX_DEPTH=64` `:11`).
8. **Assumptions:** frame is exactly one PMT message; final cdr is a u8vector.
9. **Fails:** `PmtDecodeError` (subclass of `ValueError`, `:8-9`) on truncation, unknown tag, extra bytes, excessive nesting, or non-u8 final cdr (`:70,74-75,79-80`) — all tested (`test_pmt_codec.py:23-42`).
10. **Example:** Stage 4 (37 → 27 bytes).
11. **E2E:** first decode step of RX.
12. **Delta:** new (radio only). `VERIFIED`.

### M4 — `parse_datagram`
1. **Why:** split header/payload — shared by radio RX and UDP RX logic.
2. **Problem:** 24-byte fixed framing.
3. **Callers:** `run_recv_loop` (`zmq_pdu_receiver.py:51`); `test_datagram.py`, loopback test.
4. **Calls:** `VideoHeader.from_byte` (`datagram.py:18`, `video_header.py:26-30`).
5. **Receives:** `bytes` ≥ 24 expected.
6. **Returns:** `(VideoHeader, bytes)` (`datagram.py:15-19`).
7. **State:** none.
8. **Assumptions:** sender used the same struct; `payload_size` trust deferred to Reassembler.
9. **Fails:** `ValueError` if `< 24` bytes (`:16-17`, `test_datagram.py:39-41`).
10. **Example:** Stage 5.
11. **E2E:** framing decode for every received unit.
12. **Delta:** existed for UDP; radio path reuses it unchanged. `VERIFIED`.

### M5 — `Reassembler.feed`
1. **Why:** rebuild NALUs from fragments without ordering assumptions.
2. **Problem:** validated, keyed, order-independent reassembly.
3. **Callers:** `run_recv_loop` (`zmq_pdu_receiver.py:52`), `reciever_nalu.py:63`, tests.
4. **Calls:** none (pure dict logic).
5. **Receives:** `(VideoHeader, payload)`.
6. **Returns:** `Optional[bytes]` (`reassembler.py:12-37`).
7. **State:** `pending_nalus: dict[nalu_id → {fragment_count, fragments}]` (`:5-6`); `pending_count` property (`:8-10`); no eviction.
8. **Assumptions:** `count` consistent per `nalu_id`; `payload_size` honest (checked `:21-22`); duplicates harmless (overwrite `:31`).
9. **Fails:** silent `None` drops on the four validations (`:17-23,28-29`); permanent pending entries on loss (`INFERRED`).
10. **Example:** single-fragment reverse trace + `AAABBB` (Stage 6); full matrix in `test/test_reassembler.py`.
11. **E2E:** produces the NALUs handed to ffplay/file.
12. **Delta:** unchanged from baseline — both receivers import the same class (`reciever_nalu.py:7`, `zmq_pdu_receiver.py:7`). `VERIFIED`.

### M6 — `run_recv_loop`
1. **Why:** reusable receive pipeline decoupled from ffplay.
2. **Problem:** recv → parse → feed → callback, with timeout as stop condition.
3. **Callers:** `main` (`zmq_pdu_receiver.py:82`), tests (`test_zmq_pdu_receiver.py:46`).
4. **Calls:** `rx.recv_timeout` (`:46`), `parse_datagram` (`:51`), `reassembler.feed` (`:52`), `on_nalu`/`on_timeout` (`:48,54`).
5. **Receives:** injected `rx`, `reassembler`, two callables.
6. **Returns:** `None` (only when `on_timeout()` returns `True`, `:47-49`).
7. **State:** external only (the objects passed in).
8. **Assumptions:** `on_timeout` decides termination; `PmtDecodeError`/`ValueError` are **not** caught (`:46-54`) → one bad frame kills the loop (`INFERRED` consequence; uncaught-ness `VERIFIED`).
9. **Fails:** as above; `recv_timeout` returning `None` is the only handled fault.
10. **Example:** two-frame `AAABBB` test (`test_zmq_pdu_receiver.py:37-47`).
11. **E2E:** the RX control loop.
12. **Delta:** new; the UDP receiver inlines the equivalent logic in `reciever_nalu.py:43-81`. `VERIFIED`.

### M7 — `main` (`on_nalu`, `on_timeout`, ffplay, `reconstructed_rf`)
1. **Why:** concrete sink for reassembled NALUs.
2. **Problem:** live playback + shutdown dump.
3. **Callers:** `radio/reciever_radio.py:1-4`.
4. **Calls:** `subprocess.Popen(ffplay…)` (`:62`), `Reassembler()` (`:82`), `ZMQPduReceiver()` (`:80`), file write (`:75-77`).
5. **Receives:** NALU bytes via `on_nalu` (`:64-68`), timeout signal via `on_timeout` (`:70-78`).
6. **Returns:** `None`; `on_timeout` returns `True` to stop the loop (`:78`).
7. **State:** `video: list[bytes]`, `ffplay_process`, `rx`.
8. **Assumptions:** ffplay stdin open; 5 s idle = clean end.
9. **Fails:** `BrokenPipeError` on stdin write if ffplay died (uncaught, `:66-68`) `INFERRED`; `PmtDecodeError` upstream kills the loop before `finally`.
10. **Example:** our unit → stdin `00 00 00 01 01 02 03`; on timeout file `reconstructed_rf` gets every buffered NALU with start codes (`:75-77`).
11. **E2E:** terminal consumption of the TX unit.
12. **Delta:** new output file name (`reconstructed_rf` vs UDP's `reconstructed2`); no `RecieverMetrics` on this path (UDP has one, `reciever_nalu.py:42,58,72`) `VERIFIED`.

### M8 — `reciever_nalu.py` (UDP contrast)
1. **Why:** baseline receiver without GNU Radio.
2. **Problem:** same reassembly/playback over raw UDP.
3. **Who calls it:** process entry (`python reciever_nalu.py`).
4. **Calls:** `socket.bind((SERVER_IP, SERVER_PORT))` + `settimeout(5.0)` (`:22-24`), `recvfrom(UDP_SAFE_PAYLOAD)` (`:45`), `obtain_header_video` slicing (`:35-40,56`), same `Reassembler.feed` (`:7,63`), ffplay (`:26,66-68`), `RecieverMetrics` (`:42,58,72`), file `reconstructed2` (`:78-80`).
5. **Receives:** UDP datagrams ≤ 1200 B from `127.0.0.1:65432`.
6. **Returns:** nothing; exits after timeout (`:70-81`).
7. **State:** module-level socket, ffplay, `video`, `reassembler`, `end` flag.
8. **Assumptions:** every datagram is a full datagram (UDP gives no framing help); same 24-byte header.
9. **Fails:** `socket.timeout` → treated as clean end (`:46-49`); malformed ≥24-byte headers raise inside `from_byte`/`feed` uncaught `INFERRED`.
10. **Example:** receives exactly the 27 bytes Stage 7 of 04 produced (no PMT prefix ever crosses UDP) → same `VideoHeader` → same Reassembler path.
11. **E2E:** alternative RX half of the baseline.
12. **Delta vs radio RX:** manual 24-byte slice instead of `decode_pdu_data` + `parse_datagram`; raw socket instead of ZMQ; `timeout=5.0` on the socket instead of `RCVTIMEO=5000`; extra metrics; output `reconstructed2`. Reassembly and ffplay consumption are byte-for-byte the same code. `VERIFIED`.

---

## End-to-end mini-sequence (reverse of 04)

```
RF (UNPROVEN) → rx_hackrf.grc: osmosdr → GMSK Demod → TaggedStream→PDU → PUSH bind 5556
   → ZMQ frame 37 B: 07 06 0a 00 00 00 00 1b 01 00 + datagram
   → (recv) ZMQPduReceiver PULL connect 5556, RCVTIMEO 5000       zmq_pdu_receiver.py:21-34
   → (decode_pdu_data) datagram 27 B                              pmt_codec.py:72-81
   → (parse_datagram)  VideoHeader(24 B) + payload 01 02 03        datagram.py:15-19
   → (Reassembler.feed) b"\x01\x02\x03"                           reassembler.py:12-37
   → (on_nalu) stdin write 00 00 00 01 01 02 03 → ffplay          zmq_pdu_receiver.py:64-68
   → (on_timeout after 5 s) close stdin, write "reconstructed_rf"  zmq_pdu_receiver.py:70-78
```