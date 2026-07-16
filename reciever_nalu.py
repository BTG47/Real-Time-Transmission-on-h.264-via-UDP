import socket 
import subprocess
import cv2
from video_header import VideoHeader
from nalu_parser import nalu_type_name, nalu_type
from config import UDP_SAFE_PAYLOAD, SERVER_IP, SERVER_PORT, REAL_HEADER_SIZE

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
    is_fragmented = header_recieved.fragment_count > 1
    if is_fragmented:
        is_first_fragment = header_recieved.fragment_index == 0
        is_last_fragment = header_recieved.fragment_index == header_recieved.fragment_count -1

        if is_first_fragment:
            nalu_temp = [incoming_video]
        elif is_last_fragment:
            nalu_temp.append(incoming_video)
            final_nalu = b"".join(nalu_temp)
            nalu_temp = []
        else: # Resto de paquetes intermedios normales
            nalu_temp.append(incoming_video)
    else:
        final_nalu = incoming_video
    return final_nalu, nalu_temp
    
def obtain_header_video(incoming_bytes):
    incoming_header = incoming_bytes[:REAL_HEADER_SIZE]
    incoming_video = incoming_bytes[REAL_HEADER_SIZE:]

    header_recieved = VideoHeader.from_byte(incoming_header)
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

    if end == True:
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
