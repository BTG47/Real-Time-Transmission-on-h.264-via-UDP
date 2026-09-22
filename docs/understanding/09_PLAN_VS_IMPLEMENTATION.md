# 09 — Plan vs implementation

Purpose: diff the intended design (`PLAN_RADIO_ZMQ.md`) against what is actually on the branch (`e1fead5..1abeb05`, 14 commits ahead of `main`; first integration commit `19d88c8`).
**Ruling: `PLAN_RADIO_ZMQ.md` is the intended design, NOT the truth. When plan and code disagree, CODE WINS.** Every deviation below is tagged `VERIFIED` (read in both sources) unless noted.

---

## 1. Summary

| Item | Plan | Reality | Verdict |
|---|---|---|---|
| Scope declared | Tasks 1–7 (`PLAN_RADIO_ZMQ.md:1255`, "Tareas a ejecutar: 1 a 7") | Tasks 1–10 implemented (commits 8487857, 4e7fb94, 49484cb cover 8/9/10) | **CHANGED** (beyond declared scope) |
| New files on branch | 13 new files (`:28-40`) | all 13 exist (§2) | **MATCH** |
| Modified files | `udp_transport.py`, `reciever_nalu.py`, `capture.py`, `config.py`, `README.md` (`:42-47`) | all modified; `README.md` + `config.py` also have **uncommitted** working-tree changes | **MATCH** (plus local diff) |
| Test files | 7 new test files (`:40`) | 10 new + `test/__init__.py`; baseline had only `test_scheduler.py` (§4) | **CHANGED** (more tests than planned) |
| Wire contract prose | `cons(pmt::dict(), u8vector)` (`:19`, `:432`, `:1111`) | encoder emits `07 06 …` = **nil** car, not a dict (`pmt_codec.py:13-15`); plan's own code sketch (`:496-498`) also emits `07 06` | **PARTIAL** (plan prose vs its own sketch inconsistent; code follows the sketch) |
| `TRANSPORT` default | `"udp"` (`:46`, `:955`) | committed HEAD = `"udp"` (`config.py:13`); **working tree = `"radio"`** (uncommitted) | **MATCH** (committed) + local divergence noted |
| Endpoint roles | TX 5555 Python bind / flowgraph connect; RX 5556 flowgraph bind / Python connect (`:18`) | corrected in `1abeb05`; now matches | **MATCH** (after fix) |

## 2. File checklist (`VERIFIED`)

All 13 planned new files exist:

`packets/reassembler.py` · `transport/datagram.py` · `transport/transport_factory.py` · `radio/__init__.py` · `radio/config_radio.py` · `radio/pmt_codec.py` · `radio/zmq_pdu_transport.py` · `radio/zmq_pdu_receiver.py` · `radio/reciever_radio.py` · `radio/flowgraphs/tx_bladerf.grc` · `radio/flowgraphs/rx_hackrf.grc` · `radio/flowgraphs/README_FLOWGRAPHS.md` · `requirements-radio.txt` — all present on the branch.

## 3. Per-task verdicts

| Task | Plan intent (`PLAN_RADIO_ZMQ.md`) | Implementation | Verdict |
|---|---|---|---|
| 1 — `transport/datagram.py` + refactor `udp_transport.py` (`:51`) | `build_datagram`/`parse_datagram`, byte-exact 24 B/1200 B, `UdpTransport` delegates keeping DEBUG print + `ValueError` | `datagram.py:5-19`; `udp_transport.py:6,14,15-19` | **MATCH** |
| 2 — `packets/reassembler.py` + refactor `reciever_nalu.py` (`:174`) | shared `Reassembler`, handoff cases A–F + §8.8 validation | `reassembler.py:4-37` (validations `:17-29`, idempotent overwrite `:31`, index-order join `:33-36`); `reciever_nalu.py:7,32,63` | **MATCH** (extra: radio receiver also reuses it, `zmq_pdu_receiver.py:7,52`) |
| 3 — `radio/config_radio.py` (`:369`) | endpoints 5555/5556, roles, timeouts | 5 constants `config_radio.py:1-5` | **MATCH** |
| 4 — `radio/pmt_codec.py` (`:422`) | bit-compatible codec | `encode_u8vector_pdu` follows plan's code sketch byte-for-byte (`pmt_codec.py:13-15` == `plan:496-498`); decoder generalized + hardened (see §5) | **PARTIAL** — see §5 (depth guard, `_read_exact` bug, prose-vs-sketch) |
| 5 — `radio/zmq_pdu_transport.py` + `requirements-radio.txt` (`:577`) | `ZMQPduTransport(Transport)`, PUSH bind 5555 | `zmq_pdu_transport.py:11-37`; `requirements-radio.txt` present; tolerant pyzmq import (`:1-4`) | **MATCH** (tolerant import = supportive off-plan detail) |
| 6 — `radio/zmq_pdu_receiver.py` (`:722`) | `ZMQPduReceiver`, `run_recv_loop`, `main`; PULL connect 5556 | `zmq_pdu_receiver.py:14-84`; `TIMEOUT_EXCEPTION` fallback `:12`; tolerant import `:2-5` | **MATCH** |
| 7 — `transport_factory.py` + `config.py` + `capture.py` (`:899`) | `get_transport()` switch; `TRANSPORT="udp"`; `capture.py` uses it | `transport_factory.py:3-13` matches plan sketch (`plan:960-972`) verbatim; `capture.py:5,20`; committed `config.py:13="udp"` | **MATCH** (working tree: `"radio"`, uncommitted) |
| 8 — `radio/reciever_radio.py` (`:993`) | executable RX launcher | exists, `reciever_radio.py:1-4` | **IMPLEMENTED beyond declared scope 1–7** |
| 9 — flowgraphs (`:1046`) | reference XML BladeRF TX / HackRF RX + README checklist | `tx_bladerf.grc`, `rx_hackrf.grc`, `README_FLOWGRAPHS.md` exist; roles corrected in `1abeb05` | **MATCH** (structure); behavior **CANNOT VERIFY** (no GNU Radio/hardware; only well-formedness tested, `test_flowgraphs.py:6-10`) |
| 10 — `README.md` + optional real loopback (`:1127`) | "Modo radio" section; `skipUnless(pyzmq)` loopback | section present; `test_zmq_loopback_integration.py:18` `TestZmqLoopback` with `@unittest.skipUnless(HAVE_ZMQ, …)` | **MATCH (implemented despite "opcional" + scope 1–7)** |

## 4. Test inventory (`VERIFIED`)

- Baseline (`main`/merge-base `e1fead5`): only `test/test_scheduler.py`.
- Branch adds: `test/__init__.py` (commit `a3105ec` — not in plan's file list), `test_datagram.py`, `test_reassembler.py`, `test_pmt_codec.py`, `test_zmq_pdu_transport.py`, `test_zmq_pdu_receiver.py`, `test_radio_config.py`, `test_reciever_radio.py`, `test_transport_factory.py`, `test_flowgraphs.py`, `test_zmq_loopback_integration.py`.
- Plan named 7 (`:40`); reality = 10 new files + package marker. Extra vs plan: `test_radio_config.py`, `test_reciever_radio.py`, `test_zmq_loopback_integration.py`, `test/__init__.py`.
- Suite result (Python 3.13.13, pyzmq 27.2.0 installed): `python3 -m unittest discover -s test -p "test_*.py" -v` → 42 tests OK, exit 0; 2 cosmetic `ResourceWarning`s. The loopback runs (pyzmq present). See `08_TESTS_AND_EVIDENCE.md`; full log at `/tmp/opencode/testrun.txt`.

## 5. Specific discrepancies found (all `VERIFIED`)

1. **`_read_exact` position bug — FIXED in code.** Plan sketch returns `data[pos:end], pos` (`plan:504`), which would never advance the cursor → infinite loop/truncation on single-object frames. Code returns `data[pos:end], end` (`pmt_codec.py:21`). Intent: fix a real bug; the plan doc itself was wrong.
2. **Stack-depth guard added off-plan.** Code adds `depth=0` param + `_MAX_DEPTH = 64` and raises `PmtDecodeError("anidamiento PMT excede…")` on PAIR/DICT (`pmt_codec.py:11,44-46`) and TUPLE/VECTOR (`:63-64`). Plan's `_parse(data, pos=0)` (`plan:506`) has no depth limit. Committed as `a1a531e`.
3. **pyzmq-tolerant production imports — off-plan detail.** Plan only mocked pyzmq in tests (`plan:21`) and wrapped the factory import (`plan:965-970`); it did not anticipate the **production modules** importing a possibly-missing `zmq`. Code guards `zmq_pdu_transport.py:1-4`, `zmq_pdu_receiver.py:2-5`, and `TIMEOUT_EXCEPTION = getattr(zmq, "Again", TimeoutError)` (`zmq_pdu_receiver.py:12`) — commit `6aed77d`, so the suite runs even without pyzmq.
4. **Scope exceeded: Tasks 8–10 implemented.** `PLAN_RADIO_ZMQ.md:1255` says execute tasks 1–7; commits for 8 (`8487857`), 9 (`4e7fb94`) and 10 (`49484cb`) follow. Net positive per self-review (`plan:1240-1249`) — the extra deliverables match the plan's own tasks, just beyond the stated execution window.
5. **Test class name typo.** Plan sketch: `TestZmolLoopback` (`plan:1156`); actual: `TestZmqLoopback` (`test_zmq_loopback_integration.py:18`). Cosmetic; would not affect discovery (`unittest` matches `*SimpRtp*`-style by prefix anyway).
6. **README cites a nonexistent file.** `README.md:19,86,387,515` reference `HANDOFF_CPP_UDP_H264_v2.md`; the actual file is `HANDOFF_CPP_UDP_H264.md` (plan:10 got the name right). Pre-existing README inconsistency (not a plan deviation).
7. **Wire `car` semantics vs prose.** Plan global constraint and Task 4 prose say `pdu = pmt::cons(pmt::dict(), pmt::init_u8vector(datagrama))` (`plan:19`) and "compatibility `cons(dict, u8vector)`" (`:432`, `:1111`). The implementation (and the plan's own `encode_u8vector_pdu` sketch, `plan:496-498`) emits `07 06 …` where `06` = `PST_NULL` → the car is **nil**, not a dict (`pmt_codec.py:13-15`, hexdump §3/`06_PACKET_AND_PDU_FORMAT.md`). Docs that repeat the `cons(dict,u8vector)` wording (`README_FLOWGRAPHS.md:61-70`) are looser than the bytes; code wins. GNU-Radio-side acceptance of the nil-car form remains `UNPROVEN`.
8. **Endpoint role correction commit.** `1abeb05` "docs: corregir rol bind/connect" realigned the flowgraph README/params to the plan's topology (`plan:18`): TX flowgraph `connect` on 5555, RX flowgraph `bind` on 5556. Consistent with `config_radio.py:3-4`, `zmq_pdu_transport.py:20-21`, `zmq_pdu_receiver.py:23-24`.

## 6. Plan self-review claims — spot-check

| Plan claim (`plan:1240-1251`) | Code evidence | Verdict |
|---|---|---|
| Baseline intact (delegation only) | `capture.py` loop body unchanged; `UdpTransport` still prints header under DEBUG (`udp_transport.py:15-19`, builds via `build_datagram`); `reciever_nalu.py` delegates to `Reassembler` | **MATCH** |
| ABC `Transport` respected | `zmq_pdu_transport.py:11` `class ZMQPduTransport(Transport)` implements `send_packet -> int`, `close` | **MATCH** |
| Header 24 B + ≤ 1200 B + overflow ValueError | `datagram.py:10-12`; tests `test_datagram.py:31-37` | **MATCH** |
| Only real socket = loopback `skipUnless(pyzmq)` `inproc://` | `test_zmq_loopback_integration.py` | **MATCH** (but on this machine pyzmq is installed → it actually runs, 42 tests) |
| Flowgraphs manual verify | `UNPROVEN` on this machine (no GNU Radio/hardware) | **CANNOT VERIFY** |

## 7. Unresolved / follow-ups

- `config.py:13` working-tree `"radio"` vs committed `"udp"` is uncommitted — the repo default and the runtime differ until that diff is committed (intentional per project direction; flag only).
- README `HANDOFF_CPP_UDP_H264_v2.md` → `HANDOFF_CPP_UDP_H264.md` citational fix pending (docs-only).
- GNU Radio byte acceptance + RF path remain `UNPROVEN` (hardware checklist `README_FLOWGRAPHS.md:72-81`).