import csv,gzip,tempfile,unittest
from pathlib import Path
from save_editor import Document
from save_diff import differences,export_csv
BASE=Path(__file__).resolve().parent
class DiffTests(unittest.TestCase):
    def compare(self,a,b,ignore=False):
        with tempfile.TemporaryDirectory(dir=BASE) as folder:
            p,q=Path(folder)/'a.json',Path(folder)/'b.json'
            p.write_bytes(gzip.compress(a.encode('utf-8-sig')));q.write_text(b,encoding='utf-8')
            return differences(Document(p),Document(q),ignore)
    def test_semantics(self):
        self.assertEqual(self.compare('{"a":1,"b":"x"}','{ "b":"\\u0078", "a":1.0 }'),[])
        self.assertEqual(self.compare('true','1')[0][1],'Type changed')
        self.assertEqual(self.compare('[]','{}')[0][1],'Type changed')
    def test_paths_and_structure(self):
        rows=self.compare('{"a/b":1,"~":null,"list":[1,2],"old":{}}','{"a/b":2,"~":"null","list":[1],"new":{"x":1}}')
        self.assertEqual([(r[0],r[1]) for r in rows],[('/a~1b','Changed'),('/~0','Type changed'),('/list/1','Removed'),('/old','Removed'),('/new','Added')])
        self.assertEqual(rows[-1][2:],(None,'{"x":1}'))
    def test_precision_and_references(self):
        a='{"$id":"1","$ref":"2","v":1.234567890123456789}'
        b='{"$id":"9","$ref":"8","v":1.234567890123456788}'
        self.assertEqual(len(self.compare(a,b)),3)
        rows=self.compare(a,b,True);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][2],'1.234567890123456789')
    def test_csv(self):
        with tempfile.TemporaryDirectory(dir=BASE) as folder:
            p=Path(folder)/'diff.csv';export_csv(p,[('/x','Added',None,'null'),('/y','Changed','"a,b"','"line\\nend"')])
            with p.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.reader(f))
            self.assertEqual(rows[1],['/x','Added','<missing>','null']);self.assertEqual(rows[2][2],'"a,b"')
    def test_real_saves(self):
        folders=sorted(p for p in BASE.parent.iterdir() if (p/'GameData.json').is_file())
        docs=[Document(p/'GameData.json') for p in folders]
        if len(docs)<2: self.skipTest('Optional local game saves are not present')
        self.assertEqual(differences(docs[0],docs[0]),[])
        copied=[d for d in docs if d.path.parent.name.startswith('baa')]
        if len(copied)==2: self.assertEqual(differences(*copied),[])
        self.assertGreater(len(differences(docs[0],docs[1])),0)
        for d in docs:self.assertEqual(d.path.read_bytes(),d.original)
if __name__=='__main__':unittest.main()
