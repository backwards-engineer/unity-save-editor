"""Run from SaveEditor: python test_editor.py. Originals are read only."""
import tempfile, unittest, gzip
from pathlib import Path
from save_editor import Document, leaves, parse
BASE = Path(__file__).resolve().parent
class EditorTests(unittest.TestCase):
    def test_all_supplied_files(self):
        for p in BASE.parent.glob('*/Game*.json*'):
            with self.subTest(file=str(p)):
                d = Document(p)
                self.assertEqual(d.text.encode('utf-8-sig'),gzip.decompress(p.read_bytes()))
                self.assertIsNone(d.save())
    def test_edit_and_backup(self):
        with tempfile.TemporaryDirectory(dir=BASE) as t:
            p = Path(t)/'save.json'
            raw = b'\xef\xbb\xbf'+b'{"$id":"1","Coins":600,"precise":1.234567890123456789,"array":[true,null,"a\\\"b"]}'
            original = gzip.compress(raw); p.write_bytes(original); d = Document(p)
            n = next(n for n in leaves(d.root) if n.path == '/Coins')
            before = d.text; d.replace(n,'9999')
            self.assertEqual(d.text,before[:n.start]+'9999'+before[n.end:])
            backup = d.save(); self.assertEqual(backup.read_bytes(),original)
            self.assertEqual(Document(p).text,d.text)
            n = next(n for n in leaves(d.root) if n.path == '/$id')
            with self.assertRaises(ValueError): d.replace(n,'"2"')
            p.write_bytes(b'external change')
            with self.assertRaises(ValueError): d.save()
    def test_invalid(self):
        for s in ['{} garbage','{"x":NaN}','{"a":1,}']:
            with self.assertRaises(ValueError): parse(s)
if __name__ == '__main__': unittest.main()
