import subprocess
from nalu_parser import extract_nalus_chunk, nalu_type, nalu_type_name
from sender_nalu import initialize_connection, send_nalu, send_nalu_paquetized, send_single_header
from packetizer import packetize
from ffmpeg_video_source import FfmpegVideoSource
from udp_transport import UdpTransport
from priority_classifier import obtain_classification_nalu

# =======================
# Información del paquete
# =======================

def print_nalu(idx, type_nalu, nalu_name):
    print(idx)
    print(f"Tipo de nalu: {type_nalu}")
    print(f"Nombre de nalu: {nalu_name}")
    print(f"Tam {len(nalu)}")

transport = UdpTransport()
source = None

print("Listening to /dev/video0... Parsing incoming NAL Units:\n")
try:
    source = FfmpegVideoSource()
    
    while True:
        chunk = source.read_chunk()
        nalus = source.obtain_nalus_from_chunk(chunk)
        
        if nalus is not None:
            for idx, nalu in enumerate (nalus):
                numeric_type_nalu = nalu_type(nalu)
                nalu_name = nalu_type_name(numeric_type_nalu)
                priority = obtain_classification_nalu(nalu_name)

                print_nalu(idx, numeric_type_nalu, nalu_name)

                # Variables default para el paquete
                default_flag = 0 
                default_sequence = 0
                default_payload = len(nalu)

                # Packetizar los nalu en nalus del mismo tamaño
                nalus_segmented = packetize(nalu, numeric_type_nalu, default_flag, 
                                            default_sequence, default_payload, priority)

                for single_nalu_seg in nalus_segmented:
                    # Extraer datos del single_nalu_seg
                    transport.send_packet(single_nalu_seg)

except KeyboardInterrupt:
    print("Acabando el proceso...")
    if source:
        transport.send_single_header(0,0,4,0)
finally:
    if source:
        source.close()