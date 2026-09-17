import unittest

try:
    import zmq
    HAVE_ZMQ = True
except ImportError:
    HAVE_ZMQ = False

from packets.packetizer import NALUPacket
from packets.priority_classifier import Priority
from packets.reassembler import Reassembler
from radio.pmt_codec import encode_u8vector_pdu, decode_pdu_data
from transport.datagram import build_datagram, parse_datagram
from radio.zmq_pdu_transport import ZMQPduTransport
from radio.zmq_pdu_receiver import ZMQPduReceiver

@unittest.skipUnless(HAVE_ZMQ, "pyzmq no instalado")
class TestZmqLoopback(unittest.TestCase):
    def test_tx_rx_loopback_inproc(self):
        context = zmq.Context()
        endpoint = "inproc://radiotest"
        rx = ZMQPduReceiver(endpoint=endpoint, context=context, connect=True, rcvtimeo_ms=1000)
        tx = ZMQPduTransport(endpoint=endpoint, context=context, bind=True)

        packet = NALUPacket(1, 7, 0, 2, 1, Priority.NORMAL, 0, b"XYZ")
        self.assertEqual(tx.send_packet(packet), 27)
        datagram = rx.recv_timeout()
        self.assertIsNotNone(datagram)
        header, payload = parse_datagram(datagram)
        self.assertEqual(header.nalu_id, 7)
        self.assertEqual(payload, b"XYZ")
        tx.close(); rx.close(); context.term()

    def test_loopback_reensamblado(self):
        context = zmq.Context()
        endpoint = "inproc://radiotest2"
        rx = ZMQPduReceiver(endpoint=endpoint, context=context, connect=True, rcvtimeo_ms=1000)
        tx = ZMQPduTransport(endpoint=endpoint, context=context, bind=True)
        for i, pl in enumerate([b"AA", b"BB"]):
            tx.send_packet(NALUPacket(1 + i, 5, i, 2, 1, Priority.NORMAL, 0, pl))
        r = Reassembler()
        out = []
        for _ in range(2):
            d = rx.recv_timeout()
            self.assertIsNotNone(d)
            h, p = parse_datagram(d)
            n = r.feed(h, p)
            if n is not None:
                out.append(n)
        self.assertEqual(out, [b"AABB"])
        tx.close(); rx.close(); context.term()

if __name__ == "__main__":
    unittest.main()