from config import UDP_SAFE_PAYLOAD, REAL_HEADER_SIZE
from packets.packetizer import NALUPacket
from transport.video_header import VideoHeader

def build_datagram(packet: NALUPacket) -> bytes:
    header = VideoHeader(packet.packet_sequence, packet.nalu_id, packet.fragment_index,
                         packet.fragment_count, packet.nal_type, packet.priority,
                         packet.timestamp_ns, len(packet.payload))
    data = header.to_bytes() + packet.payload
    if len(data) > UDP_SAFE_PAYLOAD:
        raise ValueError(f"Datagrama demasiado grande: {len(data)} bytes "
                         f"(header={len(header.to_bytes())}, payload={len(packet.payload)})")
    return data

def parse_datagram(data: bytes) -> tuple[VideoHeader, bytes]:
    if len(data) < REAL_HEADER_SIZE:
        raise ValueError(f"Datagrama demasiado corto: {len(data)} bytes")
    header = VideoHeader.from_byte(data[:REAL_HEADER_SIZE])
    return header, data[REAL_HEADER_SIZE:]