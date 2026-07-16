from transport import Transport
import socket
from config import SERVER_IP, SERVER_PORT
from packetizer import NALUPacket
from video_header import VideoHeader
from priority_classifier import Priority

class UdpTransport(Transport):

    def __init__(self):
        self.sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_packet(self, packet: NALUPacket):


        # Romper el paquete en unidades
        nalu_packet_sequence = packet.packet_sequence
        nalu_id = packet.nalu_id 
        nalu_fragment_index = packet.fragment_index 
        nalu_fragment_count = packet.fragment_count
        nalu_type = packet.nal_type
        nalu_priority = packet.priority
        nalu_timestamp_ns = packet.timestamp_ns
        nalu_payload = packet.payload

        nalu_pauload_size = len(nalu_payload)

        # Preparar datos lógicos
        header = VideoHeader(nalu_packet_sequence, nalu_id, nalu_fragment_index,
                             nalu_fragment_count, nalu_type, nalu_priority, nalu_timestamp_ns,
                             nalu_pauload_size)
        print(header)
        header_to_send = header.to_bytes()
        data_to_send = header_to_send + nalu_payload
        if len(data_to_send) > 1200:
            raise ValueError(
                f"Datagrama demasiado grande: {len(data_to_send)} bytes "
                f"(header={len(header_to_send)}, payload={len(nalu_payload)})"
            )
        # Enviar datos
        self.sender_socket.sendto(data_to_send, (SERVER_IP, SERVER_PORT))

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
