# Flowgraphs de referencia (GNU Radio Companion)

Artefactos de referencia para validación manual con hardware. No son parte de la
suite de tests unitarios (solo se verifica que el XML esté bien formado). Requieren
GNU Radio 3.10+ y estaciones con SDR real.

## Estructura del grafo

### TX — `tx_bladerf.grc` (BladeRF)

```
ZMQ PULL Message Source   (tcp://127.0.0.1:5555, timeout=100, mode=connect)
   │ (msg port: out → in)
   ▼
PDU to Tagged Stream      (blks2.pdu_to_tagged_stream, Type: byte, Len Tag Key: packet_len)
   ▼
GMSK Mod                  (digital.gmsk_mod, samples/symbol=8, gain=1.0)
   ▼
BladeRF sink              (gr-bladeRF; sample_rate=20e6, center_freq=2.45e9, gain=40)
```

### RX — `rx_hackrf.grc` (HackRF por USB vía gr-osmosdr)

```
osmosdr source            (type: complex, sample_rate=20e6, freq=2.45e9, args=hackrf)
   ▼
GMSK Demod                (digital.gmsk_demod, samples/symbol=8, gain=1.0)
   ▼
Tagged Stream to PDU      (blocks.tagged_stream_to_pdu, Type: byte, Len Tag Key: packet_len)
   ▼ (msg port: out → in)
ZMQ PUSH Message Sink     (tcp://127.0.0.1:5556, timeout=100, mode=bind)
```

## Endpoints

- **`5555`** — TX: lo **conecta el flowgraph** (`ZMQ PULL Message Source`, mode=connect).
  El peer (receptor Python, `radio/reciever_radio.py`) es quien hace **bind** en 5555.
- **`5556`** — RX: lo **bind** el flowgraph (`ZMQ PUSH Message Sink`, mode=bind).
  El peer (receptor Python) **se conecta** a 5556.

## Prerrequisitos de sistema

- GNU Radio 3.10+ (`import gnuradio` desde Python).
- **gr-bladeRF** (TX) — `pip install gr-bladeRF` o build desde fuente.
- **gr-osmosdr** (RX) — paquete del sistema (p. ej. `gr-osmosdr` en Fedora/Ubuntu).
- **gr-zeromq** y **pyzmq** — incluidos en GNU Radio estándar; `pip install pyzmq`.
- `python requirements-radio.txt` instalado (receptor Python, transport ZMQ PDU).

> Nota: si `gnuradio-companion`/`grcc` no está instalado, los `.grc` se pueden
> validar igualmente como XML o abrir/regenerar en una máquina con GRC.

## Orden de arranque sugerido

1. `python radio/reciever_radio.py` — receptor Python (hace bind en 5555, se conecta a 5556).
2. Iniciar el flowgraph **RX** (`rx_hackrf.grc`) — bind en 5556.
3. Iniciar el flowgraph **TX** (`tx_bladerf.grc`) — connect a 5555.
4. `python capture.py` con `TRANSPORT="radio"` (en `config.py`).

## Compatibilidad del wire

Los flowgraphs reciben/emiten PDUs en el formato serializado de GNU Radio:

```
pmt::serialize_str(cons(dict, u8vector))
```

(PDU estándar de GNU Radio: un par cuya CDR es un `u8vector`). El receptor Python
(`radio/pmt_codec.py`, `radio/zmq_pdu_receiver.py`) decodifica exactamente ese
wire espejo: `encode_u8vector_pdu()` produce `cons(dict, u8vector)` y el flujo de
TX del transport emite lo mismo sobre 5555.

## Checklist de verificación en hardware (sin automatizar)

- [ ] GNU Radio 3.10+, gr-bladeRF, gr-osmosdr y pyzmq instalados.
- [ ] Receptor Python arrancado: `python radio/reciever_radio.py`.
- [ ] RX flowgraph arrancado y **bind** en `5556` (sin error).
- [ ] TX flowgraph arrancado y **connect** a `5555` (sin error).
- [ ] `capture.py` con `TRANSPORT="radio"`; el TX PULL recibe PDUs (`cons(dict, u8vector)`).
- [ ] El RX PUSH emite PDUs que decodifica `radio/pmt_codec.py` (bytes H.264 del receptor).
- [ ] Link de RF 2.45 GHz / 20 Msps: sin pérdida de de-sincronización GMSK,
      `packet_len` consistente entre TX y RX.