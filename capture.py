import subprocess
from packets.nalu_parser import extract_nalus_chunk, nalu_type, nalu_type_name
from packets.packetizer import Paketizer
from ffmpeg_video_source import FfmpegVideoSource
from transport.transport_factory import get_transport
from packets.priority_classifier import obtain_classification_nalu
from packets.packetScheduler import PacketScheduler
from metrics.sender_metrics import SenderMetrics
from config import DEBUG
# =======================
# Información del paquete
# =======================

def print_nalu(idx, type_nalu, nalu_name, nalu_size):
    print(idx)
    print(f"Tipo de nalu: {type_nalu}")
    print(f"Nombre de nalu: {nalu_name}")
    print(f"Tam {nalu_size}")

transport = get_transport()
logicPacket = Paketizer()
schedule = PacketScheduler()
source = None
sender = None
print("Listening to /dev/video0... Parsing incoming NAL Units:\n")
try:
    source = FfmpegVideoSource()
    sender = SenderMetrics()
    
    while True:
        chunk = source.read_chunk()
        nalus = source.obtain_nalus_from_chunk(chunk)
    
        if nalus is not None:
            for idx, nalu in enumerate (nalus):
                numeric_type_nalu = nalu_type(nalu)
                nalu_name = nalu_type_name(numeric_type_nalu)
                priority = obtain_classification_nalu(numeric_type_nalu)
                nalu_size = len(nalu)

                if DEBUG:
                    print_nalu(idx, numeric_type_nalu, nalu_name, nalu_size)
    
                # Packetizar los nalu en nalus del mismo tamaño
                nalus_segmented = logicPacket.packetize(nalu, numeric_type_nalu, priority)

                schedule.enqueue(nalus_segmented)
                if schedule.has_packets():
                    packets = schedule.dequeue()
                    if packets is None:
                        break

                    for packet in packets:
                        bytes_send_size = transport.send_packet(packet)
                        if bytes_send_size:
                            sender.record(packet,sent_data_size=bytes_send_size)

    
except KeyboardInterrupt:
    print("Acabando el proceso...")
    if sender is not None:
        sender.summary()
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
        source.close()

    transport.close()