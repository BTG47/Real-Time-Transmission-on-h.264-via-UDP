from transport.video_header import VideoHeader
from packets.priority_classifier import Priority
import struct
# Configuración de ejecuión
DEBUG = False

# Configuración de ffmpeg_video_source.py
LECTURE_SIZE = 4096

# Configuración para UDP transport
SERVER_IP = '127.0.0.1'
SERVER_PORT = 65432
TRANSPORT = "radio"   # "udp" para el baseline UDP; "radio" para GNU Radio vía ZMQ (requiere requirements-radio.txt)

# SimpleRtp
header_for_calculate_size = VideoHeader(0,0,0,0,0,Priority.CRITICAL,0,0)
REAL_HEADER_SIZE = len(header_for_calculate_size.to_bytes())
UDP_SAFE_PAYLOAD = 1200
SIZE_MAX_PACKET = UDP_SAFE_PAYLOAD - REAL_HEADER_SIZE

# Configuración de la prioridad de paquetes
CRITICAL_VALUES = [7,8]               # 'SPS', 'PPS'
HIGH_VALUES = [5]                     # IDR slice
NORMAL_VALUES = [1]                   # non-IDR slice, otro
LOW_VALUES = [6]                      # SEI

# Configuración del scheduler de paquetes (colas con límite y descarte de antiguos)
SCHEDULER_MAX_ENTRIES_PER_QUEUE = 32  # Máx. grupos de NALU por cola de prioridad
SCHEDULER_MAX_AGE_MS = 500            # Vejez máxima de un grupo en cola antes de descartarlo