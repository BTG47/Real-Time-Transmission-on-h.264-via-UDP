import subprocess
from nalu_parser import extract_nalus_chunk, nalu_type, nalu_type_name
from packetizer import Paketizer
from ffmpeg_video_source import FfmpegVideoSource
from udp_transport import UdpTransport
from priority_classifier import obtain_classification_nalu
from packetScheduler import PacketScheduler

# =======================
# Información del paquete
# =======================

def print_nalu(idx, type_nalu, nalu_name, nalu_size):
    print(idx)
    print(f"Tipo de nalu: {type_nalu}")
    print(f"Nombre de nalu: {nalu_name}")
    print(f"Tam {nalu_size}")

transport = UdpTransport()
logicPacket = Paketizer()
schedule = PacketScheduler()
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
                priority = obtain_classification_nalu(numeric_type_nalu)
                nalu_size = len(nalu)

                print_nalu(idx, numeric_type_nalu, nalu_name, nalu_size)

                # Packetizar los nalu en nalus del mismo tamaño
                nalus_segmented = logicPacket.packetize(nalu, numeric_type_nalu, priority)

                schedule.enqueue(nalus_segmented)
                if schedule.has_packets():
                    packets = schedule.dequeue()
                    if packets is None:
                        break

                    for packet in packets:
                        transport.send_packet(packet)

except KeyboardInterrupt:
    print("Acabando el proceso...")
    # Debido a que ya no hay flags, de momento no se puede reconstrir el video
    #if source:
    #    transport.send_single_header(nalu_packet_sequence= 0,
    #                                 nalu_id=,
    #                                 nalu_fragment_index=,
    #                                 nalu_fragment_count=,
    #                                 nalu_type=,
    #                                 nalu_priority=,
    #                                 nalu_timestamp_ns=,
    #                                 nalu_payload_size=)
finally:
    if source:
        source.close

    transport.close()