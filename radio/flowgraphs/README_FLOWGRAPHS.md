# Flowgraphs de referencia (GNU Radio Companion)

Artefactos de referencia para validación manual con hardware. No son parte de la
suite de tests unitarios (solo se verifica que el XML esté bien formado y que el
grafo tenga la cadena access-code + header esperada). Requieren GNU Radio 3.10+,
gr-bladeRF y dos estaciones con BladeRF real.

## Enlace blade-to-blade (una frecuencia fija)

El objetivo es transmitir el video H.264 por RF **entre dos BladeRF** en una misma
frecuencia fija (**2.45 GHz**), con modulación GMSK a **20 Msps** (8 muestras/símbolo)
y un patrón de ráfaga **access code + header** para que el receptor detecte el inicio
de paquete y la longitud (los paquetes no se alinean por sí solos tras el demod).

```
Emisor (estación A)                                Receptor (estación B)
────────────────────                               ─────────────────────
capture.py (H.264)                                 reciever_radio.py (ffplay)
    │ ZMQ PUSH (bind 5555)                             ▲ ZMQ PULL (connect 5556)
    ▼                                                    │
tx_bladerf.grc                                          rx_bladerf.grc
ZMQ PULL ← 5555                                 bladerf_source (RX)
  → PDU to Tagged Stream (packet_len)            → GMSK Demod (8 sps)
  → formatter → header (access code + 16-bit)    → Correlate Access Code (tag stream)
  → Tagged Stream Mux (header + payload)         → Repack Bits 1→8 (packet_len)
  → GMSK Mod (8 sps)                             → Tagged Stream to PDU
  → BladeRF sink (TX)                            → ZMQ PUSH → 5556
```

## Estructura del grafo

### TX — `tx_bladerf.grc` (BladeRF)

```
ZMQ PULL Message Source    (tcp://127.0.0.1:5555, timeout=100, mode=connect)
   │ (msg port: out → in)
   ▼
PDU to Tagged Stream       (pdu_to_tagged_stream, Type: byte, Len Tag Key: packet_len)
   │
   ├──► Protocol Formatter (digital.protocol_formatter_bb, format=hdr_format)  → header (port 0)
   │
   └──► Tagged Stream Mux  (blocks.tagged_stream_mux, Type: byte, Len Tag: packet_len, ninputs=2)
                              header → input 0 · payload → input 1 · salida = header + payload
                              ▼
                           GMSK Mod  (digital.gmsk_mod, samples/symbol=8, bt=0.3, do_unpack=True)
                              ▼
                           BladeRF sink (gr-bladeRF; sample_rate=20e6, center_freq=2.45e9, gain=40)
```

El bloque `variable_header_format_default` (`hdr_format`) fija el header de ráfaga:
**access code** `digital.packet_utils.default_access_code` (64 bits), **threshold** `0`
y **bps** `1`. El formatter emite **solo el header** en bytes empaquetados
(access code + longitud de 16 bits repetida), y el mux antepone ese header al payload.

### RX — `rx_bladerf.grc` (BladeRF)

```
BladeRF source            (gr-bladeRF; sample_rate=20e6, center_freq=2.45e9, gain=40)
   ▼
GMSK Demod                (digital.gmsk_demod, samples/symbol=8, gain_mu=0.175, freq_error=0.0)
   ▼
Correlate Access Code     (digital.correlate_access_code_bb_ts, access_code=default, threshold=0, Tagname: packet_len)
   ▼  (emite contenido del paquete en bits, con tag de longitud en bits)
Repack Bits 1→8           (blocks.repack_bits_bb, k=1, l=8, Len Tag: packet_len, endianness=MSB_FIRST)
   ▼  (bits → bytes, tag vuelto a bytes)
Tagged Stream to PDU      (tagged_stream_to_pdu, Type: byte, Len Tag Key: packet_len)
   ▼ (msg port: out → in)
ZMQ PUSH Message Sink     (tcp://127.0.0.1:5556, timeout=100, mode=bind)
```

El correlator encuentra el access code en la secuencia de bits, lee el header de
32 bits (longitud de 16 bits *bytes* repetida), emite el payload en bits y etiqueta
`packet_len` (bits). `repack_bits_bb(1→8)` empaqueta de vuelta a bytes y reescribe
el tag en bytes, que es lo que espera `pdu_tagged_stream_to_pdu`.

> **Access code** y **umbral** deben coincidir entre TX y RX. En los flowgraphs de
> referencia ambos usan `digital.packet_utils.default_access_code` con `threshold=0`.

## Endpoints

- **`5555`** — TX: lo **conecta el flowgraph** (`ZMQ PULL Message Source`, mode=connect).
  El peer (`capture.py` vía `ZMQPduTransport`, `ZMQ_TX_BIND=True`) es quien hace **bind** en 5555.
- **`5556`** — RX: lo **bind** el flowgraph (`ZMQ PUSH Message Sink`, mode=bind).
  El peer (receptor Python) **se conecta** a 5556.

> `rx_hackrf.grc` permanece en el repo como artefacto de referencia heredado
> (HackRF por USB vía gr-osmosdr) y no forma parte del enlace blade-to-blade.

## Prerrequisitos de sistema

- GNU Radio 3.10+ (`import gnuradio` desde Python).
- **gr-bladeRF** (TX y RX) — `pip install gr-bladeRF` o build desde fuente.
- **gr-zeromq** y **pyzmq** — incluidos en GNU Radio estándar; `pip install pyzmq`.
- `python requirements-radio.txt` instalado (receptor Python, transport ZMQ PDU).

> Nota: si `gnuradio-companion`/`grcc` no está instalado, los `.grc` se pueden
> validar igualmente como XML o abrir/regenerar en una máquina con GRC.

## Orden de arranque sugerido

1. **Estación receptor (B):** `python radio/reciever_radio.py` — receptor Python (se conecta a 5556).
2. **Estación receptor (B):** iniciar el flowgraph **RX** (`rx_bladerf.grc`) — bind en 5556.
3. **Estación emisor (A):** iniciar el flowgraph **TX** (`tx_bladerf.grc`) — connect a 5555.
4. **Estación emisor (A):** `python capture.py` con `TRANSPORT="radio"` (en `config.py`).

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

- [ ] GNU Radio 3.10+, gr-bladeRF y pyzmq instalados en ambas estaciones.
- [ ] Dos BladeRF detectados por gr-bladeRF (`bladeRF-cli -p`).
- [ ] Receptor Python arrancado: `python radio/reciever_radio.py`.
- [ ] RX flowgraph arrancado y **bind** en `5556` (sin error).
- [ ] TX flowgraph arrancado y **connect** a `5555` (sin error).
- [ ] `capture.py` con `TRANSPORT="radio"`; el TX PULL recibe PDUs (`cons(dict, u8vector)`).
- [ ] El RX PUSH emite PDUs que decodifica `radio/pmt_codec.py` (bytes H.264 del receptor).
- [ ] `hdr_format` (access code) y el correlator coinciden entre TX y RX.
- [ ] Link de RF 2.45 GHz / 20 Msps: sin pérdida de de-sincronización GMSK,
      `packet_len` consistente entre TX y RX. Ambos extremos usan osciladores libres,
      por lo que puede ser necesario ajustar `freq_error` o `omega_relative_limit`
      del GMSK Demod para compensar el offset de frecuencia, así como subir el
      `threshold` del correlator si el acceso por radio degrada el bit error rate.