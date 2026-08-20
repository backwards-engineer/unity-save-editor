"""Lossless gzip/JSON save editor. Python standard library only."""
import gzip, json, os, re, shutil, tempfile
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass, field

DECODER = json.JSONDecoder(parse_float=Decimal, parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
@dataclass
class Node:
    path: str
    start: int
    end: int = 0
    children: list = field(default_factory=list)

def parse(text):
    # Validate the full document before indexing token locations.
    DECODER.decode(text)
    def ws(i):
        while i < len(text) and text[i] in ' \t\r\n': i += 1
        return i
    def value(i, path):
        i = ws(i); n = Node(path, i)
        if text[i] in '{[':
            obj = text[i] == '{'; close = '}' if obj else ']'; i = ws(i+1); index = 0
            while text[i] != close:
                if obj:
                    key, i = DECODER.raw_decode(text, i); i = ws(i)+1
                else: key = str(index)
                child, i = value(i, path+'/'+str(key).replace('~','~0').replace('/','~1'))
                n.children.append(child); index += 1; i = ws(i)
                if text[i] == ',': i = ws(i+1)
            n.end = i+1
        else:
            _, n.end = DECODER.raw_decode(text, i)
        return n, n.end
    return value(0, '')[0]

class Document:
    def __init__(self, path):
        self.path = Path(path); self.original = self.path.read_bytes()
        self.compressed = self.original.startswith(b'\x1f\x8b')
        raw = gzip.decompress(self.original) if self.compressed else self.original
        self.bom = raw.startswith(b'\xef\xbb\xbf')
        self.text = raw.decode('utf-8-sig'); self.initial = self.text; self.root = parse(self.text)
    def replace(self, node, replacement):
        replacement = replacement.strip(); DECODER.decode(replacement)
        old = DECODER.decode(self.text[node.start:node.end]); new = DECODER.decode(replacement)
        if isinstance(new,(dict,list)) or type(new) is not type(old):
            raise ValueError('Keep the original value type; use JSON import for structural changes.')
        if node.path.rsplit('/',1)[-1] in ('$id','$ref'):
            raise ValueError('$id and $ref are protected serialization references.')
        self.text = self.text[:node.start]+replacement+self.text[node.end:]; self.root = parse(self.text)
    def save(self):
        parse(self.text)
        if self.path.read_bytes() != self.original: raise ValueError('File changed outside the editor. Reopen it before saving.')
        if self.text == self.initial: return None
        raw = (b'\xef\xbb\xbf' if self.bom else b'')+self.text.encode('utf-8')
        packed = gzip.compress(raw, mtime=0) if self.compressed else raw
        if (gzip.decompress(packed) if self.compressed else packed) != raw: raise ValueError('Compression verification failed')
        backup = self.path.with_name(self.path.name+'.editor-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        shutil.copy2(self.path, backup)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix='.editor-', suffix='.tmp')
        try:
            with os.fdopen(fd,'wb') as f: f.write(packed); f.flush(); os.fsync(f.fileno())
            if self.path.read_bytes() != self.original: raise ValueError('File changed during save')
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        self.original = packed; self.initial = self.text
        return backup

def leaves(n):
    if n.children:
        for c in n.children: yield from leaves(c)
    else: yield n

def gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root = tk.Tk(); root.title('Moonlight Peaks Save Editor'); root.geometry('1100x740')
    doc = None; nodes = {}; selected = None
    status = tk.StringVar(value='Open GameData.json or GameMetaData.json. Close the game before saving.')
    query = tk.StringVar(); edit = tk.StringVar()
    def guard(fn):
        def run():
            try: fn()
            except Exception as e: messagebox.showerror('Save editor',str(e))
        return run
    def discard():
        return not doc or doc.text == doc.initial or messagebox.askyesno('Unsaved changes','Discard unsaved changes?')
    def add(parent,n,label):
        item = tree.insert(parent,'end',text=label,values=('object / array' if n.children else doc.text[n.start:n.end][:300],))
        nodes[item] = n
        if n.children: tree.insert(item,'end',text='Loading…')
    def refresh():
        nonlocal selected
        tree.delete(*tree.get_children()); nodes.clear(); selected = None
        if doc:
            for n in doc.root.children: add('',n,n.path[1:])
            status.set(str(doc.path)+(' • UNSAVED' if doc.text != doc.initial else ''))
    def opening():
        nonlocal doc
        if not discard(): return
        p = filedialog.askopenfilename(initialdir=Path(__file__).resolve().parent.parent,title='Open compressed save',filetypes=[('Save files','*.json *.bak *.lastsuccessful'),('All files','*')])
        if p: doc = Document(p); refresh()
    def expand(event):
        item = tree.focus(); n = nodes.get(item)
        children = tree.get_children(item)
        if n and children and children[0] not in nodes:
            tree.delete(*children)
            for c in n.children: add(item,c,c.path.rsplit('/',1)[-1])
    def select(event):
        nonlocal selected
        ids = tree.selection(); selected = nodes.get(ids[0]) if ids else None
        if selected:
            pathlabel.set(selected.path)
            edit.set(doc.text[selected.start:selected.end] if not selected.children else '')
    def search():
        if not doc: return
        if not query.get().strip(): refresh(); return
        tree.delete(*tree.get_children()); nodes.clear(); count = 0; term = query.get().casefold()
        for n in leaves(doc.root):
            if term in n.path.casefold() or term in doc.text[n.start:n.end].casefold():
                count += 1
                if count <= 1000: add('',n,n.path)
        status.set(f'{count} matches; showing first 1000. Clear search to browse.')
    def apply():
        if not selected or selected.children: raise ValueError('Select a scalar value first.')
        doc.replace(selected,edit.get()); refresh()
        if query.get().strip(): search()
    def save():
        if not doc: return
        backup = doc.save(); refresh()
        messagebox.showinfo('Saved',f'Backup: {backup}' if backup else 'No changes to save.')
    def export():
        if not doc: return
        p = filedialog.asksaveasfilename(defaultextension='.json',initialfile=doc.path.stem+'.decoded.json')
        if p:
            if Path(p).resolve() == doc.path.resolve(): raise ValueError('Choose a separate export file.')
            Path(p).write_bytes(doc.text.encode('utf-8'))
    def importing():
        if not doc: return
        p = filedialog.askopenfilename(title='Import edited UTF-8 JSON')
        if p:
            text = Path(p).read_text(encoding='utf-8-sig'); parsed = parse(text)
            doc.text = text; doc.root = parsed; refresh()
    bar = ttk.Frame(root,padding=10); bar.pack(fill='x')
    for label,fn in [('Open save',opening),('Save + backup',save),('Export JSON',export),('Import JSON',importing)]: ttk.Button(bar,text=label,command=guard(fn)).pack(side='left',padx=4)
    ttk.Label(root,text='Close Moonlight Peaks before saving. Edit GameData for gameplay; metadata holds menu summaries.',padding=8).pack(anchor='w')
    sb = ttk.Frame(root,padding=8); sb.pack(fill='x')
    ttk.Entry(sb,textvariable=query).pack(side='left',fill='x',expand=True)
    ttk.Button(sb,text='Search paths / values',command=guard(search)).pack(side='left')
    ttk.Button(sb,text='Browse all',command=refresh).pack(side='left')
    frame = ttk.Frame(root); frame.pack(fill='both',expand=True,padx=10)
    tree = ttk.Treeview(frame,columns=('value',),selectmode='browse'); tree.heading('#0',text='Field / JSON pointer'); tree.heading('value',text='Value'); tree.column('#0',width=580); tree.column('value',width=440)
    scroll = ttk.Scrollbar(frame,orient='vertical',command=tree.yview); tree.configure(yscrollcommand=scroll.set)
    tree.pack(side='left',fill='both',expand=True); scroll.pack(side='right',fill='y')
    tree.bind('<<TreeviewOpen>>',expand); tree.bind('<<TreeviewSelect>>',select)
    pathlabel = tk.StringVar(value='Select a field. Strings need quotes; booleans use true / false.')
    ttk.Label(root,textvariable=pathlabel,wraplength=1050,padding=8).pack(anchor='w')
    eb = ttk.Frame(root,padding=8); eb.pack(fill='x'); ttk.Entry(eb,textvariable=edit).pack(side='left',fill='x',expand=True); ttk.Button(eb,text='Apply value',command=guard(apply)).pack(side='left')
    ttk.Label(root,textvariable=status,wraplength=1050,padding=8).pack(anchor='w')
    root.protocol('WM_DELETE_WINDOW',lambda: root.destroy() if discard() else None)
    root.mainloop()

if __name__ == '__main__': gui()
