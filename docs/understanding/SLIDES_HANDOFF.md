# SLIDES_HANDOFF.md — presentation kit

Purpose: 10-slide deck explaining the GNU Radio + ZMQ PDU integration to an engineering audience. Every number below is evidence-backed (this doc's sibling files cite the `file:line`/test). Slides mirror `03_ARCHITECTURE.md`, `04_TX_FLOW.md`, `05_RX_FLOW.md`, `06_PACKET_AND_PDU_FORMAT.md`.

---

## 1. Objective (pitch the audience can walk away with)

> "We extended a working UDP H.264 real-time streaming prototype to transmit the same 24-byte header + payload datagram over the air with GNU Radio + SDR, by swapping the transport behind a one-line config switch — UDP stays intact, and both paths share one byte-exact wire format."

Three things the audience should remember:
1. **One datagram, two wires:** the 24-B `VideoHeader` + ≤1176-B payload (≤1200 B total) is identical over UDP and over ZMQ-PDU→GMSK.
2. **The seam is a factory:** `get_transport()` on `config.TRANSPORT` flips the whole pipeline; `capture.py`'s loop never changed.
3. **Python and GNU Radio meet as PMT PDUs:** the codec is bit-compatible with `pmt::serialize_str(cons(nil, u8vector))` — Python emits bytes GNU Radio's PDU blocks expect.

---

## 2. The story in 10 stages

1. Baseline: single-path UDP stream — `/dev/video0` → ffmpeg (Annex-B H.264) → NALU extraction → packetization → UDP → reassembly → ffplay.
2. Problem: the projector wants radios; the app owns the camera and the packetizer — keep the logic, change only the wire.
3. Design rule: extract shared code (`datagram.py`, `Reassembler`), add a `Transport` seam, keep the ABC untouched.
4. Wire contract: 24-B `VideoHeader` (`!IIHHBBQH`, big-endian), 1200 ceiling, 1176 max payload.
5. New isolated `radio/` package: PMT codec, two ZMQ adapters, config, entry point, reference flowgraphs.
6. TX path: capture → packetize → schedule → `ZMQPduTransport` PUSH **binds** 5555 → flowgraph PULL **connects** → PDU→tagged stream → GMSK → BladeRF.
7. RX path: HackRF → GMSK demod → tagged stream→PDU → flowgraph PUSH **binds** 5556 → `ZMQPduReceiver` PULL **connects** → decode → assemble → ffplay / file.
8. The PMT bytes: `07 06 0a 00 <u32 len> 01 00` prefix (nil metadata car) + datagram = one PDU per `send()`.
9. Tests: 42 stdlib tests, no hardware, no GNU Radio needed; pyzmq is optional (tolerant imports); loopback runs over `inproc://`.
10. Status & honesty: everything up to the ZMQ message port is `VERIFIED` by tests; RF over the air is documented but `UNPROVEN` (manual checklist only).

---

## 3. Slide sequence

### Slides 1–2 — Context
- **S1 "The baseline":** block diagram of the UDP path. Visual: `diagrams/before-after.mmd` (left half). Must-say: ffmpeg → `extract_nalus_chunk` → `Paketizer` → `UdpTransport` → `reciever_nalu.py` + `Reassembler`; only `test_scheduler.py` existed pre-branch.
- **S2 "What we wanted to add":** GNU Radio PDU transport without touching the app logic. Visual: `system-context.mmd`. Must-say: one-line switch `config.py TRANSPORT`, `Transport` ABC was already there and is respected.

### Slides 3–5 — Design & contract
- **S3 "The seam":** `get_transport()` factory + `Transport` ABC (`transport_factory.py:3-13`, `transport.py:4-12`). Must-say: `"radio"` → lazy ZMQ import with friendly `RuntimeError` if pyzmq missing; anything else → `UdpTransport`.
- **S4 "The wire contract":** Visual: `packet-format.mmd`. Must-say numbers: header 24 B `!IIHHBBQH` (`video_header.py:15-25`), `REAL_HEADER_SIZE` computed never hand-typed (`config.py:16-17`), `UDP_SAFE_PAYLOAD=1200`, `SIZE_MAX_PACKET=1176` (`config.py:18-19`), overflow → `ValueError` (`datagram.py:10-12`).
- **S5 "The binary example":** 27-B datagram → 37-B frame hexdump (from `06`). Visual: hexdump block. Must-say: both transports call the **same** `build_datagram`; test-proof `test_zmq_pdu_transport.py:41-43` and `test_datagram.py:13-17`.

### Slides 6–7 — The two flows
- **S6 "TX flow":** Visual: `tx-sequence.mmd`. Stage-by-stage: capture → classify (IDR=SPS/PPS critical, IDR high…) → fragment at 1176 → 4-priority scheduler → `encode_u8vector_pdu` → PUSH bind 5555 → flowgraph (`tx_bladerf.grc`: PULL connect → `pdu_to_tagged_stream` → `gmsk_mod` sps 8 → `bladerf_sink` 20 Msps / 2.45 GHz).
- **S7 "RX flow":** Visual: `rx-sequence.mmd`. HackRF → `gmsk_demod` → `tagged_stream_to_pdu` → PUSH bind 5556 → PULL connect → `decode_pdu_data` → `parse_datagram` → `Reassembler.feed` → ffplay + `reconstructed_rf`; 5000 ms idle ends reception.

### Slides 8–9 — PMT bytes & tests
- **S8 "The PMT PDU":** the byte layout. Must-say: prefix = `07 06 0a 00 <u32 BE len> 01 00`; **car is nil (`PST_NULL 06`), not a dict** — code wins over the README's `cons(dict,u8vector)` wording (`pmt_codec.py:13-15`); len field counts only the datagram.
- **S9 "Verification":** Visual: `module-dependencies.mmd` optional. Must-say: `python3 -m unittest discover -s test -p "test_*.py"` → **42 tests OK, exit 0**; no GNU Radio, no hardware; pyzmq optional (tolerant imports `zmq_pdu_transport.py:1-4`); real loopback `inproc://` (`test_zmq_loopback_integration.py`); plan-vs-code diff in `09`.

### Slide 10 — Status & honest limits
- **S10 "What's proven / what isn't":** Proven: header/ceiling/PMT/endpoints/roles, factory, assembly rules, 42 tests. `UNPROVEN`: GNU Radio accepting our exact bytes, GMSK over the air, BladeRF/HackRF behavior — manual checklist `README_FLOWGRAPHS.md:72-81`. Must-say: code wins; `PLAN_RADIO_ZMQ.md` is the intent, not the truth.

---

## 4. Diagram references

| Slide | Diagram | File |
|---|---|---|
| 1 | before/after routes | `docs/understanding/diagrams/before-after.mmd` |
| 2 | system context | `docs/understanding/diagrams/system-context.mmd` |
| 4 | packet anatomy | `docs/understanding/diagrams/packet-format.mmd` |
| 6 | TX sequence | `docs/understanding/diagrams/tx-sequence.mmd` |
| 7 | RX sequence | `docs/understanding/diagrams/rx-sequence.mmd` |
| 9 | module dependencies | `docs/understanding/diagrams/module-dependencies.mmd` |

Render Mermaid (e.g. `npx @mermaid-js/mermaid-cli -i file.mmd -o out.png` or GitHub mermaid paste).

---

## 5. Must-say facts (highest-confidence, slide-ready)

1. `VideoHeader` = 24 B, `!IIHHBBQH` big-endian: `4+4+2+2+1+1+8+2` (`video_header.py:15-25`), byte-exact `test_datagram.py:13-17`.
2. `REAL_HEADER_SIZE` is **computed** by packing an all-zero header at import — never hand-maintained (`config.py:16-17`).
3. `UDP_SAFE_PAYLOAD=1200`, `SIZE_MAX_PACKET=1176=1200−24` (`config.py:18-19`); payload 1177 raises `ValueError` (`test_datagram.py:31-37`).
4. Datagram: `header + payload`, `send_packet` returns `len(datagram)` in **both** transports (`udp_transport.py:21`, `zmq_pdu_transport.py:29`).
5. PDU frame: `07 06 0a 00 <len> 01 00` + datagram; car = nil (`PST_NULL`), length counts only the datagram (`pmt_codec.py:13-15`, `test_pmt_codec.py:5-12`).
6. Example: 3-B payload → 27-B datagram → 37-B frame (`test_zmq_pdu_transport.py:38-43`).
7. TX topology: Python **PUSH bind** 5555 (`config_radio.py:1,3`, `zmq_pdu_transport.py:18-23`); flowgraph **PULL connect** (`tx_bladerf.grc:70-72`).
8. RX topology: flowgraph **PUSH bind** 5556 (`rx_hackrf.grc:154-157`, `config_radio.py:2,4`); Python **PULL connect** (`zmq_pdu_receiver.py:21-27`).
9. Suite: 42 tests OK, exit 0, Python 3.13.13 / pyzmq 27.2.0 (full log `/tmp/opencode/testrun.txt`).
10. Real loopback over `inproc://` on the branch: `test_zmq_loopback_integration.py:19-32` (TX→RX, payload recovered).

## 6. Avoid saying (or say with a caveat)

- ❌ "The signal was transmitted and received at 20 Msps / 2.45 GHz." → RF is **`UNPROVEN`**; only the Python/ZMQ half is tested.
- ❌ "The wire is `cons(dict, u8vector)`" → the emitted car is **nil** (`06`), not a dict (`09`). Say: same PDU *shape*, nil metadata.
- ❌ "The branch is `19d88c8..1abeb05`" → correct range is `e1fead5..1abeb05` (14 commits; `19d88c8` is the first integration commit).
- ❌ "GNU Radio 3.10 has been validated here." → GNU Radio is **not installed** in this environment; flowgraphs are reference XML, only well-formedness is tested.
- ❌ Any claim about "the plan says…" as behavior truth → plan ≠ truth; CODE WINS.

## 7. Spoken summaries

**30 seconds:**
"We had a working UDP pipeline that turns H.264 from a webcam into framed datagrams — 24 bytes of header plus payload, up to 1200. We added GNU Radio without touching that logic: shared `datagram`/`Reassembler` code plus a transport factory. Flip `config.TRANSPORT` to `"radio"` and the same byte-exact datagram is wrapped in a GNU Radio PDU — 10 bytes of PMT prefix — pushed over ZMQ to a BladeRF flowgraph, and received back through a HackRF flowgraph into the same reassembler and ffplay. 42 tests pass with no hardware, no GNU Radio installed. What is not yet proven is the RF link itself — that's a manual checklist."

**2 minutes:**
"They started from a UDP-only H.264 live streamer. Camera → ffmpeg → Annex-B NAL units → parser → classifier by NAL type (SPS/PPS critical, IDR high) → fragmenter at 1176-byte units carrying a 24-byte big-endian header — sequence number, nalu id, fragment index/count, type, priority, monotonic timestamp, and payload size — capped at 1200 bytes per datagram. Receiver just reassembled by nalu id and fed ffplay.

"The integration's core idea: keep all of that, and replace only 'the wire'. A `Transport` ABC already existed; we extracted `build_datagram`/`parse_datagram` and a shared `Reassembler`, then added a factory keyed on `config.TRANSPORT`. UDP keeps sending the raw datagram; `"radio"` sends the same datagram wrapped in a GNU Radio PMT PDU — prefix `07 06 0a 00`, 32-bit length, one pad byte, then the datagram — over a PUSH socket bound to 5555. The BladeRF flowgraph PULLs, converts PDU to a tagged byte stream, GMSK-modulates and transmits. On RX the HackRF demodulates, rebuilds the PDU, PUSHes on 5556, and Python connects, decodes the PMT, parses the 24-byte header, and reuses the same reassembler before handing bytes to ffplay or dumping a `reconstructed_rf` file.

"Verification: the Python half is byte-proven — 42 stdlib unittests, no SDR, no GNU Radio binary needed; pyzmq is even optional thanks to tolerant imports, and a real ZMQ loopback runs over `inproc://`. The transparent caveat: acceptance of these exact bytes by GNU Radio's ZMQ/PDU blocks and the RF link remain unproven — only a manual hardware checklist. And if code ever disagrees with the plan, we document the code."

---

## 8. Source-to-slide map (handoff)

- Story stages → `04`, `05`, `06` (flows + bytes), `02` (before/after), `09` (plan vs truth).
- Numbers → `06` §6 evidence table (16 rows, all `VERIFIED` except the honest `INFERRED`/`UNPROVEN` ones).
- Open questions & limits → `03` §10.
- Tests → `08` (per-test matrix + runner command), full log `/tmp/opencode/testrun.txt`.
- Module map (Q&A / appendix slide) → `07`.