from priority_classifier import Priority
from video_header import VideoHeader
from nalu_parser import nalu_type_name
import time

class RecieverMetrics():
    def __init__(self):
        self.start_time = time.monotonic_ns() 
        self.current_seq = 0                # Es el tamaño del set
        self.packets_recieved = 0
        self.payload_bytes = 0
        self.wire_bytes = 0 
        self.payload_bitrate = 0
        self.wire_bitrate = 0
        self.total_nalus = 0
        self.nalu_rebuilded = 0
        self.nalu_incompletes = 0
        self.temp_nalu_count = 0            # Es un contador que aumenta por cada nalu de un mismo id
        self.temp_nalu_actual_id= 0
        self.temp_total_nalu_count = 0
        self.packets_duplicated = 0
        self.unique_packets_recieved = set()    # Uso del tam del set
        self.packets_out_of_order = 0
        self.packets_by_priority = {
            Priority.CRITICAL:0,
            Priority.HIGH:0,
            Priority.NORMAL:0,
            Priority.LOW:0,
        }
        self.packets_by_naly_type ={
            7:0,
            8:0,
            5:0,
            1:0,
            6:0
        }

    def record(self, packet:VideoHeader, size_header_recieved, size_video_recieved):
        # Sumar dato de bytes y paquetes recibidos
        self.payload_bytes += packet.payload_size  
        self.wire_bytes += (size_header_recieved + size_video_recieved)
        self.packets_recieved += 1

        # Obtener el tamaño del payload


        # Obtener nalus
        if packet.fragment_count > 1: # Esta fragmentada
            self.total_nalus += 1
            same_id = self.temp_nalu_actual_id == packet.nalu_id

            if same_id: # siguen en el mismo Nalu id
                self.temp_first_nalu = 0
                self.temp_nalu_count += 1
            else: # Ya terminó con el que estaba trabajando
                self.calculate_differences() # Calcular las métricas de perdida/completitud de la nalu anterior
                self.temp_nalu_actual_id = packet.nalu_id  
                self.temp_total_nalu_count = packet.fragment_count
                self.temp_nalu_count = 1        # Reinicio de contador, es inicio en 1 porque entró un paqute

        # Obtener paquetes perdidos
        if packet.packet_sequence >= self.current_seq: # Si el actual paquete es más grande que el previo, aumenta
            self.current_seq = packet.packet_sequence
        elif packet.packet_sequence <= self.current_seq: 
            # Ej: 2, 4, 3; si el current es 4, y el que sigue es menor, esta fuera de lugar
            self.packets_out_of_order +=1

        # Añadir al set para obtener duplicados
        total_packets_before_actual_packet = len(self.unique_packets_recieved)
        self.unique_packets_recieved.add(packet.packet_sequence)
        total_packets_after_actual_packet = len(self.unique_packets_recieved)

        if total_packets_after_actual_packet == total_packets_before_actual_packet:
            self.packets_duplicated += 1

        # Poner la iformaicón de cada paquete por prioridad
        nalu_priority = packet.priority
        if nalu_priority in self.packets_by_priority:
            self.packets_by_priority[nalu_priority] += 1
        nalu_type = packet.nal_type
        if nalu_type in self.packets_by_naly_type:
            self.packets_by_naly_type[nalu_type] += 1

        elapsed_time = (time.monotonic_ns() - self.start_time) / 1_000_000_000

        self.payload_bitrate = self.payload_bytes * 8 / elapsed_time
        self.wire_bitrate = self.wire_bytes * 8 / elapsed_time
                
    def calculate_differences(self):
        if self.temp_total_nalu_count != 0:
            difference = self.temp_total_nalu_count - self.temp_total_nalu_count
            if difference == 0: # Se recupero por completo
                self.nalu_rebuilded += 1
            else:
                self.nalu_incompletes += difference

    def summary(self):
        print("Métricas del receptor de información")
        print("Tiempo de inicio: ",self.start_time)
        print("ültima secuencia: ",self.current_seq)              
        print("Total de paquetes recibidos: ",self.packets_recieved) 
        print("Tamaño del payload en bytes recibidos : ",self.payload_bytes) 
        print("Tamaño real del paquete recibido: ",self.wire_bytes) 
        print("Bitrate del payload: ",self.payload_bitrate) 
        print("Bitrate del tam real: ",self.wire_bitrate) 
        print("Total de nalus obtenidas: ",self.total_nalus) 
        print("Total de nalus reconstruidas: ",self.nalu_rebuilded) 
        print("Total de nalus incompletas: ",self.nalu_incompletes) 
        print("Total de nalus duplicadas: ",self.packets_duplicated) 
        print("Total de paquetes únicos: ", len(self.unique_packets_recieved)) 
        print("Total de paquetes fuera de orden: ",self.packets_out_of_order) 
        print("Paquetes por prioridad: ",self.packets_by_priority) 

        packets_by_nal_name = {nalu_type_name(k): v for k,v in self.packets_by_naly_type.items()}
        print("Paquetes por tipo: ",packets_by_nal_name) 
