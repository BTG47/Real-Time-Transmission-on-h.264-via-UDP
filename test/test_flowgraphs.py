import unittest
import glob
from xml.dom import minidom

import radio.config_radio as radio_config

FLOWGRAPHS_DIR = "radio/flowgraphs"


def _blocks_of(path):
    doc = minidom.parse(path)
    blocks = []
    for blk in doc.getElementsByTagName("block"):
        block_type = blk.getElementsByTagName("key")[0].firstChild.data
        params = {}
        for p in blk.getElementsByTagName("param"):
            key_el = p.getElementsByTagName("key")[0]
            val_el = p.getElementsByTagName("value")[0]
            value = val_el.firstChild.data if val_el.firstChild else ""
            params[key_el.firstChild.data] = value
        blocks.append({"type": block_type, "id": params.get("id"), "params": params})
    return blocks


def _connections_of(path):
    doc = minidom.parse(path)
    conns = []
    for c in doc.getElementsByTagName("connection"):
        def get(tag):
            el = c.getElementsByTagName(tag)[0]
            return el.firstChild.data if el.firstChild else ""
        conns.append((get("source_block_id"), get("source_key"),
                      get("sink_block_id"), get("sink_key")))
    return conns


class TestFlowgraphsWellFormed(unittest.TestCase):
    def test_grc_son_xml_valido(self):
        files = glob.glob(f"{FLOWGRAPHS_DIR}/*.grc")
        self.assertGreater(len(files), 0)
        for f in files:
            minidom.parse(f)   # lanza si no es XML bien formado


class TestBladeToBladePairing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tx = _blocks_of(f"{FLOWGRAPHS_DIR}/tx_bladerf.grc")
        cls.rx = _blocks_of(f"{FLOWGRAPHS_DIR}/rx_bladerf.grc")

    @staticmethod
    def _by_type(blocks, block_type):
        return [b for b in blocks if b["type"] == block_type]

    def test_existe_par_bladerf(self):
        self.assertTrue(
            self._by_type(self.tx, "bladerf_sink"),
            "tx_bladerf.grc debe usar el bloque gr-bladeRF bladerf_sink",
        )
        self.assertTrue(
            self._by_type(self.rx, "bladerf_source"),
            "rx_bladerf.grc debe usar el bloque gr-bladeRF bladerf_source",
        )

    def test_misma_frecuencia_y_sample_rate(self):
        tx_sink = self._by_type(self.tx, "bladerf_sink")[0]["params"]
        rx_src = self._by_type(self.rx, "bladerf_source")[0]["params"]
        self.assertEqual(tx_sink["sample_rate"], rx_src["sample_rate"])
        self.assertEqual(tx_sink["center_freq"], rx_src["center_freq"])
        self.assertEqual(tx_sink["center_freq"], "2.45e9")

    def test_gmsk_emparejado(self):
        mod = self._by_type(self.tx, "digital_gmsk_mod")[0]["params"]
        demod = self._by_type(self.rx, "digital_gmsk_demod")[0]["params"]
        self.assertEqual(mod["samples_per_symbol"], demod["samples_per_symbol"])
        self.assertEqual(mod["gain"], demod["gain"])
        self.assertEqual(mod["samples_per_symbol"], "8")

    def test_mismo_len_tag_y_tipo(self):
        tx_pdu = self._by_type(self.tx, "blks2_pdu_to_tagged_stream")[0]["params"]
        rx_pdu = self._by_type(self.rx, "blocks_tagged_stream_to_pdu")[0]["params"]
        self.assertEqual(tx_pdu["len_tag_key"], rx_pdu["len_tag_key"])
        self.assertEqual(tx_pdu["type"], rx_pdu["type"])
        self.assertEqual(tx_pdu["len_tag_key"], "packet_len")
        self.assertEqual(tx_pdu["type"], "byte")


class TestZmqEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tx = _blocks_of(f"{FLOWGRAPHS_DIR}/tx_bladerf.grc")
        cls.rx = _blocks_of(f"{FLOWGRAPHS_DIR}/rx_bladerf.grc")

    @staticmethod
    def _first(blocks, block_type):
        return [b for b in blocks if b["type"] == block_type][0]["params"]

    def test_tx_pull_connect_5555(self):
        pull = self._first(self.tx, "zeromq_pull_msg_source")
        self.assertEqual(pull["address"], radio_config.ZMQ_TX_ENDPOINT)
        self.assertEqual(pull["mode"], "connect")
        self.assertEqual(pull["address"], "tcp://127.0.0.1:5555")

    def test_rx_push_bind_5556(self):
        push = self._first(self.rx, "zeromq_push_msg_sink")
        self.assertEqual(push["address"], radio_config.ZMQ_RX_ENDPOINT)
        self.assertEqual(push["mode"], "bind")
        self.assertEqual(push["address"], "tcp://127.0.0.1:5556")

    def test_roles_bind_connect_par(self):
        # Convención: exactamente un bind por puerto.
        # 5555: Python TX hace bind (ZMQ_TX_BIND=True) -> flowgraph TX conecta.
        self.assertTrue(radio_config.ZMQ_TX_BIND)
        self.assertEqual(self._first(self.tx, "zeromq_pull_msg_source")["mode"], "connect")
        # 5556: flowgraph RX hace bind -> Python RX conecta (ZMQ_RX_CONNECT=True).
        self.assertTrue(radio_config.ZMQ_RX_CONNECT)
        self.assertEqual(self._first(self.rx, "zeromq_push_msg_sink")["mode"], "bind")


class TestGraphIntegrity(unittest.TestCase):
    def test_conexiones_referencian_bloques_existentes(self):
        files = glob.glob(f"{FLOWGRAPHS_DIR}/*.grc")
        self.assertGreater(len(files), 0)
        for f in files:
            blocks = _blocks_of(f)
            ids = [b["id"] for b in blocks]
            self.assertEqual(len(ids), len(set(ids)), f"IDs duplicados en {f}")
            id_set = set(ids)
            for src, _sk, dst, _dk in _connections_of(f):
                self.assertIn(src, id_set, f"{f}: source {src!r} no existe")
                self.assertIn(dst, id_set, f"{f}: sink {dst!r} no existe")


if __name__ == "__main__":
    unittest.main()