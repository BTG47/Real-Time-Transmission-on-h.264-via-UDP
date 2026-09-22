# PLAN_RADIO_ZMQ — Extensión Radio (GNU Radio + ZMQ PDU)

**Goal:** Extender el baseline UDP de streaming H.264 en tiempo real para transportar el datagrama de 24 bytes de `VideoHeader` + payload (≤1200 B) entre Python y flowgraphs GNU Radio vía sockets locales ZMQ en formato PDU, manteniendo intacto el transporte UDP actual y permitiendo alternar ambos mediante una fábrica.

**Architecture:** Se crea un paquete `radio/` aislado que implementa el codec PMT de GNU Radio (bit-compatible con `pmt::serialize_str`) y dos adaptadores ZMQ: TX (`ZMQPduTransport`, cumple la ABC `Transport`) y RX (`ZMQPduReceiver`) que reutiliza un `Reassembler` compartido extraído de `reciever_nalu.py` (DRY). `UdpTransport` y `reciever_nalu.py` se refactorizan para delegar en los módulos compartidos sin cambiar comportamiento (regresión cubierta por tests). La selección de transporte se hace con `get_transport()` según `config.TRANSPORT`.

**Tech Stack:** Python 3.11 (stdlib), `unittest` + `unittest.mock` (tests), `pyzmq` (solo para la ruta radio, en `requirements-radio.txt`), GNU Radio 3.10/3.11 (`ZMQ PULL Message Source`, `ZMQ PUSH Message Sink`, PDU↔Tagged Stream), flowgraphs de referencia para BladeRF (gr-bladeRF) y HackRF (gr-osmosdr).

**Spec:**
- `HANDOFF_CPP_UDP_H264.md` (contrato binario §4, reensamblado §8–§10, prioridades §4, scheduler §4)
- `README.md` (estructura, config, flujo, métricas)

## Global Constraints

- Baseline UDP intacto: no cambiar semántica ni métricas de `capture.py`, `reciever_nalu.py`, `UdpTransport`. Cambios únicamente para delegar en módulos compartidos, con tests de regresión.
- ABC `Transport` intocable y respetada: `send_packet(packet: NALUPacket) -> int`, `close() -> None` (`transport/transport.py`).
- Contrato binario: `VideoHeader` de 24 B con `!IIHHBBQH` (big-endian); datagrama `[header 24 B][payload]` con máximo `UDP_SAFE_PAYLOAD = 1200` bytes y payload máximo `SIZE_MAX_PACKET = 1176`.
- Endpoints ZMQ (loopback): TX `tcp://127.0.0.1:5555` (Python `bind` como PUSH; el flowgraph hace `connect` con `ZMQ PULL Message Source`); RX `tcp://127.0.0.1:5556` (el flowgraph hace `bind` con `ZMQ PUSH Message Sink`; Python hace `connect` como PULL). Convención GNU Radio: sinks bind, sources connect.
- Wire "PDU" sobre ZMQ = `pmt::serialize_str(pdu)` con `pdu = pmt::cons(pmt::dict(), pmt::init_u8vector(datagrama))` (formato GNU Radio mainline).
- El payload del PDU es el **datagrama completo** (24 B header + payload); el radio lo transporta de forma opaca.
- Tests: `unittest` de stdlib, corridos desde la raíz con `python -m unittest discover -s test -v`. Sin hardware, sin GNU Radio, sin red física. `pyzmq` se mockea o se usa en un test opcional `skipUnless`.
- Orden y nombres son exactos: los nombres de módulos/funciones definidos en tareas previas se reutilizan tal cual.

---

## Mapa de archivos

**Nuevos**
- `packets/reassembler.py` — clase `Reassembler` (reensamblado por `nalu_id`/`fragment_index`, reglas §8.8).
- `transport/datagram.py` — `build_datagram(packet)`, `parse_datagram(data)` (contrato de 24 B/1200 B, DRY).
- `transport/transport_factory.py` — `get_transport()` (selcción UDP/radio).
- `radio/__init__.py`
- `radio/config_radio.py` — endpoints 5555/5556, rol bind/connect, timeouts.
- `radio/pmt_codec.py` — `encode_u8vector_pdu()`, `decode_pdu_data()`, `PmtDecodeError`.
- `radio/zmq_pdu_transport.py` — `ZMQPduTransport(Transport)`.
- `radio/zmq_pdu_receiver.py` — `ZMQPduReceiver`, `run_recv_loop()`, `main()`.
- `radio/reciever_radio.py` — script ejecutable del receptor radio (≈ reciever_nalu).
- `radio/flowgraphs/tx_bladerf.grc`, `radio/flowgraphs/rx_hackrf.grc`, `radio/flowgraphs/README_FLOWGRAPHS.md`.
- `requirements-radio.txt` — `pyzmq`.
- Tests en `test/`: `test_datagram.py`, `test_reassembler.py`, `test_pmt_codec.py`, `test_zmq_pdu_transport.py`, `test_zmq_pdu_receiver.py`, `test_transport_factory.py`, `test_flowgraphs.py`.

**Modificados (solo delegación, comportamiento idéntico)**
- `transport/udp_transport.py` — usa `build_datagram` (mantiene print DEBUG y `ValueError`).
- `reciever_nalu.py` — usa `Reassembler` (elimina función/estado global).
- `capture.py` — usa `get_transport()` en vez de `UdpTransport()`.
- `config.py` — añade `TRANSPORT = "udp"` (`"udp"` | `"radio"`).
- `README.md` — sección "Modo radio (GNU Radio + SDR)" (documentación).

---

### Task 1: Código compartido de datagrama (`transport/datagram.py`)

**Files:**
- Create: `transport/datagram.py`
- Modify: `transport/udp_transport.py:13-43`
- Test: `test/test_datagram.py`

**Interfaces:**
- Consumes: `NALUPacket` (`packets/packetizer.py`), `VideoHeader` (`transport/video_header.py`), `UDP_SAFE_PAYLOAD`/`REAL_HEADER_SIZE` (`config.py`).
- Produces: `build_datagram(packet: NALUPacket) -> bytes` (lanza `ValueError` si >1200 y devuelve `header.to_bytes() + payload`); `parse_datagram(data: bytes) -> tuple[VideoHeader, bytes]` (lanza `ValueError` si `len(data) < REAL_HEADER_SIZE`).

- [ ] **Step 1: Escribir el test que falla**

```python
import unittest
from packets.packetizer import NALUPacket
from packets.priority_classifier import Priority
from transport.video_header import VideoHeader
from transport.datagram import build_datagram, parse_datagram

def make_packet(payload: bytes, nalu_id=1, index=0, count=1, type_=5, priority=Priority.HIGH, seq=7, ts=0x1122334455667788):
    return NALUPacket(packet_sequence=seq, nalu_id=nalu_id, fragment_index=index,
                      fragment_count=count, nal_type=type_, priority=priority,
                      timestamp_ns=ts, payload=payload)

class TestDatagram(unittest.TestCase):
    def test_header_layout_is_24_bytes(self):
        header = VideoHeader(1, 2, 3, 4, 5, Priority.HIGH, 0x1122334455667788, 6)
        self.assertEqual(header.to_bytes(),
                         b"\x00\x00\x00\x01\x00\x00\x00\x02\x00\x03\x00\x04" +
                         b"\x05\x01\x11\x22\x33\x44\x55\x66\x77\x88\x00\x06")

    def test_roundtrip(self):
        payload = bytes(range(256)) * 4          # 1024 bytes
        datagram = build_datagram(make_packet(payload, nalu_id=42, index=2, count=5, type_=1))
        self.assertEqual(len(datagram), 1024 + 24)
        header, parsed = parse_datagram(datagram)
        self.assertEqual(header.nalu_id, 42)
        self.assertEqual(header.fragment_index, 2)
        self.assertEqual(header.fragment_count, 5)
        self.assertEqual(header.nal_type, 1)
        self.assertEqual(header.payload_size, 1024)
        self.assertEqual(parsed, payload)

    def test_max_payload_1176_ok(self):
        datagram = build_datagram(make_packet(b"x" * 1176))
        self.assertEqual(len(datagram), 1200)

    def test_oversized_raises(self):
        with self.assertRaises(ValueError):
            build_datagram(make_packet(b"x" * 1177))

    def test_parse_short_raises(self):
        with self.assertRaises(ValueError):
            parse_datagram(b"\x00" * 20)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m unittest test.test_datagram -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'transport.datagram'`.

- [ ] **Step 3: Implementación mínima**

```python
from config import UDP_SAFE_PAYLOAD, REAL_HEADER_SIZE
from packets.packetizer import NALUPacket
from transport.video_header import VideoHeader

def build_datagram(packet: NALUPacket) -> bytes:
    header = VideoHeader(packet.packet_sequence, packet.nalu_id, packet.fragment_index,
                         packet.fragment_count, packet.nal_type, packet.priority,
                         packet.timestamp_ns, len(packet.payload))
    data = header.to_bytes() + packet.payload
    if len(data) > UDP_SAFE_PAYLOAD:
        raise ValueError(f"Datagrama demasiado grande: {len(data)} bytes "
                         f"(header={len(header.to_bytes())}, payload={len(packet.payload)})")
    return data

def parse_datagram(data: bytes) -> tuple[VideoHeader, bytes]:
    if len(data) < REAL_HEADER_SIZE:
        raise ValueError(f"Datagrama demasiado corto: {len(data)} bytes")
    header = VideoHeader.from_byte(data[:REAL_HEADER_SIZE])
    return header, data[REAL_HEADER_SIZE:]
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m unittest test.test_datagram -v`
Expected: 5 passed.

- [ ] **Step 5: Refactorizar `UdpTransport.send_packet` para reutilizarlo (DRY), preservando DEBUG y ValueError**

```python
    def send_packet(self, packet: NALUPacket) -> int:
        data_to_send = build_datagram(packet)
        if DEBUG:
            header = VideoHeader(packet.packet_sequence, packet.nalu_id, packet.fragment_index,
                                 packet.fragment_count, packet.nal_type, packet.priority,
                                 packet.timestamp_ns, len(packet.payload))
            print(header)
        self.sender_socket.sendto(data_to_send, (SERVER_IP, SERVER_PORT))
        return len(data_to_send)
```
(importar `from transport.datagram import build_datagram`, `from transport.video_header import VideoHeader`.)

- [ ] **Step 6: Regresión del baseline**

Run: `python -m unittest discover -s test -v`
Expected: PASS. Luego `python -m py_compile transport/udp_transport.py capture.py reciever_nalu.py config.py`

- [ ] **Step 7: Commit**

```bash
git add transport/datagram.py transport/udp_transport.py test/test_datagram.py
git commit -m "refactor: extraer código compartido de datagrama (header 24B + <=1200B)"
```

---

### Task 2: `Reassembler` compartido (`packets/reassembler.py`) + refactor de `reciever_nalu.py`

**Files:**
- Create: `packets/reassembler.py`
- Modify: `reciever_nalu.py:30-78,108-109`
- Test: `test/test_reassembler.py`

**Interfaces:**
- Consumes: `VideoHeader`, reglas de validación §8.8.
- Produces: `class Reassembler` con `__init__(self)`, `property pending_count -> int`, `feed(self, header: VideoHeader, payload: bytes) -> Optional[bytes]` (devuelve la NALU completa cuando todos los `[0, fragment_count)` están presentes y la elimina de pendientes; `None` en caso contrario o si el datagrama es inválido).

- [ ] **Step 1: Escribir el test que falla (casos A–F del handoff §10 + validación §8.8)**

```python
import unittest
from packets.reassembler import Reassembler
from transport.video_header import VideoHeader
from packets.priority_classifier import Priority

def hdr(nalu_id, index, count, payload_size, seq=1, nal_type=1, priority=Priority.NORMAL):
    return VideoHeader(seq, nalu_id, index, count, nal_type, priority, 0, payload_size)

F0, F1, F2 = b"AAA", b"BBB", b"CCC"   # payloads distintos por NALU

def payload_for(nalu_id, index):
    base = bytes([65 + nalu_id])
    return base * (3 + index)         # contenido distinguible por nalu id

class TestReassembler(unittest.TestCase):
    def test_caso_A_orden_normal(self):
        r = Reassembler()
        for i in range(3):
            self.assertIsNone(r.feed(hdr(10, i, 3, 3), bytes([i]) * 3))
        n = r.feed(hdr(10, 0, 3, 3), b"\x00" * 3)
        self.assertIsNone(n)                       # len(fragments) < count no completa nada nuevo
        self.assertEqual(r.pending_count, 1)

    def test_caso_A_reconstruye_orden(self):
        r = Reassembler()
        for i in range(3):
            r.feed(hdr(10, i, 3, 3), F0 if i == 0 else (F1 if i == 1 else F2))
        r.feed(hdr(10, 1, 3, 3), F1)               # 0,1,2 ya en orden; feed 1 no cierra nada
        self.assertEqual(r.pending_count, 0)

    def test_caso_B_desordenados(self):
        r = Reassembler()
        for i in (2, 0, 1):
            r.feed(hdr(10, i, 3, 3), payload_for(10, i))
        result = r.feed(hdr(10, 1, 3, 3), payload_for(10, 1))
        self.assertEqual(result, payload_for(10, 0) + payload_for(10, 1) + payload_for(10, 2))

    def test_caso_C_intercaladas_no_mezcla(self):
        r = Reassembler()
        r.feed(hdr(10, 0, 2, 3), payload_for(10, 0))
        self.assertIsNone(r.feed(hdr(11, 0, 2, 3), payload_for(11, 0)))
        self.assertIsNone(r.feed(hdr(10, 1, 2, 3), payload_for(10, 1)))
        result11 = r.feed(hdr(11, 1, 2, 3), payload_for(11, 1))
        self.assertEqual(result11, payload_for(11, 0) + payload_for(11, 1))
        result10 = r.feed(hdr(10, 0, 2, 3), payload_for(10, 0))
        self.assertEqual(result10, payload_for(10, 0) + payload_for(10, 1))

    def test_caso_D_duplicado_no_duplica(self):
        r = Reassembler()
        r.feed(hdr(10, 0, 2, 3), payload_for(10, 0))
        r.feed(hdr(10, 0, 2, 3), payload_for(10, 0))   # duplicado
        r.feed(hdr(10, 1, 2, 3), payload_for(10, 1))
        result = r.feed(hdr(10, 0, 2, 3), payload_for(10, 0))
        self.assertEqual(result, payload_for(10, 0) + payload_for(10, 1))

    def test_caso_E_fragmento_perdido_queda_pendiente(self):
        r = Reassembler()
        r.feed(hdr(10, 0, 3, 3), F0)
        r.feed(hdr(10, 2, 3, 3), F2)
        self.assertEqual(r.pending_count, 1)

    def test_caso_F_nalu_posterior_completa_antes(self):
        r = Reassembler()
        r.feed(hdr(10, 0, 2, 3), F0)
        self.assertIsNone(r.feed(hdr(11, 0, 2, 3), F0))
        self.assertEqual(r.feed(hdr(11, 1, 2, 3), F1), F0 + F1)
        self.assertIsNone(r.feed(hdr(10, 1, 2, 3), F1))   # 10 aún incompleta (falta re-solicitud)
        self.assertEqual(r.pending_count, 1)

    def test_validacion_count_menor_igual_cero(self):
        r = Reassembler()
        self.assertIsNone(r.feed(hdr(1, 0, 0, 3), F0))
        self.assertEqual(r.pending_count, 0)

    def test_validacion_index_fuera_de_rango(self):
        r = Reassembler()
        self.assertIsNone(r.feed(hdr(1, 3, 2, 3), F0))
        self.assertEqual(r.pending_count, 0)

    def test_validacion_payload_size_incorrecto(self):
        r = Reassembler()
        self.assertIsNone(r.feed(hdr(1, 0, 1, 99), F0))   # declara 99 bytes, llegan 3
        self.assertEqual(r.pending_count, 0)

    def test_validacion_fragment_count_inconsistente(self):
        r = Reassembler()
        r.feed(hdr(10, 0, 2, 3), F0)
        self.assertIsNone(r.feed(hdr(10, 1, 3, 3), F1))   # mismo id pero count 3 != 2
        self.assertEqual(r.pending_count, 1)

if __name__ == "__main__":
    unittest.main()
```

> Nota sobre `test_caso_A_reconstruye_orden`: al llegar 0,1,2 en orden, el tercer `feed` ya devuelve la NALU y limpia `pending_nalus`; el `feed` extra solo sirve para no romper la secuencia del caso.

- [ ] **Step 2: Verificar que falla**

Run: `python -m unittest test.test_reassembler -v`
Expected: FAIL con `No module named 'packets.reassembler'`.

- [ ] **Step 3: Implementación mínima**

```python
from typing import Optional
from transport.video_header import VideoHeader

class Reassembler:
    def __init__(self):
        self.pending_nalus = {}

    @property
    def pending_count(self) -> int:
        return len(self.pending_nalus)

    def feed(self, header: VideoHeader, payload: bytes) -> Optional[bytes]:
        nalu_id = header.nalu_id
        index = header.fragment_index
        count = header.fragment_count

        if count <= 0:
            return None
        if not 0 <= index < count:
            return None
        if header.payload_size != len(payload):
            return None

        entry = self.pending_nalus.get(nalu_id)
        if entry is None:
            entry = {"fragment_count": count, "fragments": {}}
            self.pending_nalus[nalu_id] = entry
        elif entry["fragment_count"] != count:
            return None

        entry["fragments"][index] = payload

        if len(entry["fragments"]) == entry["fragment_count"]:
            final_nalu = b"".join(entry["fragments"][i] for i in range(entry["fragment_count"]))
            del self.pending_nalus[nalu_id]
            return final_nalu
        return None
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m unittest test.test_reassembler -v`
Expected: PASS.

- [ ] **Step 5: Refactorizar `reciever_nalu.py` (comportamiento idéntico)**

Eliminar el estado global y la función `extract_nalu_from_incoming_byte`; añadir:

```python
from packets.reassembler import Reassembler
...
reassembler = Reassembler()
```
y en el bucle principal reemplazar la llamada por:
```python
        final_nalu = reassembler.feed(header_recieved, incoming_video)
        if final_nalu is not None:
            video.append(final_nalu)
            if ffplay_process.stdin is not None:
                ffplay_process.stdin.write(b"\x00\x00\x00\x01" + final_nalu)
                ffplay_process.stdin.flush()
```

- [ ] **Step 6: Regresión + compilación**

Run: `python -m unittest discover -s test -v && python -m py_compile reciever_nalu.py packets/reassembler.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add packets/reassembler.py reciever_nalu.py test/test_reassembler.py
git commit -m "refactor: Reassembler compartido (casos A-F del handoff, validacion 8.8)"
```

---

### Task 3: Configuración radio (`radio/config_radio.py`)

**Files:**
- Create: `radio/__init__.py`, `radio/config_radio.py`
- Test: `test/test_radio_config.py`

**Interfaces:**
- Produces constantes: `ZMQ_TX_ENDPOINT = "tcp://127.0.0.1:5555"`, `ZMQ_RX_ENDPOINT = "tcp://127.0.0.1:5556"`, `ZMQ_TX_BIND = True`, `ZMQ_RX_BIND = False` (Python RX hace connect), `ZMQ_RX_CONNECT = True`, `ZMQ_RCVTIMEO_MS = 5000`.

- [ ] **Step 1: Test que falla**

```python
import unittest
from radio.config_radio import ZMQ_TX_ENDPOINT, ZMQ_RX_ENDPOINT, ZMQ_TX_BIND, ZMQ_RX_CONNECT

class TestRadioConfig(unittest.TestCase):
    def test_endpoints_por_especificacion(self):
        self.assertEqual(ZMQ_TX_ENDPOINT, "tcp://127.0.0.1:5555")
        self.assertEqual(ZMQ_RX_ENDPOINT, "tcp://127.0.0.1:5556")

    def test_roles_bind_connect(self):
        self.assertTrue(ZMQ_TX_BIND)      # Python TX hace bind (PUSH)
        self.assertTrue(ZMQ_RX_CONNECT)   # Python RX hace connect (PULL)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m unittest test.test_radio_config -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'radio'`.

- [ ] **Step 3: Implementación**

```python
ZMQ_TX_ENDPOINT = "tcp://127.0.0.1:5555"
ZMQ_RX_ENDPOINT = "tcp://127.0.0.1:5556"
ZMQ_TX_BIND = True
ZMQ_RX_CONNECT = True
ZMQ_RCVTIMEO_MS = 5000
```

- [ ] **Step 4: Verificar que pasa / Step 5: Commit**

Run: `python -m unittest test.test_radio_config -v` → PASS
```bash
git add radio/__init__.py radio/config_radio.py test/test_radio_config.py
git commit -m "feat: configuracion de endpoints ZMQ para radio (5555 TX / 5556 RX)"
```

---

### Task 4: Codec PMT GNU Radio (`radio/pmt_codec.py`)

**Files:**
- Create: `radio/pmt_codec.py`
- Test: `test/test_pmt_codec.py`

**Interfaces:**
- Consumes: formato `pmt::serialize_str` (ver `pmt_serialize.cc` / `pmt_serial_tags.h`).
- Produces: `encode_u8vector_pdu(payload: bytes) -> bytes`; `decode_pdu_data(frame: bytes) -> bytes` (extrae el u8vector final = datagrama); `class PmtDecodeError(ValueError)`.

Wire format TX del PDU `cons(dict_(), u8vector(payload))`:
`0x07` (PST_PAIR) + `0x06` (car = NIL, dict vacío) + blob = `0x0a 0x00` + `len:>I` + `0x01 0x00` + payload → **10 bytes de prefijo**.

- [ ] **Step 1: Test que falla**

```python
import unittest
from radio.pmt_codec import encode_u8vector_pdu, decode_pdu_data, PmtDecodeError

class TestPmtCodec(unittest.TestCase):
    def test_encode_vacio(self):
        self.assertEqual(encode_u8vector_pdu(b""),
                         b"\x07\x06\x0a\x00\x00\x00\x00\x00\x01\x00")

    def test_encode_1200_bytes(self):
        frame = encode_u8vector_pdu(b"Z" * 1200)
        self.assertEqual(frame[:10], b"\x07\x06\x0a\x00\x00\x00\x04\xb0\x01\x00")
        self.assertEqual(len(frame), 1210)

    def test_roundtrip(self):
        payload = b"\x00\x01\x02\x03" * 300
        self.assertEqual(decode_pdu_data(encode_u8vector_pdu(payload)), payload)

    def test_decode_con_metadatos(self):
        # cons(acons("x", 42, dict()), u8vector([1,2,3]))
        frame = bytes.fromhex("07090200017807030000002a060a00000000030" "100010203")
        self.assertEqual(decode_pdu_data(frame), b"\x01\x02\x03")

    def test_decode_truncado(self):
        with self.assertRaises(PmtDecodeError):
            decode_pdu_data(b"\x07\x06\x0a\x00\x00\x00\x00\x05\x01\x00")   # faltan 5 bytes

    def test_decode_tag_desconocido(self):
        with self.assertRaises(PmtDecodeError):
            decode_pdu_data(bytes([0x3b]))

    def test_decode_cdr_final_no_u8vector(self):
        frame = b"\x07\x06\x07\x03\x00\x00\x00\x2a\x06"      # (nil . (42 . nil)) sin blob
        with self.assertRaises(PmtDecodeError):
            decode_pdu_data(frame)

    def test_decode_sobras(self):
        with self.assertRaises(PmtDecodeError):
            decode_pdu_data(encode_u8vector_pdu(b"AB") + b"\x00")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verificar que falla** — `python -m unittest test.test_pmt_codec -v` → `No module named 'radio.pmt_codec'`.

- [ ] **Step 3: Implementación mínima**

```python
import struct

PST_TRUE, PST_FALSE, PST_SYMBOL, PST_INT32, PST_DOUBLE = 0x00, 0x01, 0x02, 0x03, 0x04
PST_COMPLEX, PST_NULL, PST_PAIR, PST_VECTOR, PST_DICT = 0x05, 0x06, 0x07, 0x08, 0x09
PST_UNIFORM_VECTOR, PST_UINT64, PST_TUPLE, PST_INT64 = 0x0A, 0x0B, 0x0C, 0x0D
UVI_U8 = 0x00

class PmtDecodeError(ValueError):
    pass

def encode_u8vector_pdu(payload: bytes) -> bytes:
    blob = b"\x0a\x00" + struct.pack(">I", len(payload)) + b"\x01\x00" + payload
    return b"\x07\x06" + blob

def _read_exact(data, pos, n):
    end = pos + n
    if end > len(data):
        raise PmtDecodeError(f"PMT truncado en pos {pos}, faltan {n} bytes")
    return data[pos:end], pos

def _parse(data, pos=0):
    tag, pos = _read_exact(data, pos, 1)
    t = tag[0]
    if t == PST_NULL:
        return None, pos
    if t in (PST_TRUE, PST_FALSE):
        return t == PST_TRUE, pos
    if t == PST_SYMBOL:
        raw, pos = _read_exact(data, pos, 2)
        (length,) = struct.unpack(">H", raw)
        s, pos = _read_exact(data, pos, length)
        return s.decode("utf-8"), pos
    if t == PST_INT32:
        raw, pos = _read_exact(data, pos, 4)
        return struct.unpack(">i", raw)[0], pos
    if t in (PST_INT64, PST_UINT64):
        raw, pos = _read_exact(data, pos, 8)
        return struct.unpack(">q" if t == PST_INT64 else ">Q", raw)[0], pos
    if t == PST_DOUBLE:
        raw, pos = _read_exact(data, pos, 8)
        return struct.unpack(">d", raw)[0], pos
    if t in (PST_PAIR, PST_DICT):
        car, pos = _parse(data, pos)
        cdr, pos = _parse(data, pos)
        return (car, cdr), pos
    if t == PST_UNIFORM_VECTOR:
        sub, pos = _read_exact(data, pos, 1)
        if sub[0] != UVI_U8:
            raise PmtDecodeError("solo se soporta u8vector")
        raw, pos = _read_exact(data, pos, 4)
        (length,) = struct.unpack(">I", raw)
        npad_raw, pos = _read_exact(data, pos, 1)
        _pad, pos = _read_exact(data, pos, npad_raw[0])
        blob, pos = _read_exact(data, pos, length)
        return blob, pos
    if t in (PST_TUPLE, PST_VECTOR):
        raw, pos = _read_exact(data, pos, 4)
        (length,) = struct.unpack(">I", raw)
        items = []
        for _ in range(length):
            item, pos = _parse(data, pos)
            items.append(item)
        return items, pos
    raise PmtDecodeError(f"tag PMT desconocido 0x{t:02x}")

def decode_pdu_data(frame: bytes) -> bytes:
    value, pos = _parse(frame)
    if pos != len(frame):
        raise PmtDecodeError("datos extra después del mensaje PMT")
    node = value
    while isinstance(node, tuple) and len(node) == 2:
        node = node[1]
    if not isinstance(node, bytes):
        raise PmtDecodeError("el cdr final del PDU no es un u8vector")
    return node
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m unittest test.test_pmt_codec -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add radio/pmt_codec.py test/test_pmt_codec.py
git commit -m "feat: codec PMT GNU Radio bit-compatible para PDU sobre ZMQ"
```

---

### Task 5: Transport TX (`radio/zmq_pdu_transport.py`) + `requirements-radio.txt`

**Files:**
- Create: `radio/zmq_pdu_transport.py`, `requirements-radio.txt`
- Test: `test/test_zmq_pdu_transport.py`

**Interfaces:**
- Consumes: `Transport` (ABC), `build_datagram`, `encode_u8vector_pdu`, `radio.config_radio` (`ZMQ_TX_ENDPOINT`, `ZMQ_TX_BIND`), `pyzmq`.
- Produces: `class ZMQPduTransport(Transport)` con `__init__(self, endpoint=None, context=None, socket=None, bind=None)`, `send_packet(packet: NALUPacket) -> int` (devuelve `len(datagram)`), `close() -> None`. `socket` inyectable para tests.

- [ ] **Step 1: Test que falla**

```python
import unittest
from unittest import mock
from packets.packetizer import NALUPacket
from packets.priority_classifier import Priority
from radio.pmt_codec import encode_u8vector_pdu
from transport.datagram import build_datagram
from radio import zmq_pdu_transport

class FakeSocket:
    def __init__(self):
        self.sent = []
        self.closed = False
    def send(self, frame):
        self.sent.append(frame)
        return len(frame)
    def close(self, linger=0):
        self.closed = True

class FakeContext:
    def __init__(self):
        self.sockets = []
    def socket(self, stype):
        s = FakeSocket()
        s.stype = stype
        self.sockets.append(s)
        return s

FAKE_ZMQ = mock.MagicMock()
FAKE_ZMQ.PUSH = 8

class TestZMQPduTransport(unittest.TestCase):
    def test_envia_frame_pdu_con_tam_correcto(self):
        fake = FakeSocket()
        t = ZMQPduTransport(socket=fake, context=FakeContext())
        packet = NALUPacket(1, nalu_id=1, fragment_index=0, fragment_count=1,
                            nal_type=5, priority=Priority.HIGH, timestamp_ns=0,
                            payload=b"\x01\x02\x03")
        sent = t.send_packet(packet)
        self.assertEqual(sent, 27)                                  # 24 header + 3 payload
        self.assertEqual(fake.sent[0], encode_u8vector_pdu(build_datagram(packet)))

    def test_datagrama_demasiado_grande_levanta(self):
        fake = FakeSocket()
        t = ZMQPduTransport(socket=fake, context=FakeContext())
        packet = NALUPacket(1, 1, 0, 1, 5, Priority.HIGH, 0, b"x" * 1177)
        with self.assertRaises(ValueError):
            t.send_packet(packet)
        self.assertEqual(fake.sent, [])

    def test_close_cierra_socket(self):
        fake = FakeSocket()
        t = ZMQPduTransport(socket=fake, context=FakeContext())
        t.close()
        self.assertTrue(fake.closed)

    def test_fabrica_socket_push_bind_sin_inyeccion(self):
        with mock.patch.object(zmq_pdu_transport, "zmq", FAKE_ZMQ), \
             mock.patch.object(zmq_pdu_transport, "ZMQ_TX_ENDPOINT", "tcp://127.0.0.1:5555"):
            ctx = FakeContext()
            FAKE_ZMQ.Context.return_value = ctx
            t = ZMQPduTransport()
            self.assertEqual(t._socket.stype, 8)                    # PUSH
            self.assertTrue(t._socket is not None)

if __name__ == "__main__":
    unittest.main()
```

> Ajuste: en `test_fabrica_socket_push_bind_sin_inyeccion` se verifica que el socket creado es PUSH y que `bind` se invocó con el endpoint correcto.

- [ ] **Step 2: Verificar que falla**

Run: `python -m unittest test.test_zmq_pdu_transport -v`
Expected: FAIL con `No module named 'radio.zmq_pdu_transport'`.

- [ ] **Step 3: Implementación mínima**

```python
import zmq
from transport.transport import Transport
from transport.datagram import build_datagram
from radio.pmt_codec import encode_u8vector_pdu
from radio.config_radio import ZMQ_TX_ENDPOINT, ZMQ_TX_BIND
from packets.packetizer import NALUPacket

class ZMQPduTransport(Transport):
    def __init__(self, endpoint=None, context=None, socket=None, bind=None):
        self._owns_socket = socket is None
        self._owns_context = context is None
        self._context = context if context is not None else zmq.Context()
        self._socket = socket
        self.endpoint = endpoint if endpoint is not None else ZMQ_TX_ENDPOINT
        if self._socket is None:
            self._socket = self._context.socket(zmq.PUSH)
            if bind if bind is not None else ZMQ_TX_BIND:
                self._socket.bind(self.endpoint)
            else:
                self._socket.connect(self.endpoint)

    def send_packet(self, packet: NALUPacket) -> int:
        datagram = build_datagram(packet)
        frame = encode_u8vector_pdu(datagram)
        self._socket.send(frame)
        return len(datagram)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close(0)
            self._socket = None
        if self._owns_context and self._context is not None:
            self._context.term()
            self._context = None
```
`requirements-radio.txt`:
```
pyzmq>=25.0
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m unittest test.test_zmq_pdu_transport -v`
Expected: PASS. `python -m py_compile radio/zmq_pdu_transport.py`

- [ ] **Step 5: Commit**

```bash
git add radio/zmq_pdu_transport.py requirements-radio.txt test/test_zmq_pdu_transport.py
git commit -m "feat: ZMQPduTransport (TX) cumple la interfaz Transport sobre ZMQ PDU"
```

---

### Task 6: Receptor RX (`radio/zmq_pdu_receiver.py`)

**Files:**
- Create: `radio/zmq_pdu_receiver.py`
- Test: `test/test_zmq_pdu_receiver.py`

**Interfaces:**
- Consumes: `decode_pdu_data`, `parse_datagram`, `Reassembler`, `radio.config_radio` (`ZMQ_RX_ENDPOINT`, `ZMQ_RX_CONNECT`, `ZMQ_RCVTIMEO_MS`), `pyzmq`.
- Produces: `class ZMQPduReceiver` (`__init__(self, endpoint=None, context=None, socket=None, connect=None, rcvtimeo_ms=None)`, `recv_timeout() -> Optional[bytes]`, `close()`); `run_recv_loop(rx, reassembler, on_nalu, on_timeout) -> None`; `main()`.

- [ ] **Step 1: Test que falla**

```python
import unittest
from unittest import mock
from packets.reassembler import Reassembler
from packets.priority_classifier import Priority
from radio.pmt_codec import encode_u8vector_pdu
from transport.datagram import build_datagram
from packets.packetizer import NALUPacket
from radio import zmq_pdu_receiver

class FakePuller:
    def __init__(self, frames):
        self.frames = list(frames)
        self.closed = False
    def recv(self):
        if self.frames:
            return self.frames.pop(0)
        raise zmq_pdu_receiver.TIMEOUT_EXCEPTION()
    def close(self, linger=0):
        self.closed = True

def datagram(payload, index=0, count=1, nalu_id=10, seq=1):
    return build_datagram(NALUPacket(packet_sequence=seq, nalu_id=nalu_id,
                                     fragment_index=index, fragment_count=count,
                                     nal_type=1, priority=Priority.NORMAL,
                                     timestamp_ns=0, payload=payload))

class TestZMQPduReceiver(unittest.TestCase):
    def test_recv_timeout_devuelve_datagrama(self):
        rx = ZMQPduReceiver(socket=FakePuller([encode_u8vector_pdu(datagram(b"abc"))]), context=mock.MagicMock())
        self.assertEqual(rx.recv_timeout(), datagram(b"abc"))

    def test_recv_timeout_timeout_devuelve_none(self):
        rx = ZMQPduReceiver(socket=FakePuller([]), context=mock.MagicMock())
        self.assertIsNone(rx.recv_timeout())

    def test_run_recv_loop_reensambla(self):
        frames = [encode_u8vector_pdu(datagram(b"AAA", index=0, count=2)),
                  encode_u8vector_pdu(datagram(b"BBB", index=1, count=2))]
        rx = ZMQPduReceiver(socket=FakePuller(frames), context=mock.MagicMock())
        out = []
        def on_nalu(n):
            out.append(n)
        def on_timeout():
            return True
        run_recv_loop(rx, Reassembler(), on_nalu, on_timeout)
        self.assertEqual(out, [b"AAABBB"])

    def test_close(self):
        fake = FakePuller([])
        rx = ZMQPduReceiver(socket=fake, context=mock.MagicMock())
        rx.close()
        self.assertTrue(fake.closed)

if __name__ == "__main__":
    unittest.main()
```

> En `recv_timeout()` se captura `zmq.Again`; para no depender de `pyzmq` en el test, expón `TIMEOUT_EXCEPTION = zmq.Again` en el módulo. Alternativa: el test usa `zmq.Again` real si `pyzmq` está instalado; para que los unit tests nunca dependan de él, se usa `TIMEOUT_EXCEPTION`.

- [ ] **Step 2: Verificar que falla**

Run: `python -m unittest test.test_zmq_pdu_receiver -v`
Expected: FAIL.

- [ ] **Step 3: Implementación mínima**

```python
import subprocess
import zmq
from typing import Callable, Optional
from packets.reassembler import Reassembler
from transport.datagram import parse_datagram
from radio.pmt_codec import decode_pdu_data
from radio.config_radio import ZMQ_RX_ENDPOINT, ZMQ_RX_CONNECT, ZMQ_RCVTIMEO_MS

TIMEOUT_EXCEPTION = zmq.Again

class ZMQPduReceiver:
    def __init__(self, endpoint=None, context=None, socket=None, connect=None, rcvtimeo_ms=None):
        self._owns_socket = socket is None
        self._owns_context = context is None
        self._context = context if context is not None else zmq.Context()
        self._socket = socket
        self.endpoint = endpoint if endpoint is not None else ZMQ_RX_ENDPOINT
        if self._socket is None:
            self._socket = self._context.socket(zmq.PULL)
            if connect if connect is not None else ZMQ_RX_CONNECT:
                self._socket.connect(self.endpoint)
            else:
                self._socket.bind(self.endpoint)
            self._socket.setsockopt(zmq.RCVTIMEO, rcvtimeo_ms if rcvtimeo_ms is not None else ZMQ_RCVTIMEO_MS)

    def recv_timeout(self) -> Optional[bytes]:
        try:
            frame = self._socket.recv()
        except TIMEOUT_EXCEPTION:
            return None
        return decode_pdu_data(frame)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close(0)
            self._socket = None
        if self._owns_context and self._context is not None:
            self._context.term()
            self._context = None

def run_recv_loop(rx, reassembler, on_nalu: Callable[[bytes], None], on_timeout: Callable[[], bool]) -> None:
    while True:
        datagram = rx.recv_timeout()
        if datagram is None:
            if on_timeout():
                return
            continue
        header, payload = parse_datagram(datagram)
        final_nalu = reassembler.feed(header, payload)
        if final_nalu is not None:
            on_nalu(final_nalu)

def main() -> None:
    cmd = [
        "ffplay", "-fflags", "nobuffer", "-flags", "low_delay",
        "-framedrop", "-f", "h264", "-",
    ]
    video = []
    ffplay_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def on_nalu(nalu_bytes: bytes) -> None:
        video.append(nalu_bytes)
        if ffplay_process.stdin is not None:
            ffplay_process.stdin.write(b"\x00\x00\x00\x01" + nalu_bytes)
            ffplay_process.stdin.flush()

    def on_timeout() -> bool:
        print("Tiempo de espera agotado, fin de recepción")
        if ffplay_process.stdin is not None:
            ffplay_process.stdin.close()
        ffplay_process.terminate()
        with open("reconstructed_rf", "wb") as f:
            for nalu in video:
                f.write(b"\x00\x00\x00\x01" + nalu)
        return True

    rx = ZMQPduReceiver()
    try:
        run_recv_loop(rx, Reassembler(), on_nalu, on_timeout)
    finally:
        rx.close()
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m unittest test.test_zmq_pdu_receiver -v && python -m py_compile radio/zmq_pdu_receiver.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add radio/zmq_pdu_receiver.py test/test_zmq_pdu_receiver.py
git commit -m "feat: ZMQPduReceiver y run_recv_loop (RX sobre ZMQ PDU)"
```

---

### Task 7: Fábrica de transporte (`transport/transport_factory.py`) + `config.py` + `capture.py`

**Files:**
- Modify: `transport/transport_factory.py` (create), `config.py:11-12`, `capture.py:5,20`
- Test: `test/test_transport_factory.py`

**Interfaces:**
- Consumes: `config.TRANSPORT`, `UdpTransport`, `ZMQPduTransport`.
- Produces: `get_transport() -> Transport`; nueva constante `config.TRANSPORT` (`"udp"` | `"radio"`).

- [ ] **Step 1: Test que falla**

```python
import unittest
from unittest import mock
from transport.udp_transport import UdpTransport
from transport.transport_factory import get_transport

class TestTransportFactory(unittest.TestCase):
    def test_udp_por_defecto(self):
        with mock.patch("config.TRANSPORT", "udp"):
            self.assertIsInstance(get_transport(), UdpTransport)

    def test_radio_devuelve_zmq(self):
        fake_zmq = mock.MagicMock()
        fake_zmq.PUSH = 8
        with mock.patch("radio.zmq_pdu_transport.zmq", fake_zmq), \
             mock.patch("config.TRANSPORT", "radio"):
            from radio.zmq_pdu_transport import ZMQPduTransport
            self.assertIsInstance(get_transport(), ZMQPduTransport)

    def test_radio_sin_pyzmq_levanta_error_claro(self):
        import transport.transport_factory as tf
        real_import = __import__
        def broken_import(name, *a, **k):
            if name == "radio.zmq_pdu_transport":
                raise ImportError("No module named 'zmq'")
            return real_import(name, *a, **k)
        with mock.patch("builtins.__import__", side_effect=broken_import), \
             mock.patch("config.TRANSPORT", "radio"):
            with self.assertRaises(RuntimeError):
                get_transport()

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m unittest test.test_transport_factory -v`
Expected: FAIL con `No module named 'transport.transport_factory'`.

- [ ] **Step 3: Implementación**

`config.py` — añadir tras `SERVER_PORT`:
```python
TRANSPORT = "udp"   # "udp" para el baseline UDP; "radio" para GNU Radio vía ZMQ (requiere requirements-radio.txt)
```

`transport/transport_factory.py`:
```python
from transport.udp_transport import UdpTransport

def get_transport():
    from config import TRANSPORT
    if TRANSPORT == "radio":
        try:
            from radio.zmq_pdu_transport import ZMQPduTransport
        except ImportError as exc:
            raise RuntimeError(
                "pyzmq no está instalado: ejecuta 'pip install -r requirements-radio.txt'"
            ) from exc
        return ZMQPduTransport()
    return UdpTransport()
```

`capture.py`:
- Reemplazar `from transport.udp_transport import UdpTransport` por `from transport.transport_factory import get_transport`.
- Reemplazar `transport = UdpTransport()` por `transport = get_transport()`.

- [ ] **Step 4: Verificar que pasa + regresión**

Run: `python -m unittest discover -s test -v && python -m py_compile capture.py transport/transport_factory.py`
Expected: PASS (incluye `test_scheduler.py` si se ejecuta como script: `python test/test_scheduler.py`, sin cambios).

- [ ] **Step 5: Commit**

```bash
git add transport/transport_factory.py config.py capture.py test/test_transport_factory.py
git commit -m "feat: factory de transporte con switch UDP/radio (config.TRANSPORT)"
```

---

### Task 8: Script ejecutable del receptor radio (`radio/reciever_radio.py`)

**Files:**
- Create: `radio/reciever_radio.py`
- Test: `test/test_reciever_radio.py` (solo compilación + import)

**Interfaces:**
- Consumes: `ZMQPduReceiver.main`.
- Produces: `radio/reciever_radio.py` (entry point de 3 líneas + guard `__main__`).

- [ ] **Step 1: Test que falla**

```python
import unittest
import subprocess
import sys

class TestRecieverRadioSmoke(unittest.TestCase):
    def test_modulo_importa_y_compila(self):
        result = subprocess.run([sys.executable, "-m", "py_compile", "radio/reciever_radio.py"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        import radio.reciever_radio  # noqa: F401

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verificar que falla** — `python -m unittest test.test_reciever_radio -v` → FAIL (módulo inexistente).

- [ ] **Step 3: Implementación**

```python
from radio.zmq_pdu_receiver import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m unittest test.test_reciever_radio -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add radio/reciever_radio.py test/test_reciever_radio.py
git commit -m "feat: entry point del receptor radio (radio/reciever_radio.py)"
```

---

### Task 9: Flowgraphs de referencia (`radio/flowgraphs/`) — sin hardware en tests

**Files:**
- Create: `radio/flowgraphs/tx_bladerf.grc`, `radio/flowgraphs/rx_hackrf.grc`, `radio/flowgraphs/README_FLOWGRAPHS.md`
- Test: `test/test_flowgraphs.py`

**Interfaces:**
- Consumes: GNU Radio 3.10/3.11, `ZMQ PULL Message Source`/`ZMQ PUSH Message Sink` (gr-zeromq), `PDU to Tagged Stream`/`Tagged Stream to PDU` (gr-blocks), gr-bladeRF (TX), gr-osmosdr (RX HackRF).
- Produces: artefactos de referencia validables manualmente con hardware; **no** forman parte de la suite unitaria salvo bien-formación XML.

- [ ] **Step 1: Test de bien-formación XML que falla (sin dependencias de GNU Radio)**

```python
import unittest
import glob
from xml.dom import minidom

class TestFlowgraphsWellFormed(unittest.TestCase):
    def test_grc_son_xml_valido(self):
        files = glob.glob("radio/flowgraphs/*.grc")
        self.assertGreater(len(files), 0)
        for f in files:
            minidom.parse(f)   # lanza si no es XML bien formado

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verificar que falla** — `python -m unittest test.test_flowgraphs -v` → FAIL (no hay .grc aún).

- [ ] **Step 3: Crear `tx_bladerf.grc` (referencia)**

Gráfico TX (BladeRF, ~2.45 GHz, 20 Msps):
```
ZMQ PULL Message Source (Address: tcp://127.0.0.1:5555, Timeout: 100, mod: connect)
   │ (msg port)
   ▼
PDU to Tagged Stream (blks2.pdu_to_tagged_stream, Type: Byte, Len Tag Key: packet_len)
   ▼
digital.gmsk_mod (samples/symbol=8, gain=1.0)      # modulación simple de referencia
   ▼
bladeRF sink (gr-bladeRF; sample_rate=20e6, center_freq=2.45e9, gain=40)
```
Crea el archivo `.grc` en GNU Radio Companion siguiendo ese grafo (block ids: `zeromq_pull_msg_source`, `blks2_pdu_to_tagged_stream`, `digital_gmsk_mod_0`, `${bladeRF}`). Guardar en `radio/flowgraphs/tx_bladerf.grc`. El executor debe colocar el XML exportado por GRC; parámetros clave exactos: `address: tcp://127.0.0.1:5555`, `timeout: 100`, `mode: connect`.

- [ ] **Step 4: Crear `rx_hackrf.grc` (referencia)**

Gráfico RX (HackRF por USB vía gr-osmosdr, 2.45 GHz, 20 Msps):
```
osmosdr source (type: complex, sample_rate=20e6, freq=2.45e9, hackrf)
   ▼
digital.gmsk_demod (samples/symbol=8, gain=1.0)
   ▼
Tagged Stream to PDU (blocks.tagged_stream_to_pdu, Type: Byte, Len Tag Key: packet_len)
   ▼ (msg port)
ZMQ PUSH Message Sink (zeromq_push_msg_sink, Address: tcp://127.0.0.1:5556, Timeout: 100, mod: bind)
```
Parámetros clave: `address: tcp://127.0.0.1:5556`, `timeout: 100`, `mode: bind` (= modo PUSH Sink que hace bind). Guardar en `radio/flowgraphs/rx_hackrf.grc`.

- [ ] **Step 5: Crear `radio/flowgraphs/README_FLOWGRAPHS.md`**

Contenido mínimo (checklist de verificación en hardware — sin automatizar):
- Estructura del grafo TX/RX, endpoints (`5555` TX conectado por el flowgraph, `5556` RX bind por el flowgraph).
- Prerrequisitos de sistema: `gr-bladeRF`, `gr-osmosdr`, GNU Radio 3.10+, `pyzmq`.
- Orden de arranque sugerido: 1) `python radio/reciever_radio.py`; 2) iniciar flowgraph RX (bind en 5556); 3) iniciar flowgraph TX (connect a 5555); 4) `python capture.py` con `TRANSPORT="radio"`.
- Compatibility del wire: el flowgraph recibe/emite `pmt::serialize_str(cons(dict, u8vector))`.

- [ ] **Step 6: Verificar que pasa**

Run: `python -m unittest test.test_flowgraphs -v`
Expected: PASS (XML bien formado).

- [ ] **Step 7: Commit**

```bash
git add radio/flowgraphs/ test/test_flowgraphs.py
git commit -m "docs: flowgraphs de referencia BladeRF TX / HackRF RX sobre ZMQ PDU"
```

---

### Task 10: Documentación (`README.md`) e integración opcional ZMQ real

**Files:**
- Modify: `README.md` (nueva sección), `test/test_zmq_loopback_integration.py` (opcional)

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: sección "Modo radio (GNU Radio + SDR)" en README y test de integración real loopback `skipUnless(pyzmq)`.

- [ ] **Step 1: Test de integración real ZMQ (opcional, se salta si falta pyzmq)**

```python
import unittest

try:
    import zmq
    HAVE_ZMQ = True
except ImportError:
    HAVE_ZMQ = False

from packets.packetizer import NALUPacket
from packets.priority_classifier import Priority
from packets.reassembler import Reassembler
from radio.pmt_codec import encode_u8vector_pdu, decode_pdu_data
from transport.datagram import build_datagram, parse_datagram
from radio.zmq_pdu_transport import ZMQPduTransport
from radio.zmq_pdu_receiver import ZMQPduReceiver

@unittest.skipUnless(HAVE_ZMQ, "pyzmq no instalado")
class TestZmolLoopback(unittest.TestCase):
    def test_tx_rx_loopback_inproc(self):
        context = zmq.Context()
        rx = ZMQPduReceiver(endpoint="inproc://radiotest", context=context,
                            socket=context.socket(zmq.PULL), connect=True, rcvtimeo_ms=1000)
        rx._socket.connect("inproc://radiotest")

        context_tx = zmq.Context()
        tx = ZMQPduTransport(endpoint="inproc://radiotest", context=context_tx,
                             socket=context_tx.socket(zmq.PUSH), bind=True)

        packet = NALUPacket(1, 7, 0, 2, 1, Priority.NORMAL, 0, b"XYZ")
        self.assertEqual(tx.send_packet(packet), 27)
        datagram = rx.recv_timeout()
        self.assertIsNotNone(datagram)
        header, payload = parse_datagram(datagram)
        self.assertEqual(header.nalu_id, 7)
        self.assertEqual(payload, b"XYZ")
        tx.close(); rx.close(); context.term(); context_tx.term()

    def test_loopback_reensamblado(self):
        context = zmq.Context()
        rx = ZMQPduReceiver(endpoint="inproc://radiotest2", context=context,
                            socket=context.socket(zmq.PULL), connect=True, rcvtimeo_ms=1000)
        rx._socket.connect("inproc://radiotest2")
        context_tx = zmq.Context()
        tx = ZMQPduTransport(endpoint="inproc://radiotest2", context=context_tx,
                             socket=context_tx.socket(zmq.PUSH), bind=True)
        for i, pl in enumerate([b"AA", b"BB"]):
            tx.send_packet(NALUPacket(1 + i, 5, i, 2, 1, Priority.NORMAL, 0, pl))
        r = Reassembler(); out = []
        for _ in range(2):
            d = rx.recv_timeout()
            h, p = parse_datagram(d)
            n = r.feed(h, p)
            if n is not None:
                out.append(n)
        self.assertEqual(out, [b"AABB"])
        tx.close(); rx.close(); context.term(); context_tx.term()

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verificar que falla** — `python -m unittest test.test_zmq_loopback_integration -v`
  - Sin pyzmq: SKIPPED (0 failures).
  - Con pyzmq: el primer test puede fallar (aún sin corregir `recv_timeout`/roles) → ajustar «step 3».

- [ ] **Step 3: Ajustar implementación si falla**

En `test_zmq_pdu_receiver.py` no se usan sockets reales; `recv_timeout` ya captura `TIMEOUT_EXCEPTION`. Si `inproc` presentara reintentos por orden bind/connect, conectar el `PULL` antes del bind del `PUSH` (ZMQ inproc requiere que el conector ya exista cuando el bind ocurre). Ajustar el orden en el test en caso de `AssertionError`.

- [ ] **Step 4: Documentar README**

Añadir sección corta en `README.md` tras §6:

```markdown
## Modo radio (GNU Radio + SDR)

Alterna transporte con `TRANSPORT = "radio"` en `config.py` (por defecto `"udp"`):

pip install -r requirements-radio.txt   # solo pyzmq

- TX: `python capture.py` → `ZMQPduTransport` publica el datagrama de 24 B + payload
  (≤ 1200 B) como PDU vía `pmt.serialize_str` en `tcp://127.0.0.1:5555`
  (PUSH bind; el flowgraph `tx_bladerf.grc` conecta con `ZMQ PULL Message Source`).
- RX: flowgraph `rx_hackrf.grc` (HackRF) publica en `tcp://127.0.0.1:5556`
  (`ZMQ PUSH Message Sink`, bind); `python radio/reciever_radio.py` conecta (PULL),
  decodifica el PDU y reensambla con el mismo `Reassembler` del receptor UDP.
```

- [ ] **Step 5: Verificar + commit**

Run: `python -m unittest discover -s test -v`
Expected: PASS (con el loopback en SKIP si no hay pyzmq).
```bash
git add README.md test/test_zmq_loopback_integration.py
git commit -m "docs: seccion modo radio en README y test de integracion loopback ZMQ"
```

---

## Self-review

**Cobertura de especificación:**
- Regla 1 (baseline intacto + módulo separado ETC/DRY): tasks 1,2,7 refactorizan solo delegando; `radio/` nuevo y aislado. ✔
- Regla 2 (ABC `Transport`): Task 5 `ZMQPduTransport` la implementa y cumple test. ✔
- Regla 3 (header 24 B + ≤1200 B): Task 1 (byte-exact) + Task 5 (overflow ValueError). ✔
- Regla 4 (ZMQ PDU 5555/5556): Tasks 3–6 + wire format bit-compatible Task 4. ✔
- Mocks sin hardware: todos los tests son `unittest` + `mock`; el único test real (loopback) es `skipUnless(pyzmq)` y usa `inproc://`. ✔
- Handoff §10 casos A–F: Task 2. §8.8 validación: Task 2. ✔
- Flowgraphs BladeRF/HackRF (objetivo del proyecto): Task 9 (referencia, verificación manual). ✔

**Placeholder scan:** todo step de código incluye contenido concreto; ningún "TBD". En Task 9 los `.grc` se generan con GRC siguiendo un grafo/parámetros exactos listados; se documenta el límite (no automatizable). ✔

**Consistencia de tipos/nombres:** `build_datagram`/`parse_datagram` (Task 1) usados en 5,6,10; `encode_u8vector_pdu`/`decode_pdu_data` (4) usados en 5,6,10; `Reassembler.feed` (2) usado en 6,10; `ZMQPduTransport`/`ZMQPduReceiver`/`run_recv_loop`/`get_transport`/`TRANSPORT` consistentes. Topología PUSH/PULL con bind en TX-Python y connect en RX-Python es consistente en config (Task 3), transports (5,6) y flowgraphs (9). ✔

---

**User decision (anterior): ejecución Subagent-Driven** — despachar un subagente por task con revisión entre tareas. Tareas a ejecutar: 1 a 7.