from transport import Transport
import socket
from config import SERVER_IP, SERVER_PORT
from packetizer import NALUPacket
from simple_rtp_header import SimpleRtp
class UdpTransport(Transport):

    def __init__(self):
        self.sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_packet(self, packet: NALUPacket):
        # Romper el paquete en unidades
        nalu_seg_payload = packet.payload
        nalu_seg_sequence = packet.sequence
        nalu_seg_type = packet.nal_type
        nalu_seg_flag = packet.flag
        nalu_seg_size = packet.size

        # Preparar datos lógicos
        header = SimpleRtp(nalu_seg_sequence, nalu_seg_type, nalu_seg_flag, nalu_seg_size)
        print(header)
        header_to_send = header.to_bytes()
        data_to_send = header_to_send + nalu_seg_payload

        # Enviar datos
        self.sender_socket.sendto(data_to_send, (SERVER_IP, SERVER_PORT))

    def send_single_header(self, actual_sequence, nalu_type, flag, payload_size):
        header = SimpleRtp(actual_sequence, nalu_type, flag, payload_size)
        print(header)
        header_to_send = header.to_bytes()
        self.sender_socket.sendto(header_to_send, (SERVER_IP, SERVER_PORT))

    def close(self):
        self.sender_socket.close()
