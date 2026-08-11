import time
from packets.priority_classifier import Priority
from config import REAL_HEADER_SIZE
from packets.nalu_parser import nalu_type_name
# El objetivo de este código es obtener métricas para comparar el desarrollo del protocolo

class SenderMetrics:
    def __init__(self):
        self.start_time = time.monotonic_ns()
        self.payload_bitrate = 0
        self.wire_bitrate = 0
        self.payload_bytes = 0
        self.wire_bytes_sent = 0
        self.packets_sent = 0
        self.nalus_sent = 0
        self.fragmented_packets_sent = 0
        self.packets_by_priority = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 0,
            Priority.NORMAL:0,
            Priority.LOW:0,
        }
        self.packets_by_nal_type ={
            7:0,
            8:0,
            5:0,
            1:0,
            6:0
        }
    def record(self, packet, sent_data_size):
        if sent_data_size < 0:
            return
        # obtener información del paquete enviado
        nalu_fragment_index = packet.fragment_index 
        nalu_fragment_count = packet.fragment_count
        nalu_type = packet.nal_type
        nalu_priority = packet.priority
        #nalu_timestamp_ns = packet.timestamp_ns
        nalu_payload = packet.payload

        # Aumentar valores internos
        self.packets_sent += 1
        self.payload_bytes += len(nalu_payload)
        self.wire_bytes_sent += sent_data_size
        if nalu_fragment_index == 0:
            self.nalus_sent +=1
        if nalu_fragment_count > 1:
            # Si hay más de 1, ese fragmento se cuenta
            self.fragmented_packets_sent += 1

        # Obtener la prioridad y tipo de nalu
        if nalu_priority in self.packets_by_priority:
            self.packets_by_priority[nalu_priority] += 1
        if nalu_type in self.packets_by_nal_type:
            self.packets_by_nal_type[nalu_type] +=1

        # Obtener tiempo
        elapsed_seconds = (time.monotonic_ns() - self.start_time) / 1_000_000_000
        
        self.payload_bitrate = self.payload_bytes * 8 /elapsed_seconds
        self.wire_bitrate = self.wire_bytes_sent * 8 / elapsed_seconds

    def summary(self):
        print("==== Resumen de los datos enviados ====")
        print("start_time: ", self.start_time)
        print("payload_bitrate: ", self.payload_bitrate)
        print("wire_bitrate: ", self.wire_bitrate)
        print("payload_bytes: ", self.payload_bytes)
        print("wire_bytes_sent: ", self.wire_bytes_sent)
        print("packets_sent: ", self.packets_sent)
        print("nalus_sent: ", self.nalus_sent)
        print("fragmented_packets_sent: ", self.fragmented_packets_sent)
        print("packets_by_priority: ", self.packets_by_priority)
        # Transformar los números de tipo a string
        packets_by_nal_type_name = {nalu_type_name(k): v for k,v in self.packets_by_nal_type.items()}

        print("packets_by_nal_type: ", packets_by_nal_type_name) 