from transport.transport import Transport
import socket
from config import SERVER_IP, SERVER_PORT, DEBUG
from packets.packetizer import NALUPacket
from transport.video_header import VideoHeader
from transport.datagram import build_datagram

class UdpTransport(Transport):

    def __init__(self):
        self.sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_packet(self, packet: NALUPacket) -> int:
        data_to_send = build_datagram(packet)
        if DEBUG:
            header = VideoHeader(packet.packet_sequence, packet.nalu_id, packet.fragment_index,
                                 packet.fragment_count, packet.nal_type, packet.priority,
                                 packet.timestamp_ns, len(packet.payload))
            print(header)
        self.sender_socket.sendto(data_to_send, (SERVER_IP, SERVER_PORT))
        return len(data_to_send)

    def send_single_header(self, nalu_packet_sequence, nalu_id, nalu_fragment_index, 
                           nalu_fragment_count,nalu_type, nalu_priority, nalu_timestamp_ns,
                           nalu_payload_size):
        header = VideoHeader(nalu_packet_sequence, nalu_id, nalu_fragment_index,
                             nalu_fragment_count, nalu_type, nalu_priority, nalu_timestamp_ns,
                             nalu_payload_size)
        print(header)
        header_to_send = header.to_bytes()
        self.sender_socket.sendto(header_to_send, (SERVER_IP, SERVER_PORT))

    def close(self):
        self.sender_socket.close()
