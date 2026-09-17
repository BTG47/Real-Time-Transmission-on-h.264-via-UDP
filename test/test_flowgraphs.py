import unittest
import glob
from xml.dom import minidom

class TestFlowgraphsWellFormed(unittest.TestCase):
    def test_grc_son_xml_valido(self):
        files = glob.glob("radio/flowgraphs/*.grc")
        self.assertGreater(len(files), 0)
        for f in files:
            minidom.parse(f)   # lanza si no es XML bien formado

if __name__ == "__main__":
    unittest.main()