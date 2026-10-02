import unittest
from packets.reassembler import Reassembler
from transport.video_header import VideoHeader
from packets.priority_classifier import Priority

def hdr(nalu_id, index, count, payload_size, seq=1, nal_type=1, priority=Priority.NORMAL):
    return VideoHeader(seq, nalu_id, index, count, nal_type, priority, 0, payload_size)

F0, F1, F2 = b"AAA", b"BBB", b"CCC"

def payload_for(nalu_id, index):
    base = 65 + nalu_id
    return bytes([base, base + 1, base + 2])   # 3 bytes, contenido distinguible por nalu id

class TestReassembler(unittest.TestCase):
    def test_caso_A_orden_normal(self):
        r = Reassembler()
        self.assertIsNone(r.feed(hdr(10, 0, 3, 3), bytes([0]) * 3))
        self.assertIsNone(r.feed(hdr(10, 1, 3, 3), bytes([1]) * 3))
        full = r.feed(hdr(10, 2, 3, 3), bytes([2]) * 3)     # tercer fragmento completa la NALU
        self.assertEqual(full, bytes([0]) * 3 + bytes([1]) * 3 + bytes([2]) * 3)
        self.assertIsNone(r.feed(hdr(10, 0, 3, 3), b"\x00" * 3))   # recrea pendiente {0}, no completa
        self.assertEqual(r.pending_count, 1)

    def test_caso_A_reconstruye_orden(self):
        r = Reassembler()
        for i in range(3):
            r.feed(hdr(10, i, 3, 3), F0 if i == 0 else (F1 if i == 1 else F2))
        self.assertEqual(r.pending_count, 0)   # 0,1,2 en orden reconstruyen y limpian

    def test_caso_B_desordenados(self):
        r = Reassembler()
        self.assertIsNone(r.feed(hdr(10, 2, 3, 3), payload_for(10, 2)))
        self.assertIsNone(r.feed(hdr(10, 0, 3, 3), payload_for(10, 0)))
        result = r.feed(hdr(10, 1, 3, 3), payload_for(10, 1))
        self.assertEqual(result, payload_for(10, 0) + payload_for(10, 1) + payload_for(10, 2))

    def test_caso_C_intercaladas_no_mezcla(self):
        r = Reassembler()
        r.feed(hdr(10, 0, 2, 3), payload_for(10, 0))
        self.assertIsNone(r.feed(hdr(11, 0, 2, 3), payload_for(11, 0)))
        result10 = r.feed(hdr(10, 1, 2, 3), payload_for(10, 1))
        self.assertEqual(result10, payload_for(10, 0) + payload_for(10, 1))   # 10 no se mezcla con 11
        result11 = r.feed(hdr(11, 1, 2, 3), payload_for(11, 1))
        self.assertEqual(result11, payload_for(11, 0) + payload_for(11, 1))
        self.assertEqual(r.pending_count, 0)

    def test_caso_D_duplicado_no_duplica(self):
        r = Reassembler()
        r.feed(hdr(10, 0, 2, 3), payload_for(10, 0))
        r.feed(hdr(10, 0, 2, 3), payload_for(10, 0))   # duplicado no duplica
        result = r.feed(hdr(10, 1, 2, 3), payload_for(10, 1))
        self.assertEqual(result, payload_for(10, 0) + payload_for(10, 1))
        self.assertEqual(r.pending_count, 0)

    def test_caso_E_fragmento_perdido_queda_pendiente(self):
        r = Reassembler()
        r.feed(hdr(10, 0, 3, 3), F0)
        r.feed(hdr(10, 2, 3, 3), F2)
        self.assertEqual(r.pending_count, 1)

    def test_caso_F_nalu_posterior_completa_antes(self):
        r = Reassembler()
        r.feed(hdr(10, 0, 2, 3), F0)
        self.assertIsNone(r.feed(hdr(11, 0, 2, 3), F0))
        self.assertEqual(r.feed(hdr(11, 1, 2, 3), F1), F0 + F1)   # 11 completa primero
        self.assertEqual(r.feed(hdr(10, 1, 2, 3), F1), F0 + F1)   # 10 completa al llegar su último fragmento
        self.assertEqual(r.pending_count, 0)

    def test_validacion_count_menor_igual_cero(self):
        r = Reassembler()
        self.assertIsNone(r.feed(hdr(1, 0, 0, 3), F0))
        self.assertEqual(r.pending_count, 0)

    def test_validacion_index_fuera_de_rango(self):
        r = Reassembler()
        self.assertIsNone(r.feed(hdr(1, 3, 2, 3), F0))
        self.assertEqual(r.pending_count, 0)

    def test_validacion_payload_size_incorrecto(self):
        r = Reassembler()
        self.assertIsNone(r.feed(hdr(1, 0, 1, 99), F0))   # declara 99 bytes, llegan 3
        self.assertEqual(r.pending_count, 0)

    def test_validacion_fragment_count_inconsistente(self):
        r = Reassembler()
        r.feed(hdr(10, 0, 2, 3), F0)
        self.assertIsNone(r.feed(hdr(10, 1, 3, 3), F1))   # mismo id pero count 3 != 2
        self.assertEqual(r.pending_count, 1)

if __name__ == "__main__":
    unittest.main()