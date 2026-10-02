import unittest
from radio.pmt_codec import encode_u8vector_pdu, decode_pdu_data, PmtDecodeError

class TestPmtCodec(unittest.TestCase):
    def test_encode_vacio(self):
        self.assertEqual(encode_u8vector_pdu(b""),
                         b"\x07\x06\x0a\x00\x00\x00\x00\x00\x01\x00")

    def test_encode_1200_bytes(self):
        frame = encode_u8vector_pdu(b"Z" * 1200)
        self.assertEqual(frame[:10], b"\x07\x06\x0a\x00\x00\x00\x04\xb0\x01\x00")
        self.assertEqual(len(frame), 1210)

    def test_roundtrip(self):
        payload = b"\x00\x01\x02\x03" * 300
        self.assertEqual(decode_pdu_data(encode_u8vector_pdu(payload)), payload)

    def test_decode_con_metadatos(self):
        # cons(acons("x", 42, dict()), u8vector([1,2,3]))
        frame = bytes.fromhex("07090200017807030000002a060a00000000030" "100010203")
        self.assertEqual(decode_pdu_data(frame), b"\x01\x02\x03")

    def test_decode_truncado(self):
        with self.assertRaises(PmtDecodeError):
            decode_pdu_data(b"\x07\x06\x0a\x00\x00\x00\x00\x05\x01\x00")   # faltan 5 bytes

    def test_decode_tag_desconocido(self):
        with self.assertRaises(PmtDecodeError):
            decode_pdu_data(bytes([0x3b]))

    def test_decode_cdr_final_no_u8vector(self):
        frame = b"\x07\x06\x07\x03\x00\x00\x00\x2a\x06"      # (nil . (42 . nil)) sin blob
        with self.assertRaises(PmtDecodeError):
            decode_pdu_data(frame)

    def test_decode_sobras(self):
        with self.assertRaises(PmtDecodeError):
            decode_pdu_data(encode_u8vector_pdu(b"AB") + b"\x00")

    def test_decode_anidamiento_excesivo(self):
        with self.assertRaises(PmtDecodeError):
            decode_pdu_data(b"\x07" * 1000)

if __name__ == "__main__":
    unittest.main()