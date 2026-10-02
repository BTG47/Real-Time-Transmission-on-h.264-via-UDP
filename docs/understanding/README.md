# Understanding the GNU Radio / ZMQ Integration

Architecture reconstruction and change documentation for the H.264 real-time
transmission prototype, focused on the integration of GNU Radio through ZMQ PDU
transport (branch `blade_protocol_adaptation`).

Every document is built from repository evidence. Claims distinguish:

- `VERIFIED` — directly read from source code or a passing test.
- `INFERRED` — derived from architecture/naming.
- `PLAN_ONLY` — stated only in `PLAN_RADIO_ZMQ.md`.
- `UNPROVEN` — no evidence; treated as unknown.

Rule: **the code is truth**; `PLAN_RADIO_ZMQ.md` records intent before
implementation.

## Index

| Doc | Content |
|-----|---------|
| [`01_CHANGE_SUMMARY.md`](01_CHANGE_SUMMARY.md) | What the system did before, what the integration adds, what changed and what stayed compatible. |
| [`02_BEFORE_AFTER.md`](02_BEFORE_AFTER.md) | Visual before/after of the architecture (old UDP route vs new radio route). |
| [`03_ARCHITECTURE.md`](03_ARCHITECTURE.md) | C4-style architecture: containers, modules, transport abstraction, radio, GNU Radio, receiver. |
| [`04_TX_FLOW.md`](04_TX_FLOW.md) | Transmit path, step by step, with concrete byte-level traces. |
| [`05_RX_FLOW.md`](05_RX_FLOW.md) | Receive path, step by step, from GNU Radio / ZMQ to ffplay. |
| [`06_PACKET_AND_PDU_FORMAT.md`](06_PACKET_AND_PDU_FORMAT.md) | The 24-byte `VideoHeader`, 1200-byte datagram ceiling, and the GNU Radio PMT/PDU wire format. |
| [`07_MODULE_GUIDE.md`](07_MODULE_GUIDE.md) | Per-module guide: purpose, responsibilities, callers, inputs/outputs, failures, examples. |
| [`08_TESTS_AND_EVIDENCE.md`](08_TESTS_AND_EVIDENCE.md) | What the test suite proves and the exact run + results. |
| [`09_PLAN_VS_IMPLEMENTATION.md`](09_PLAN_VS_IMPLEMENTATION.md) | `PLAN_RADIO_ZMQ.md` vs actual code, classified MATCH/PARTIAL/CHANGED/NOT IMPLEMENTED/CANNOT VERIFY. |
| [`SLIDES_HANDOFF.md`](SLIDES_HANDOFF.md) | Distilled source for building a presentation: story, slide sequence, facts, warnings. |

## Diagrams (`diagrams/`)

| File | View |
|------|------|
| `before-after.mmd` | Old UDP route vs new GNU Radio/ZMQ route. |
| `system-context.mmd` | C4 system context: app, camera/ffmpeg, GNU Radio, SDR, ffplay. |
| `module-dependencies.mmd` | Python module dependency graph. |
| `tx-sequence.mmd` | Transmit sequence diagram. |
| `rx-sequence.mmd` | Receive sequence diagram. |
| `packet-format.mmd` | Datagram → PMT/PDU → ZMQ frame layout. |

## Suggested reading order

Start from `01_CHANGE_SUMMARY.md` → `02_BEFORE_AFTER.md` → `04/05_TX_RX_FLOW.md`
→ `06_PACKET_AND_PDU_FORMAT.md`. For the full picture, overlay
`09_PLAN_VS_IMPLEMENTATION.md`.

## Quick command reference

```bash
# Full test suite (read-only evidence)
python3 -m unittest discover -s test -v

# List installed project skills
npx skills list
```