import unittest
from unittest import mock
from packets.packetizer import NALUPacket
from packets.priority_classifier import Priority
from radio.pmt_codec import encode_u8vector_pdu
from transport.datagram import build_datagram
from radio import zmq_pdu_transport
from radio.zmq_pdu_transport import ZMQPduTransport

class FakeSocket:
    def __init__(self):
        self.sent = []
        self.closed = False
    def send(self, frame):
        self.sent.append(frame)
        return len(frame)
    def bind(self, endpoint):
        self.bound = endpoint
    def close(self, linger=0):
        self.closed = True

class FakeContext:
    def __init__(self):
        self.sockets = []
    def socket(self, stype):
        s = FakeSocket()
        s.stype = stype
        self.sockets.append(s)
        return s

FAKE_ZMQ = mock.MagicMock()
FAKE_ZMQ.PUSH = 8

class TestZMQPduTransport(unittest.TestCase):
    def test_envia_frame_pdu_con_tam_correcto(self):
        fake = FakeSocket()
        t = ZMQPduTransport(socket=fake, context=FakeContext())
        packet = NALUPacket(1, nalu_id=1, fragment_index=0, fragment_count=1,
                            nal_type=5, priority=Priority.HIGH, timestamp_ns=0,
                            payload=b"\x01\x02\x03")
        sent = t.send_packet(packet)
        self.assertEqual(sent, 27)                                  # 24 header + 3 payload
        self.assertEqual(fake.sent[0], encode_u8vector_pdu(build_datagram(packet)))

    def test_datagrama_demasiado_grande_levanta(self):
        fake = FakeSocket()
        t = ZMQPduTransport(socket=fake, context=FakeContext())
        packet = NALUPacket(1, 1, 0, 1, 5, Priority.HIGH, 0, b"x" * 1177)
        with self.assertRaises(ValueError):
            t.send_packet(packet)
        self.assertEqual(fake.sent, [])

    def test_close_cierra_socket(self):
        fake = FakeSocket()
        t = ZMQPduTransport(socket=fake, context=FakeContext())
        t.close()
        self.assertTrue(fake.closed)

    def test_fabrica_socket_push_bind_sin_inyeccion(self):
        with mock.patch.object(zmq_pdu_transport, "zmq", FAKE_ZMQ), \
             mock.patch.object(zmq_pdu_transport, "ZMQ_TX_ENDPOINT", "tcp://127.0.0.1:5555"):
            ctx = FakeContext()
            FAKE_ZMQ.Context.return_value = ctx
            t = ZMQPduTransport()
            self.assertEqual(t._socket.stype, 8)                    # PUSH
            self.assertEqual(t._socket.bound, "tcp://127.0.0.1:5555")
            self.assertTrue(t._socket is not None)

if __name__ == "__main__":
    unittest.main()