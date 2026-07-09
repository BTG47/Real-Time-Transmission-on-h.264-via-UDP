from dataclasses import dataclass
import struct
@dataclass
class SimpleRtp():
    sequence : int      # 4 bytes
    nal_type: int       # 1 byte
    flags: int          # 1 byte, flag = 1 fin de la segmentación de un nalu, flag = 2, fin del video, para rearmarlo
    payload_size: int   # 2 bytes

    def to_bytes(self):
        return struct.pack('!IBBH', 
                           self.sequence,
                           self.nal_type,
                           self.flags,
                           self.payload_size)
    @classmethod
    def from_byte(cls, data):
        # Obtención de datos binarios:
        sequence, nal_type, flags, payload = struct.unpack('!IBBH', data)

        return cls(sequence, nal_type, flags, payload)
    
