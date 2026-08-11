from dataclasses import dataclass
from priority_classifier import Priority
import struct
@dataclass
class VideoHeader():
    packet_sequence: int    # 4 bytes
    nalu_id: int            # 4 bytes
    fragment_index: int     # 2 bytes
    fragment_count: int     # 2 bytes
    nal_type: int           # 1 byte
    priority: Priority      # 1 byte
    timestamp_ns: int       # 8 bytes
    payload_size: int     # 2 bytes

    def to_bytes(self):
        return struct.pack('!IIHHBBQH', 
                            self.packet_sequence, 
                            self.nalu_id,
                            self.fragment_index,
                            self.fragment_count,
                            self.nal_type,
                            self.priority,
                            self.timestamp_ns,
                            self.payload_size
                           )
    @classmethod
    def from_byte(cls, data):
        # Obtención de datos binarios:
        packet_sequence, nalu_id, fragment_index, fragment_count, nal_type, priority, timestamp_ns, payload_size = struct.unpack('!IIHHBBQH', data)
        return cls(packet_sequence, nalu_id, fragment_index, fragment_count, nal_type, priority, timestamp_ns, payload_size)
    
