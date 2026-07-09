import subprocess
from nalu_parser import extract_nalus_chunk, nalu_type, nalu_type_name
from sender_nalu import initialize_connection, send_nalu, send_nalu_paquetized, send_single_header
from packetizer import packetize

# =======================
# Información del paquete
# =======================

LECTURE_SIZE = 4096
SERVER_IP = '127.0.0.1'
SERVER_PORT = 65432

cmd = [
    'ffmpeg', '-hide_banner',
    '-f', 'v4l2',
    '-i', '/dev/video0',
    '-c:v', 'libx264',
    '-preset', 'ultrafast',
    '-tune', 'zerolatency',
    '-f', 'h264',
    'pipe:1'
]

def print_nalu(idx, nalu_hashable, type_nalu, nalu_name):
    print(idx)
    print(f"Tipo de nalu: {type}")
    print(f"Nombre de nalu: {nalu_name}")
    print(f"Tam {len(nalu)}")

process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

stream_buffer = bytearray()
remain_buffer = 0

sender_socket = initialize_connection()

print("Listening to /dev/video0... Parsing incoming NAL Units:\n")
try:
    stdout = process.stdout
    if stdout is None:
        raise RuntimeError("Failed to open process stdout")
    
    while True:
        chunk = stdout.read(LECTURE_SIZE)
        if not chunk:
            print("No hay chunk")
            break
        # process chunk (append to buffer or parse NAL units)
        stream_buffer.extend(chunk)
        nalus, remain_buffer = extract_nalus_chunk(stream_buffer)
        stream_buffer = stream_buffer[-remain_buffer:]

        if nalus is not None:
            for idx, nalu in enumerate (nalus):
                nalu_hashable = bytes(nalu)
                type_nalu = nalu_type(nalu_hashable)
                nalu_name = nalu_type_name(type_nalu)

                # Variables default para el paquete
                default_flag = 0 
                default_sequence = 0
                default_payload = len(nalu)

                print_nalu(idx,nalu_hashable, type_nalu, nalu_name)
                # Packetizar los nalu
                nalus_segmented = packetize(nalu, type_nalu, default_flag, default_sequence, default_payload)

                for single_nalu_seg in nalus_segmented:
                    # Extraer datos del single_nalu_seg
                    nalu_seg_payload = single_nalu_seg.payload
                    nalu_seg_sequence = single_nalu_seg.sequence
                    nalu_seg_type = single_nalu_seg.nal_type
                    nalu_seg_flag = single_nalu_seg.flag
                    nalu_seg_size = single_nalu_seg.size
                    # Enviar los datos de los nalus segmentados
                    send_nalu(sender_socket, nalu_seg_payload, nalu_seg_sequence, nalu_seg_type, 
                              nalu_seg_flag, nalu_seg_size, SERVER_IP, SERVER_PORT)

except KeyboardInterrupt:
    print("Acabando el proceso...")
    send_single_header(sender_socket,0,0,4,0,SERVER_IP,SERVER_PORT)
finally:
    process.terminate()