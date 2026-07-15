from simple_rtp_header import SimpleRtp

# Configuración de ffmpeg_video_source.py
LECTURE_SIZE = 4096

# Configuración para UDP transport
SERVER_IP = '127.0.0.1'
SERVER_PORT = 65432

# SimpleRtp
header_for_calculate_size = SimpleRtp(0,0,0,0)
REAL_HEADER_SIZE = len(header_for_calculate_size.to_bytes())
UDP_SAFE_PAYLOAD = 1200
SIZE_MAX_PACKET = UDP_SAFE_PAYLOAD - REAL_HEADER_SIZE