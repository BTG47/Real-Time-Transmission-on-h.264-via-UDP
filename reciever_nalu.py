import socket 
import subprocess
import cv2
from simple_rtp_header import SimpleRtp
from nalu_parser import nalu_type_name, nalu_type
from config import UDP_SAFE_PAYLOAD
# =========
# Variables de red
# ================

SERVER_IP = '127.0.0.1'
SERVER_PORT = 65432
PACKET_SIZE = 8



# =============
# Configuración del receptor ffmepg
# ==============

cmd = [
    'ffplay', 
    '-fflags', 'nobuffer',
    '-flags', 'low_delay',
    '-framedrop',
    '-f', 'h264',
    '-'
]

client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.bind((SERVER_IP, SERVER_PORT))
client_socket.settimeout(5.0)

ffplay_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)


print(f"Escuchando {SERVER_IP}: {SERVER_PORT}")

video = []
nalu_temp = []
end = False

def extract_nalu_from_incoming_byte(header_recieved, nalu_temp, final_nalu, incoming_video):
    if (header_recieved.flags == 0):
        final_nalu = incoming_video

    if header_recieved.flags == 1:
        nalu_temp = [incoming_video]

    if header_recieved.flags == 2:
        nalu_temp.append(incoming_video)

    if header_recieved.flags == 3:
        nalu_temp.append(incoming_video)
        for nalu in nalu_temp:
            final_nalu += nalu
        nalu_temp = []
    return final_nalu, nalu_temp
    
def obtain_header_video(incoming_bytes):
    incoming_header = incoming_bytes[:PACKET_SIZE]
    incoming_video = incoming_bytes[PACKET_SIZE:]

    header_recieved = SimpleRtp.from_byte(incoming_header)
    return header_recieved, incoming_video

while True:
    try:
        incoming_bytes, client_addr = client_socket.recvfrom(UDP_SAFE_PAYLOAD)
    except socket.timeout:
        print("Tiempo de espera agotado")
        end = True
        incoming_bytes = None
    
    if end or incoming_bytes is None:
        incoming_header = None
        incoming_video = None
        header_recieved = None
    else:
        header_recieved, incoming_video = obtain_header_video(incoming_bytes)
        print(header_recieved)

        final_nalu = b''
        final_nalu, nalu_temp = extract_nalu_from_incoming_byte(header_recieved, nalu_temp, final_nalu, incoming_video)

        if len(final_nalu) > 0:
            video.append(final_nalu)
            if ffplay_process.stdin is not None:
                ffplay_process.stdin.write(b'\x00\x00\x00\x01' + final_nalu)
                ffplay_process.stdin.flush()


    
    if (header_recieved is not None and header_recieved.flags == 4) or end == True:
        print("Último paquete alcanzado, fin")
            # Matar proceso stdin
        if ffplay_process.stdin is not None:
            ffplay_process.stdin.close()
        ffplay_process.terminate()
        #Dejado solo para debuggear
        with open('reconstructed2', 'wb') as f:
            for video_nalu in video:
                f.write(b'\x00\x00\x00\x01' + video_nalu)
        break
