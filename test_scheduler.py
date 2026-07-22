import time
from nalu_parser import nalu_type
from packetizer import Paketizer
from udp_transport import UdpTransport
from priority_classifier import obtain_classification_nalu
from packetScheduler import PacketScheduler
from priority_classifier import Priority
from packetizer import NALUPacket

transport = UdpTransport()
logicPacket = Paketizer()
schedule = PacketScheduler()

NALU = b''

time = time.monotonic_ns()

# Se van a simular varios datos. Primero se empaqueta. Se va a enviar 2 HIGH y 1 CRITICAL
nalu_packet_high_1 = NALUPacket(packet_sequence = 1, 
                            nalu_id = 1,
                            fragment_index= 1,
                            fragment_count= 1,
                            nal_type= 5,
                            priority= Priority.HIGH,
                            timestamp_ns = time,
                            payload=NALU)

nalu_packet_high_2 = NALUPacket(packet_sequence = 2, 
                            nalu_id = 2,
                            fragment_index= 1,
                            fragment_count= 1,
                            nal_type= 5,
                            priority= Priority.HIGH,
                            timestamp_ns = time,
                            payload=NALU)

nalu_packet_critial_1 = NALUPacket(packet_sequence = 3, 
                            nalu_id = 3,
                            fragment_index= 1,
                            fragment_count= 1,
                            nal_type= 7,
                            priority= Priority.CRITICAL,
                            timestamp_ns = time,
                            payload=NALU)
list_high_1 = [nalu_packet_high_1]
list_high_2 = [nalu_packet_high_2]
list_critial = [nalu_packet_critial_1]
print("Enqueue...")
schedule.enqueue(list_high_1)
schedule.enqueue(list_high_2)
schedule.enqueue(list_critial)

while schedule.has_packets():
    print("Hay paquetes")
    packets = schedule.dequeue()
    if packets is None:
        break
    for packet in packets:
        print("Transportando...")
        transport.send_packet(packet=packet)
