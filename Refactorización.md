# Refactorización

## Fase 1: Dividir prioridades
En esta fase, el objetivo es simplificar y separar los trabajos en códigos que sean fácilmente distingibles

| Responsabilidad            | Archivo actual   | Archivo propuesto                   |
| -------------------------- | ---------------- | ----------------------------------- |
| Capturar y codificar video | `capture.py`     | `ffmpeg_video_source.py`                   |
| Extraer NALUs              | `nalu_parser.py` | Se mantiene                         |
| Clasificar prioridad       | No existe        | `priority_classifier.py`            |
| Fragmentar NALUs           | `packetizer.py`  | Se mantiene                         |
| Enviar datos               | `sender_nalu.py` | `transport.py` / `udp_transport.py` |
| Coordinar todo             | `capture.py`     | Se mantiene                         |
| Métricas                   | No existe        | Más adelante                        |


