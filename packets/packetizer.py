from dataclasses import dataclass
from config import SIZE_MAX_PACKET
from packets.priority_classifier import Priority
import time

@dataclass
class NALUPacket:
    # Esta es una clase interna, es un paso previo a mandarlo por la red
    packet_sequence: int    # Es la secuencia global, no se reinicia (en estos momentos)
    nalu_id: int            # Es el id de una nalu 
    fragment_index: int     # Es la actual nalu fragmentada
    fragment_count: int     # Es el total de las nalus fragmentadas
    nal_type: int           # Es el tipo de anlu en formato númerico
    priority: Priority      # Es el tipo de prioridad con el que cuenta la nalu
    timestamp_ns: int       # Es le tiempo en el cuál fue obtenido o sacado dicho nalu
    payload: bytes          # Es en sí el contenido de la nalu


class Paketizer():

    def __init__(self):
        self.packet_sequence = 0
        self.nalu_id = 0
        #self.fragment_index = 0    Tampoco se guarda, el índice es obtenido y no sirve guardarlo
        #self.fragment_count = 0    Tampoco va, se calcula en cada iteración, no tiene que sobrevivir
        #self.nal_type = 0          Esto se importa a la función
        #self.Priority = 0          La prioridad de igual manera se importa
        #self.timestamp_ns = None   El tiempo se calcula
        #self.payload = None        El payload se importa a la función

    def packetize(self, nalu, nalu_type,priority) -> list[NALUPacket]:
        """
        Encargado de recibir un paquete grande de NALU y romperlo en NALUS pequeñas conservando su 
        sequencia con un paquete sencillo, dicho paquete es temporal y luego se recuperan los datos para el 
        final
        """
        nalu_list: list[NALUPacket] = []

        # Primero romper en una lista de fragmentos de nalu
        fragments = []
        for offset in range (0, len(nalu), SIZE_MAX_PACKET):
            fragment = nalu[offset:SIZE_MAX_PACKET + offset]
            fragments.append(fragment)

        # Calcular su tamaño
        fragment_count = len(fragments)

        # Asignar su id único y tiempo a cada nalu
        self.nalu_id += 1
        nalu_time = time.monotonic_ns()

        # Después, armar su paquete
        for fragment_index, fragment in enumerate(fragments):
            self.packet_sequence += 1
        
            #Armar paquete
            nalu_packet = NALUPacket(packet_sequence = self.packet_sequence, 
                                     nalu_id = self.nalu_id,
                                     fragment_index= fragment_index,
                                     fragment_count= fragment_count,
                                     nal_type= nalu_type,
                                     priority= priority,
                                     timestamp_ns = nalu_time,
                                     payload=fragment)
            
            nalu_list.append(nalu_packet)       

        return nalu_list


def update_flag(flag):
    """
    Su única misión es cambiar la bandera del paquete para indicar el inicio o paquete intermedio
    de uno segmentado
    """
    if flag == 0:
        return 1
    elif flag == 1:
        return 2
    else:
        return flag
    # Recordatorio:
    # Flag = 0 Es para paquete no segmentado
    # Flag = 1 Es para el inicio de un paquete segmentado
    # Flag = 2 Es para un paquete segmentado no final (uno en medio)
    # Flag = 3 Es para el final de un paquete segmentado
    # Flag = 4 Es para indicar el final de la transmisión