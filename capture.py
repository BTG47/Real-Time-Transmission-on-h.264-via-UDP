import subprocess
from nalu_parser import extract_nalus_chunk, nalu_type, nalu_type_name
from packetizer import Paketizer
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

Transport = UdpTransport()
LogicPacket = Paketizer()
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

                # Packetizar los nalu en nalus del mismo tamaño
                nalus_segmented = LogicPacket.packetize(nalu, numeric_type_nalu, priority)

                for single_nalu_seg in nalus_segmented:
                    # Extraer datos del single_nalu_seg
                    Transport.send_packet(single_nalu_seg)

except KeyboardInterrupt:
    print("Acabando el proceso...")
    # Debido a que ya no hay flags, de momento no se puede reconstrir el video
    #if source:
    #    Transport.send_single_header(nalu_packet_sequence= 0,
    #                                 nalu_id=,
    #                                 nalu_fragment_index=,
    #                                 nalu_fragment_count=,
    #                                 nalu_type=,
    #                                 nalu_priority=,
    #                                 nalu_timestamp_ns=,
    #                                 nalu_payload_size=)
finally:
    if source:
        source.close()