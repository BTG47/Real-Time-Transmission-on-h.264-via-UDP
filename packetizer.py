from dataclasses import dataclass
from simple_rtp_header import SimpleRtp
from config import SIZE_MAX_PACKET

@dataclass
class NALUPacket:
    payload: bytes
    sequence: int
    nal_type: int
    flag: int
    size: int


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

def packetize(nalu, nal_type, flag, actual_sequence, payload_size, priority):
    """
    Encargado de recibir un paquete grande de NALU y romperlo en NALUS pequeñas conservando su 
    sequencia con un paquete sencillo, dicho paquete es temporal y luego se recuperan los datos para el 
    final
    """
    nalu_list: list[NALUPacket] = []
    #print(f"Seq actual {actual_sequence}")
    isTheLastSegmentedPacket = actual_sequence > 0 and flag != 0 and flag !=4

    # Primero romper en una lista de fragmentos de nalu
    fragments = []
    for offset in range (0, len(nalu), SIZE_MAX_PACKET):
        fragment = nalu[offset:SIZE_MAX_PACKET + offset]
        fragments.append(fragment)

    # Después, obtener su flag y sequence dependiendo de su posición
    for idx, fragment in enumerate(fragments):
        if (flag == 4):
            flag = 4
        elif (idx + 1) == len (fragments):
            flag = 3
        elif idx > 0:
            flag = 2
        elif idx == 0:
            flag = 1
        sequence = idx
        packet_size = len(fragment)
        nalu_packet = NALUPacket(payload=fragment, sequence=sequence, nal_type=nal_type, flag=flag, size = packet_size)
        nalu_list.append(nalu_packet)

    return nalu_list