# H.264 Real-Time Streaming Prototype over UDP

Prototipo experimental para transmitir video H.264 en tiempo real usando UDP.

El objetivo actual no es implementar el protocolo final, sino disponer de una base modular y medible para experimentar con:

- captura y codificación H.264;
- parsing de NALUs;
- fragmentación;
- prioridades;
- scheduling;
- transporte UDP;
- reconstrucción en el receptor;
- métricas de emisor y receptor;
- futura migración y comparación con C++.

> La documentación técnica extensa, contratos internos, diagramas y guía de migración a C++ se encuentran en:
>
> **`HANDOFF_CPP_UDP_H264_v2.md`**

---

## 1. Flujo general

```text
Cámara
  ↓
FFmpeg
  ↓
H.264 Annex B
  ↓
NALU Parser
  ↓
Priority Classifier
  ↓
Packetizer
  ↓
Packet Scheduler
  ↓
UDP Transport
  ↓
──────────────────────────── Red / localhost
  ↓
UDP Receiver
  ↓
VideoHeader + Payload
  ↓
Reensamblado por nalu_id / fragment_index
  ↓
NALU completa
  ↓
ffplay
```

---

## 2. Estructura del proyecto

```text
07_REAL_TIME_H264/
├── metrics/
│   ├── reciever_metrics.py
│   └── sender_metrics.py
│
├── packets/
│   ├── nalu_parser.py
│   ├── packetizer.py
│   ├── packetScheduler.py
│   └── priority_classifier.py
│
├── test/
│   └── test_scheduler.py
│
├── transport/
│   ├── sender_nalu.py
│   ├── transport.py
│   ├── udp_transport.py
│   └── video_header.py
│
├── capture.py
├── config.py
├── ffmpeg_video_source.py
├── reciever_nalu.py
├── requirements.txt
├── README.md
└── HANDOFF_CPP_UDP_H264_v2.md
```

`sender_nalu.py` contiene código histórico de iteraciones anteriores y no forma parte del flujo principal actual.

---

## 3. Requisitos

### Sistema operativo

El prototipo actual está pensado principalmente para Linux.

La captura utiliza:

```text
v4l2
/dev/video0
```

Comprueba que la cámara exista con:

```bash
ls /dev/video*
```

o:

```bash
v4l2-ctl --list-devices
```

### Python

Se recomienda Python 3.11.

El flujo principal actual usa únicamente módulos de la biblioteca estándar de Python, por lo que `requirements.txt` no instala paquetes externos por defecto.

Instalación:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

El archivo `requirements.txt` se mantiene intencionalmente mínimo.

### FFmpeg

Se necesita:

- `ffmpeg`
- `ffplay`
- herramientas de V4L2

En Fedora:

```bash
sudo dnf install ffmpeg ffmpeg-devel v4l-utils
```

Comprobar instalación:

```bash
ffmpeg -version
ffplay -version
```

FFmpeg no se instala mediante `requirements.txt`; es una dependencia del sistema.

---

## 4. Configuración

La configuración principal está en:

```text
config.py
```

Valores importantes:

```python
DEBUG = False
LECTURE_SIZE = 4096
SERVER_IP = "127.0.0.1"
SERVER_PORT = 65432
UDP_SAFE_PAYLOAD = 1200
```

El tamaño máximo del payload se calcula automáticamente restando el tamaño real de `VideoHeader`.

---

## 5. Ejecutar en una sola computadora

Primero inicia el receptor.

### Terminal 1 — receptor

Desde la raíz del proyecto:

```bash
python reciever_nalu.py
```

Deberías ver algo similar a:

```text
Escuchando 127.0.0.1:65432
```

### Terminal 2 — emisor

Desde la raíz del proyecto:

```bash
python capture.py
```

El emisor abre la cámara, codifica H.264, extrae NALUs, asigna prioridad, fragmenta, agenda paquetes, envía por UDP y registra métricas.

Para detener:

```text
Ctrl + C
```

El emisor imprime un resumen de métricas al terminar.

El receptor termina después de alcanzar su timeout de recepción y también imprime sus métricas.

---

## 6. Ejecutar entre dos computadoras

En el equipo receptor:

1. identifica su IP local;
2. asegúrate de que el puerto UDP configurado esté permitido por el firewall;
3. ejecuta `reciever_nalu.py`.

En ambos equipos, cambia en `config.py`:

```python
SERVER_IP = "<IP_DEL_RECEPTOR>"
```

Por ejemplo:

```python
SERVER_IP = "192.168.1.50"
```

El puerto debe coincidir:

```python
SERVER_PORT = 65432
```

Después:

### Receptor

```bash
python reciever_nalu.py
```

### Emisor

```bash
python capture.py
```

---

## 7. Cámara

La fuente de video se define en:

```text
ffmpeg_video_source.py
```

Actualmente FFmpeg utiliza:

```bash
ffmpeg -hide_banner \
  -f v4l2 \
  -i /dev/video0 \
  -c:v libx264 \
  -preset ultrafast \
  -tune zerolatency \
  -f h264 \
  pipe:1
```

Si la cámara está en otra ruta, cambia `/dev/video0` por el dispositivo correcto.

---

## 8. Modo debug

En `config.py`:

```python
DEBUG = False
```

Cámbialo a:

```python
DEBUG = True
```

para mostrar información adicional de NALUs y headers.

Para pruebas de rendimiento conviene mantener `DEBUG = False`, porque imprimir por paquete puede alterar las métricas.

---

## 9. Header actual

El protocolo experimental utiliza un header binario custom de **24 bytes**:

```text
packet_sequence   4 bytes
nalu_id           4 bytes
fragment_index    2 bytes
fragment_count    2 bytes
nal_type          1 byte
priority          1 byte
timestamp_ns      8 bytes
payload_size      2 bytes
```

Formato:

```text
[ VideoHeader 24 B ][ payload H.264 ]
```

El datagrama completo no debe superar 1200 bytes, por lo que el payload máximo actual es de 1176 bytes.

El contrato binario exacto y las consideraciones de interoperabilidad con C++ están documentadas en:

```text
HANDOFF_CPP_UDP_H264_v2.md
```

---

## 10. Prioridades

Clasificación actual:

```text
CRITICAL → SPS / PPS
HIGH     → IDR
NORMAL   → non-IDR
LOW      → SEI
```

Estas prioridades son lógicas y actualmente sirven para organizar paquetes mediante `PacketScheduler`.

---

## 11. Reconstrucción del receptor

El receptor mantiene NALUs pendientes mediante una estructura equivalente a:

```text
pending_nalus[nalu_id]
├── fragment_count
└── fragments[fragment_index] = payload
```

Cuando están presentes todos los índices esperados, la NALU se reconstruye en orden y se elimina del conjunto pendiente.

Esto permite manejar fragmentos de distintas NALUs intercalados.

---

## 12. Métricas

### Emisor

Se registran, entre otras:

```text
payload_bitrate
wire_bitrate
payload_bytes
wire_bytes_sent
packets_sent
nalus_sent
fragmented_packets_sent
packets_by_priority
packets_by_nal_type
```

### Receptor

Se registran métricas relacionadas con:

```text
paquetes recibidos
bytes recibidos
bitrate
paquetes únicos
duplicados
fuera de orden
NALUs
prioridades
tipos de NALU
```

La lógica de pérdidas, expiración y NALUs incompletas sigue en evolución.

---

## 13. Prueba del scheduler

Existe una prueba sencilla en:

```text
test/test_scheduler.py
```

Ejecuta desde la raíz:

```bash
python test/test_scheduler.py
```

Su objetivo es comprobar que el scheduler respete:

```text
CRITICAL
HIGH
NORMAL
LOW
```

independientemente del orden de inserción.

---

## 14. Limitaciones actuales

Este prototipo todavía no implementa completamente:

- retransmisión;
- FEC;
- timeout para NALUs incompletas;
- limpieza avanzada de `pending_nalus`;
- garantía del orden final entre NALUs completadas;
- jitter buffer;
- sincronización de relojes entre equipos;
- seguridad;
- telemetría;
- control;
- QUIC;
- GNU Radio;
- adaptación dinámica de bitrate.

---

## 15. Comparación Python ↔ C++

Este repositorio funciona como baseline para portar el sistema a C++.

La documentación técnica se encuentra en:

```text
HANDOFF_CPP_UDP_H264_v2.md
```

Ahí se especifican arquitectura, contratos entre módulos, estructura del header, equivalencias Python → C++, pruebas de interoperabilidad, casos de reordenamiento, métricas recomendadas y limitaciones actuales.

Comparaciones previstas:

```text
Python sender → Python receiver
C++ sender    → Python receiver
Python sender → C++ receiver
C++ sender    → C++ receiver
```

Primero debe validarse compatibilidad funcional y después rendimiento.

---

## 16. Estado actual

El prototipo ya implementa:

```text
captura
→ H.264
→ parsing de NALUs
→ clasificación de prioridad
→ fragmentación
→ scheduling
→ UDP
→ métricas
→ reensamblado por nalu_id
→ reproducción con ffplay
```

No representa todavía el protocolo definitivo.

Su propósito actual es servir como una implementación experimental clara, medible y portable sobre la cual continuar trabajando.
