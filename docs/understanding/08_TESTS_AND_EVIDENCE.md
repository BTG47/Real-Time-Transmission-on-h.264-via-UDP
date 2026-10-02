# 08 — Tests and Evidence

> What the suite proves, how it was run, and the exact result. All tests are
> `unittest` (stdlib). Evidence for this document: the test sources under
> `test/` and one fresh run, below.

## Run (reproducible)

```bash
python3 -m unittest discover -s test -p "test_*.py" -v
```

Fresh execution on 2026-09-22, Python 3.13.13, pyzmq 27.2.0:

```
Ran 42 tests in 0.075s
OK
```

- **Result:** all 42 tests pass.
- **Skips:** none (the ZMQ loopback tests ran because pyzmq is installed; they
  are `skipUnless(HAVE_ZMQ)` and would skip where pyzmq is absent).
- **Warnings (cosmetic, non-failing):** two `ResourceWarning: unclosed socket`
  — one from `UdpTransport` created in `test_transport_factory.py:9` (no `close`
  in that test), and one from `test_scheduler.py`'s module-level `UdpTransport()`.
  `test_scheduler.py` also prints `Enqueue.../Hay paquetes/Transportando...` from
  its own `print` statements. Neither affects the verdict.

## What each behavior proved — right next to the code

### `test_datagram.py` — the shared wire contract

| Test | Proves |
|---|---|
| `test_header_layout_is_24_bytes` | `VideoHeader.to_bytes()` layout is byte-exact big-endian: 24 bytes `!IIHHBBQH` → `00 00 00 01 | 00 00 00 02 | 00 03 | 00 04 | 05 | 01 | 11 22 33 44 55 66 77 88 | 00 06` |
| `test_roundtrip` | `build_datagram` → `parse_datagram` round-trips unchanged (1024 B payload → 1048 B datagram); `payload_size` == payload length |
| `test_max_payload_1176_ok` | a 1176-byte payload produces exactly a 1200-byte datagram (the ceiling) |
| `test_oversized_raises` | a 1177-byte payload raises `ValueError` (`transport/datagram.py:10-12`) — the overflow guard |
| `test_parse_short_raises` | parsing fewer than 24 bytes raises `ValueError` |

→ These are the same bytes that cross UDP **and** ZMQ; the radios carry them
opaquely (`transport/datagram.py:5-19`).

### `test_reassembler.py` — shared reassembly semantics (handoff cases A–F + §8.8)

| Test | Proves |
|---|---|
| `test_caso_A_orden_normal` / `test_caso_A_reconstruye_orden` | in-order fragments (0,1,2) reassemble into `f0+f1+f2` and clear the pending entry; a completed NALU can be re-created (new pending set for same id) |
| `test_caso_B_desordenados` | out-of-order delivery reassembles correctly by index |
| `test_caso_C_intercaladas_no_mezcla` | fragments of two NALUs interleaved do NOT mix (keyed by `nalu_id`) |
| `test_caso_D_duplicado_no_duplica` | a duplicate fragment does not duplicate its content |
| `test_caso_E_fragmento_perdido_queda_pendiente` | a missing fragment leaves the NALU pending (no premature output) |
| `test_caso_F_nalu_posterior_completa_antes` | a later NALU can complete before an earlier one |
| `test_validacion_count_menor_igual_cero` | `fragment_count <= 0` is rejected (returns `None`) |
| `test_validacion_index_fuera_de_rango` | `fragment_index` outside `[0, count)` is rejected |
| `test_validacion_payload_size_incorrecto` | `payload_size != len(payload)` is rejected |
| `test_validacion_fragment_count_inconsistente` | a fragment reusing `nalu_id` with a different `fragment_count` is rejected |

→ These are the exact rules documented as §8.8 in `HANDOFF_CPP_UDP_H264.md` and
implemented in `packets/reassembler.py:17-36`. Both receivers (UDP and radio)
depend on them (`reciever_nalu.py:63`, `radio/zmq_pdu_receiver.py:52`).

### `test_pmt_codec.py` — GNU Radio PMT wire compatibility

| Test | Proves |
|---|---|
| `test_encode_vacio` | empty payload → exact frame `07 06 0a 00 00 00 00 00 01 00` |
| `test_encode_1200_bytes` | prefix `07 06 0a 00 00 00 04 b0 01 00` (=10 bytes), total frame 1210 bytes for a 1200-byte datagram |
| `test_roundtrip` | `encode_u8vector_pdu` → `decode_pdu_data` round-trips byte-identical payloads |
| `test_decode_con_metadatos` | decoder tolerates a PDU whose CAR is a real dict (`acons("x",42)`) and still returns the trailing u8vector |
| `test_decode_truncado` | truncated PMT raises `PmtDecodeError` |
| `test_decode_tag_desconocido` | unknown PMT tag raises `PmtDecodeError` |
| `test_decode_cdr_final_no_u8vector` | PDU whose final CDR is not a u8vector raises `PmtDecodeError` |
| `test_decode_sobras` | trailing bytes after the PMT message raise `PmtDecodeError` |
| `test_decode_anidamiento_excesivo` | deep nesting (1000 `0x07`) raises `PmtDecodeError` (the `_MAX_DEPTH=64` guard) |

→ This is the bit-compatible `pmt::serialize_str(cons(dict, u8vector))` codec
(`radio/pmt_codec.py`) that makes GNU Radio ZMQ message blocks accept the frames.

### `test_radio_config.py` — endpoint / role contract

| Test | Proves |
|---|---|
| `test_endpoints_por_especificacion` | TX `tcp://127.0.0.1:5555`, RX `tcp://127.0.0.1:5556` |
| `test_roles_bind_connect` | Python TX **binds** (PUSH), Python RX **connects** (PULL) |

→ Matches `radio/config_radio.py:1-5` and the flowgraph roles in
`radio/flowgraphs/README_FLOWGRAPHS.md:34-39`.

### `test_zmq_pdu_transport.py` — TX adapter behavior

| Test | Proves |
|---|---|
| `test_envia_frame_pdu_con_tam_correcto` | with payload `b"\x01\x02\x03"`, `send_packet` returns **27** (= 24 B header + 3 B payload) and the emitted frame equals `encode_u8vector_pdu(build_datagram(packet))` exactly |
| `test_datagrama_demasiado_grande_levanta` | oversized payload raises `ValueError` and nothing is sent |
| `test_close_cierra_socket` | `close()` closes the socket (linger 0) |
| `test_fabrica_socket_push_bind_sin_inyeccion` | with no injection, the transport creates a PUSH socket (stype 8) **bound** to `tcp://127.0.0.1:5555` |

→ Proves `ZMQPduTransport` honors the `Transport` ABC and the wire format.

### `test_zmq_pdu_receiver.py` — RX adapter behavior

| Test | Proves |
|---|---|
| `test_recv_timeout_devuelve_datagrama` | `recv_timeout()` returns the **decoded datagram bytes** (PDU → datagram), not the raw frame |
| `test_recv_timeout_timeout_devuelve_none` | on `zmq.Again`-style timeout it returns `None` (the loop's stop signal) |
| `test_run_recv_loop_reensambla` | `run_recv_loop` feeds `Reassembler` and calls `on_nalu` with the rebuilt NALU (`AAA`+`BBB` → `AAABBB`) |
| `test_close` | `close()` closes the pull socket |

### `test_transport_factory.py` — selection logic

| Test | Proves |
|---|---|
| `test_udp_por_defecto` | `TRANSPORT = "udp"` → `UdpTransport` instance |
| `test_radio_devuelve_zmq` | `TRANSPORT = "radio"` → `ZMQPduTransport` instance |
| `test_radio_sin_pyzmq_levanta_error_claro` | `radio` mode without pyzmq raises a clear `RuntimeError` pointing at `requirements-radio.txt` |

→ Proves the factory switch (`transport/transport_factory.py:3-13`) and the
pyzmq-missing failure mode.

### `test_zmq_loopback_integration.py` — real ZMQ round trip (skipUnless pyzmq)

| Test | Proves |
|---|---|
| `test_tx_rx_loopback_inproc` | a real `zmq.Context` on `inproc://` moves an encoded PDU from `ZMQPduTransport` (PUSH bind) to `ZMQPduReceiver` (PULL connect); the decoded datagram parses back to `nalu_id=7`, payload `XYZ` |
| `test_loopback_reensamblado` | two fragments (`AA`,`BB`) across two PDU frames reassemble into `AABB` through the full TX→ZMQ→RX→Reassembler chain |

→ The only test exercising real ZMQ sockets (not mocks). It runs here because
pyzmq 27.2 is installed.

### `test_reciever_radio.py` — entry point smoke

| Test | Proves |
|---|---|
| `test_modulo_importa_y_compila` | `radio/reciever_radio.py` compiles and imports cleanly |

### `test_flowgraphs.py` — flowgraph sanity

| Test | Proves |
|---|---|
| `test_grc_son_xml_valido` | every `radio/flowgraphs/*.grc` is well-formed XML |

→ This is intentionally the ONLY claim about the flowgraphs that the suite can
make: GNU Radio is not installed here, so block semantics are unchecked.
`README_FLOWGRAPHS.md:72-81` lists the manual hardware checklist.

### `test_scheduler.py` — pre-existing priority scheduling

Module-level script: enqueues 2 HIGH then 1 CRITICAL and dequeues until empty,
printing `Enqueue.../Hay paquetes/Transportando...`. It exercises
`PacketScheduler` ordering through `UdpTransport.send_packet` (loopback UDP).
It is **not** an assertion-based unit test (no asserts); it would fail only if an
exception is raised. Carries the cosmetic `ResourceWarning` noted above.

## What the results tell us

1. The **wire format is stable and shared**: 24 B header + ≤1200 B datagram,
   round-trips byte-identical (`test_datagram.py`).
2. **Reassembly rules hold** for both receivers: ordering, duplicates,
   interleaving, validation — same class, same tests (`test_reassembler.py`).
3. **PMT codec is GNU-Radio-compatible** at the byte level, including the
   10-byte prefix and error handling (`test_pmt_codec.py`).
4. **TX and RX adapters behave as designed** with mock sockets, and the
   **real-ZMQ path works** end to end via `inproc://` (`test_zmq_*`).
5. **Selection and failure modes are explicit** (`test_transport_factory.py`).
6. The **radio link itself is not proven** by this suite — only the XML of the
   flowgraphs is validated (`test_flowgraphs.py`); RF behavior remains
   `UNPROVEN`/manual («Checklist de verificación en hardware»).