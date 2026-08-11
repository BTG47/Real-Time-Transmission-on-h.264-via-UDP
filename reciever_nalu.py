import socket 
import subprocess
from transport.video_header import VideoHeader
from metrics.reciever_metrics import RecieverMetrics
from packets.nalu_parser import nalu_type_name, nalu_type
from config import UDP_SAFE_PAYLOAD, SERVER_IP, SERVER_PORT, REAL_HEADER_SIZE, DEBUG

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
pending_nalus = {}
end = False

def extract_nalu_from_incoming_byte(header_recieved, pending_nalus, incoming_video):
    """
    Se manejará una estructura de tipo
    Pending_nalus {
        naluId {
            "fragment_count" = hader.fragment_count
            "fragments" = {
                header.fragment_index = incoming video
            }
        }
    }
    """
    nalu_id = header_recieved.nalu_id
    nalu_index = header_recieved.fragment_index
    nalu_fragment_count = header_recieved.fragment_count


    # Verificaciones de seguridad
    if nalu_fragment_count <= 0:
        return None

    if not 0 <= nalu_index < nalu_fragment_count:
        return None

    if header_recieved.payload_size != len(incoming_video):
        return None

    if nalu_id not in pending_nalus:
        pending_nalus[nalu_id] = {
            "fragment_count": nalu_fragment_count,
            "fragments": {}
        } 


    pending_nalus[nalu_id]["fragments"][nalu_index] = incoming_video

    fragments = pending_nalus[nalu_id]["fragments"]

    if len(fragments) == nalu_fragment_count:
        final_nalu = b"".join(fragments[index] for index in range(nalu_fragment_count))

        del pending_nalus[nalu_id]

        return final_nalu
    return None
    
def obtain_header_video(incoming_bytes):
    incoming_header = incoming_bytes[:REAL_HEADER_SIZE]
    incoming_video = incoming_bytes[REAL_HEADER_SIZE:]

    header_recieved = VideoHeader.from_byte(incoming_header)
    return header_recieved, incoming_video, incoming_header

reciever_metrics = RecieverMetrics()
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
        header_recieved, incoming_video, incoming_header = obtain_header_video(incoming_bytes)

        reciever_metrics.record(header_recieved, size_header_recieved= len(incoming_header), size_video_recieved= len(incoming_video))
        
        if DEBUG:
            print(header_recieved)

        final_nalu = b''
        final_nalu = extract_nalu_from_incoming_byte(header_recieved, pending_nalus, incoming_video)

        if final_nalu != None:
            video.append(final_nalu)
            if ffplay_process.stdin is not None:
                ffplay_process.stdin.write(b'\x00\x00\x00\x01' + final_nalu)
                ffplay_process.stdin.flush()

    if end == True:
        print("Último paquete alcanzado, fin")
        reciever_metrics.summary()
            # Matar proceso stdin
        if ffplay_process.stdin is not None:
            ffplay_process.stdin.close()
        ffplay_process.terminate()
        #Dejado solo para debuggear
        with open('reconstructed2', 'wb') as f:
            for video_nalu in video:
                f.write(b'\x00\x00\x00\x01' + video_nalu)
        break
