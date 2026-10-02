import unittest
from radio.config_radio import ZMQ_TX_ENDPOINT, ZMQ_RX_ENDPOINT, ZMQ_TX_BIND, ZMQ_RX_CONNECT

class TestRadioConfig(unittest.TestCase):
    def test_endpoints_por_especificacion(self):
        self.assertEqual(ZMQ_TX_ENDPOINT, "tcp://127.0.0.1:5555")
        self.assertEqual(ZMQ_RX_ENDPOINT, "tcp://127.0.0.1:5556")

    def test_roles_bind_connect(self):
        self.assertTrue(ZMQ_TX_BIND)      # Python TX hace bind (PUSH)
        self.assertTrue(ZMQ_RX_CONNECT)   # Python RX hace connect (PULL)

if __name__ == "__main__":
    unittest.main()