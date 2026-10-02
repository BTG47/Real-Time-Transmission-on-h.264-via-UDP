import unittest
from unittest import mock
from transport.udp_transport import UdpTransport
from transport.transport_factory import get_transport

class TestTransportFactory(unittest.TestCase):
    def test_udp_por_defecto(self):
        with mock.patch("config.TRANSPORT", "udp"):
            self.assertIsInstance(get_transport(), UdpTransport)

    def test_radio_devuelve_zmq(self):
        fake_zmq = mock.MagicMock()
        fake_zmq.PUSH = 8
        with mock.patch("radio.zmq_pdu_transport.zmq", fake_zmq), \
             mock.patch("config.TRANSPORT", "radio"):
            from radio.zmq_pdu_transport import ZMQPduTransport
            self.assertIsInstance(get_transport(), ZMQPduTransport)

    def test_radio_sin_pyzmq_levanta_error_claro(self):
        import transport.transport_factory as tf
        real_import = __import__
        def broken_import(name, *a, **k):
            if name == "radio.zmq_pdu_transport":
                raise ImportError("No module named 'zmq'")
            return real_import(name, *a, **k)
        with mock.patch("builtins.__import__", side_effect=broken_import), \
             mock.patch("config.TRANSPORT", "radio"):
            with self.assertRaises(RuntimeError):
                get_transport()

if __name__ == "__main__":
    unittest.main()