import unittest
import subprocess
import sys

class TestRecieverRadioSmoke(unittest.TestCase):
    def test_modulo_importa_y_compila(self):
        result = subprocess.run([sys.executable, "-m", "py_compile", "radio/reciever_radio.py"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        import radio.reciever_radio  # noqa: F401

if __name__ == "__main__":
    unittest.main()