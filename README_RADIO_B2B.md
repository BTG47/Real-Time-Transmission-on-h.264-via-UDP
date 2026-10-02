# Enlace blade→blade H.264 en vivo — Guía de instalación y arranque

Runbook para transmitir video H.264 en tiempo real **por RF entre dos BladeRF**
(una computadora emisora con cámara y una computadora receptora). Todo es
**copiar y pegar**: cada bloque de código es un grupo de comandos listos para la
terminal.

---

## 1. Topología

```
COMPUTADORA A (EMISOR)                         COMPUTADORA B (RECEPTOR)
┌─────────────────────────────┐               ┌─────────────────────────────┐
│  Cámara v4l2 (/dev/video0)  │               │                             │
│  └─ ffmpeg (libx264)        │               │                             │
│     └─ capture.py           │               │                             │
│        └─ ZMQ PUSH bind     │               │  ZMQ PULL connect           │
│           tcp://127.0.0.1:5555              │  tcp://127.0.0.1:5556       │
│           tx_bladerf.grc (PULL connect)     │  rx_bladerf.grc (PUSH bind) │
│           └─ bladeRF TX @ 2.45 GHz ────────►│  └─ bladeRF RX @ 2.45 GHz   │
│  + BladeRF (transmisión)                    │  + BladeRF (recepción)      │
│         (antena TX)                         │         (antena RX)         │
└─────────────────────────────┘               └─────────────────────────────┘
                                       RF
                                   2.45 GHz / 20 Msps / GMSK 8 sps
```

Puntos clave:

- **ZMQ es local a cada PC** (loopback `127.0.0.1`). La única conexión entre las
  dos computadoras es **la señal de RF** (blade → blade).
  No hay que abrir puertos de red.
- **Computadora A**: cámara + `capture.py` + flowgraph TX.
- **Computadora B**: flowgraph RX + `radio/reciever_radio.py` (reproduce con ffplay).
  **No necesita cámara** y **no ejecuta** `capture.py`.
- Parámetros RF fijos: **2.45 GHz**, **20 Msps**, GMSK **8 sps** (ampliables desde
  `radio/flowgraphs/tx_bladerf.grc` y `rx_bladerf.grc`).
- Cada paquete viaja como una **ráfaga con access code + header de longitud**
  (`digital.packet_utils.default_access_code`, 64 bits). El TX antepone el access
  code y la longitud de 16 bits (formatter); el RX correlaciona el access code y
  repaquetiza bits → bytes (correlator + repack). TX y RX deben usar el mismo
  access code (`hdr_format` y correlator).

---

## 2. Parte común — instalación idéntica en A y B

Ejecuta **todos** los comandos siguientes en las **dos** computadoras.

### 2.1 Crear el entorno conda

```bash
conda create -y -n radio -c conda-forge \
  gnuradio gnuradio-grc gnuradio-zeromq \
  pyzmq libbladeRF libbladeRF-python
```

### 2.2 Activar el entorno

```bash
conda activate radio
```

> Cuando abras una terminal nueva, recuerda ejecutar `conda activate radio`
> antes de cualquier comando de este runbook.

### 2.3 Instalar gr-bladeRF desde fuente

> No hay paquete conda de `gr-bladeRF`; se compila contra el entorno.

```bash
conda install -y -n radio -c conda-forge cmake ninja pkg-config gxx_linux-64
conda activate radio
```

```bash
cd "$HOME"
git clone https://github.com/Nuand/gr-bladeRF.git
cd gr-bladeRF
mkdir -p build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX="${CONDA_PREFIX}"
make -j"$(nproc)"
make install
```

### 2.4 Verificar la instalación

```bash
grcc --version
```

```bash
python -c "import gnuradio; from gnuradio import digital, blocks, zeromq; print('gnuradio OK')"
```

```bash
python -c "import bladeRF; print('bladeRF OK')"
```

```bash
ls "${CONDA_PREFIX}/share/gnuradio/grc/blocks" | grep -i bladerf
```

Debe listar (como mínimo): `bladeRF_source` y `bladeRF_sink`.

### 2.5 Dependencias de sistema (FFmpeg, V4L2)

```bash
sudo dnf install -y ffmpeg v4l-utils
```

```bash
ffmpeg -version | head -1
ffplay -version | head -1
```

### 2.6 Clonar el proyecto e instalar dependencias Python

```bash
cd "$HOME"
git clone https://github.com/<tu-org>/Real-Time-Transmission-on-h.264-via-UDP.git video-radio
cd video-radio
conda activate radio
pip install -r requirements-radio.txt
```

### 2.7 Fijar el transporte en radio

En `config.py` verifica que esté:

```python
TRANSPORT = "radio"   # "udp" para el baseline UDP; "radio" para GNU Radio vía ZMQ
```

---

## 3. Computadora A — EMISORA (con cámara + BladeRF TX)

### 3.1 Verificar cámara y BladeRF

```bash
ls /dev/video*
```

```bash
bladeRF-cli -p
```

Debe aparecer el BladeRF. Si dice `No devices are available`, revisa el cable
USB y los permisos (udev).

### 3.2 Compilar el flowgraph de transmisión

```bash
cd "$HOME/video-radio"
conda activate radio
grcc -o radio/flowgraphs/ radio/flowgraphs/tx_bladerf.grc
```

### 3.3 Encender la transmisión

**Terminal 1** — arranca el flowgraph TX (conecta a `127.0.0.1:5555`):

```bash
cd "$HOME/video-radio"
conda activate radio
python radio/flowgraphs/tx_bladerf.py
```

**Terminal 2** — arranca la captura (bind en `127.0.0.1:5555`):

```bash
cd "$HOME/video-radio"
conda activate radio
python capture.py
```

Si la cámara no es `/dev/video0`, cámbiala en `ffmpeg_video_source.py` antes
de arrancar.

---

## 4. Computadora B — RECEPTORA (BladeRF RX, sin cámara)

### 4.1 Verificar el BladeRF

```bash
bladeRF-cli -p
```

### 4.2 Compilar el flowgraph de recepción

```bash
cd "$HOME/video-radio"
conda activate radio
grcc -o radio/flowgraphs/ radio/flowgraphs/rx_bladerf.grc
```

### 4.3 Encender la recepción

> Orden importante: primero el bind (flowgraph RX), después el receptor Python.

**Terminal 1** — arranca el flowgraph RX (bind en `127.0.0.1:5556`):

```bash
cd "$HOME/video-radio"
conda activate radio
python radio/flowgraphs/rx_bladerf.py
```

**Terminal 2** — arranca el receptor de video (conecta a `127.0.0.1:5556`):

```bash
cd "$HOME/video-radio"
conda activate radio
python radio/reciever_radio.py
```

Debería abrir una ventana de **ffplay** reproduciendo el video recibido por RF.

---

## 5. Checklist de verificación

- [ ] `conda activate radio` en todas las terminales.
- [ ] `bladeRF-cli -p` reconoce el BladeRF en A y en B.
- [ ] Antenas conectadas en ambos BladeRF.
- [ ] `grcc` compiló `tx_bladerf.grc` (A) y `rx_bladerf.grc` (B) sin errores.
- [ ] A: TX en 2.45 GHz / 20 Msps / 8 sps → `python radio/flowgraphs/tx_bladerf.py`.
- [ ] B: RX en 2.45 GHz / 20 Msps / 8 sps → `python radio/flowgraphs/rx_bladerf.py` (bind).
- [ ] A: `python capture.py` publica PDUs en 5555 (bind).
- [ ] B: `python radio/reciever_radio.py` decodifica PDUs de 5556 (connect).
- [ ] TX (`hdr_format`) y RX (correlator) usan el mismo access code (por defecto `default_access_code`).
- [ ] Venta de ffplay mostrando video.

---

## 6. Si no sale video (offset de frecuencia)

Los dos BladeRF usan osciladores independientes (no comparten reloj), por lo que
sus frecuencias no son exactamente iguales. Si el demod GMSK pierde la
sincronía:

1. En `radio/flowgraphs/rx_bladerf.grc`, bloque `digital_gmsk_demod`, prueba
   valores del parámetro `freq_error` (por ejemplo `0.0`, `-50`, `50`) hasta
   estabilizar el flujo.
2. Si la deriva de símbolo es el problema, amplía `omega_relative_limit`
   (por defecto `0.005`) a `0.01` y recompila:

```bash
grcc -o radio/flowgraphs/ radio/flowgraphs/rx_bladerf.grc
```

3. El correlator (`digital_correlate_access_code_bb_ts`) usa un **threshold** de
   `0` (coincidencia exacta del access code). Si la señal llega degradada y no se
   detectan paquetes, súbelo a `3` en ambos extremos (el umbral de `hdr_format`
   del TX y el del correlator del RX deben coincidir) y recompila:

```bash
grcc -o radio/flowgraphs/ radio/flowgraphs/tx_bladerf.grc radio/flowgraphs/rx_bladerf.grc
```

4. Verifica ganancia RX en `bladeRF_source` (`gain0`, típico `40`) y que la
   distancia/atenuación entre antenas permita recibir señal.

---

## 7. Detener

En todas las terminales: `Ctrl + C`.

- `capture.py` imprime el resumen de métricas del emisor al terminar.
- `reciever_radio.py` escribe el video reconstruido en `reconstructed_rf`
  después de su timeout de recepción.