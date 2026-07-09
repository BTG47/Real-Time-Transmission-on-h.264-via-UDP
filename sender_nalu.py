import socket

from nalu_parser import extract_nalus, nalu_type, nalu_type_name

from simple_rtp_header import SimpleRtp
from packetizer import NALUPacket

# ================
# Variables de red
# ================

SERVER_IP = '127.0.0.1'
SERVER_PORT = 65432
SEQUENCE = 0
NAL_TYPE = 0
FLAG = 0

def initialize_connection():
    sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return sender_socket

def send_nalu(sender_socket, nalu, actual_sequence, nalu_type, flag, payload_size, server_ip, server_port):
    header = SimpleRtp(actual_sequence, nalu_type, flag, payload_size)
    print(header)
    header_to_send = header.to_bytes()
    data_to_send = header_to_send + nalu
    sender_socket.sendto(data_to_send, (server_ip, server_port))

def send_single_header(sender_socket, actual_sequence, nalu_type, flag, payload_size, server_ip, server_port):
    header = SimpleRtp(actual_sequence, nalu_type, flag, payload_size)
    print(header)
    header_to_send = header.to_bytes()
    sender_socket.sendto(header_to_send, (server_ip, server_port))

def send_nalu_paquetized(packet_list, sender_socket, server_ip, server_port):
    for packet in packet_list:
        nalu_payload = packet.payload
        sequence = packet.sequence
        nal_type = packet.nal_type
        flag = packet.flag
        size = packet.size

        send_nalu(sender_socket, nalu_payload, sequence, nal_type, flag, size, server_ip, server_port)
