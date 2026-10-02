import unittest
from unittest import mock
from packets.reassembler import Reassembler
from packets.priority_classifier import Priority
from radio.pmt_codec import encode_u8vector_pdu
from transport.datagram import build_datagram
from packets.packetizer import NALUPacket
from radio import zmq_pdu_receiver
from radio.zmq_pdu_receiver import ZMQPduReceiver, run_recv_loop

class FakePuller:
    def __init__(self, frames):
        self.frames = list(frames)
        self.closed = False
    def recv(self):
        if self.frames:
            return self.frames.pop(0)
        raise zmq_pdu_receiver.TIMEOUT_EXCEPTION()
    def close(self, linger=0):
        self.closed = True

def datagram(payload, index=0, count=1, nalu_id=10, seq=1):
    return build_datagram(NALUPacket(packet_sequence=seq, nalu_id=nalu_id,
                                     fragment_index=index, fragment_count=count,
                                     nal_type=1, priority=Priority.NORMAL,
                                     timestamp_ns=0, payload=payload))

class TestZMQPduReceiver(unittest.TestCase):
    def test_recv_timeout_devuelve_datagrama(self):
        rx = ZMQPduReceiver(socket=FakePuller([encode_u8vector_pdu(datagram(b"abc"))]), context=mock.MagicMock())
        self.assertEqual(rx.recv_timeout(), datagram(b"abc"))

    def test_recv_timeout_timeout_devuelve_none(self):
        rx = ZMQPduReceiver(socket=FakePuller([]), context=mock.MagicMock())
        self.assertIsNone(rx.recv_timeout())

    def test_run_recv_loop_reensambla(self):
        frames = [encode_u8vector_pdu(datagram(b"AAA", index=0, count=2)),
                  encode_u8vector_pdu(datagram(b"BBB", index=1, count=2))]
        rx = ZMQPduReceiver(socket=FakePuller(frames), context=mock.MagicMock())
        out = []
        def on_nalu(n):
            out.append(n)
        def on_timeout():
            return True
        run_recv_loop(rx, Reassembler(), on_nalu, on_timeout)
        self.assertEqual(out, [b"AAABBB"])

    def test_close(self):
        fake = FakePuller([])
        rx = ZMQPduReceiver(socket=fake, context=mock.MagicMock())
        rx.close()
        self.assertTrue(fake.closed)

if __name__ == "__main__":
    unittest.main()