import unittest
from packets.packetizer import NALUPacket
from packets.priority_classifier import Priority
from transport.video_header import VideoHeader
from transport.datagram import build_datagram, parse_datagram

def make_packet(payload: bytes, nalu_id=1, index=0, count=1, type_=5, priority=Priority.HIGH, seq=7, ts=0x1122334455667788):
    return NALUPacket(packet_sequence=seq, nalu_id=nalu_id, fragment_index=index,
                      fragment_count=count, nal_type=type_, priority=priority,
                      timestamp_ns=ts, payload=payload)

class TestDatagram(unittest.TestCase):
    def test_header_layout_is_24_bytes(self):
        header = VideoHeader(1, 2, 3, 4, 5, Priority.HIGH, 0x1122334455667788, 6)
        self.assertEqual(header.to_bytes(),
                         b"\x00\x00\x00\x01\x00\x00\x00\x02\x00\x03\x00\x04" +
                         b"\x05\x01\x11\x22\x33\x44\x55\x66\x77\x88\x00\x06")

    def test_roundtrip(self):
        payload = bytes(range(256)) * 4          # 1024 bytes
        datagram = build_datagram(make_packet(payload, nalu_id=42, index=2, count=5, type_=1))
        self.assertEqual(len(datagram), 1024 + 24)
        header, parsed = parse_datagram(datagram)
        self.assertEqual(header.nalu_id, 42)
        self.assertEqual(header.fragment_index, 2)
        self.assertEqual(header.fragment_count, 5)
        self.assertEqual(header.nal_type, 1)
        self.assertEqual(header.payload_size, 1024)
        self.assertEqual(parsed, payload)

    def test_max_payload_1176_ok(self):
        datagram = build_datagram(make_packet(b"x" * 1176))
        self.assertEqual(len(datagram), 1200)

    def test_oversized_raises(self):
        with self.assertRaises(ValueError):
            build_datagram(make_packet(b"x" * 1177))

    def test_parse_short_raises(self):
        with self.assertRaises(ValueError):
            parse_datagram(b"\x00" * 20)

if __name__ == "__main__":
    unittest.main()