"""Read-only structural comparison of gzip or plain JSON saves."""
import csv
from decimal import Decimal
from pathlib import Path
from save_editor import Document, DECODER


def differences(left, right, ignore_ids=False):
    """Compare objects by key, arrays by index; preserve exact value tokens in output."""
    rows = []
    def raw(doc, node):
        return None if node is None else doc.text[node.start:node.end]
    def kind(doc, node):
        first = doc.text[node.start]
        if first == '{': return 'object'
        if first == '[': return 'array'
        v = DECODER.decode(raw(doc,node))
        if isinstance(v, bool): return 'boolean'
        if isinstance(v, (int,Decimal)): return 'number'
        return type(v).__name__
    def visit(a,b):
        path = (a if a is not None else b).path
        if ignore_ids and path.rsplit('/',1)[-1] in ('$id','$ref'): return
        if a is None or b is None:
            rows.append((path,'Added' if a is None else 'Removed',raw(left,a),raw(right,b))); return
        ka,kb = kind(left,a),kind(right,b)
        if ka != kb:
            rows.append((path,'Type changed',raw(left,a),raw(right,b))); return
        if ka in ('object','array'):
            aa = {n.path:n for n in a.children}; bb = {n.path:n for n in b.children}
            for p in aa: visit(aa[p],bb.get(p))
            for p in bb:
                if p not in aa: visit(None,bb[p])
        elif DECODER.decode(raw(left,a)) != DECODER.decode(raw(right,b)):
            rows.append((path,'Changed',raw(left,a),raw(right,b)))
    visit(left.root,right.root)
    return rows


def export_csv(path, rows):
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        writer = csv.writer(f); writer.writerow(['JSON pointer','Change','Save A (JSON)','Save B (JSON)'])
        writer.writerows((p,s,'<missing>' if a is None else a,'<missing>' if b is None else b) for p,s,a,b in rows)


def gui(demo=False):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root = tk.Tk(); root.title('Moonlight Peaks Save Diff'); root.geometry('1250x820')
    docs = [None,None]; paths = [tk.StringVar(),tk.StringVar()]; rows = []; visible = []; page = 0
    query = tk.StringVar(); change = tk.StringVar(value='All'); ignore = tk.BooleanVar(value=False)
    status = tk.StringVar(value='Choose two saves. Comparison never writes to either save.')
    base = Path(__file__).resolve().parent.parent
    def guard(fn):
        def run(*args):
            try: return fn(*args)
            except Exception as e: messagebox.showerror('Save Diff',str(e))
        return run
    def load(i,folder=False):
        p = filedialog.askdirectory(initialdir=base,title=f'Choose save {"AB"[i]} folder') if folder else filedialog.askopenfilename(initialdir=base,title=f'Choose save {"AB"[i]}',filetypes=[('Save files','*.json *.bak *.lastsuccessful'),('All files','*')])
        if not p: return
        if folder: p = str(Path(p)/'GameData.json')
        d = Document(p); docs[i] = d; paths[i].set(str(d.path)); compare()
    def compare():
        nonlocal rows
        if all(docs):
            root.config(cursor='watch'); root.update_idletasks()
            try: rows = differences(*docs,ignore_ids=ignore.get())
            finally: root.config(cursor='')
            filter_rows()
    def filter_rows(*args):
        nonlocal visible,page
        term = query.get().casefold(); state = change.get()
        visible = [r for r in rows if (state == 'All' or r[1] == state) and (not term or any(term in str(v).casefold() for v in r))]
        page = 0; render()
    def render():
        tree.delete(*tree.get_children()); detail_a.delete('1.0','end'); detail_b.delete('1.0','end')
        for index in range(page*1000,min((page+1)*1000,len(visible))):
            p,s,a,b = visible[index]
            preview = lambda v: '<missing>' if v is None else v.replace('\n',' ')[:240]
            tree.insert('','end',iid=str(index),values=(s,p or '/',preview(a),preview(b)))
        counts = {s:sum(r[1] == s for r in rows) for s in ('Changed','Added','Removed','Type changed')}
        status.set(f'{len(rows):,} differences — '+', '.join(f'{v:,} {k.lower()}' for k,v in counts.items())+f' | {len(visible):,} filtered | Page {page+1} / {max(1,(len(visible)+999)//1000)}')
    def turn(delta):
        nonlocal page
        page = max(0,min(max(0,(len(visible)-1)//1000),page+delta)); render()
    def select(event):
        selection = tree.selection()
        if selection:
            p,s,a,b = visible[int(selection[0])]
            for widget,value in ((detail_a,a),(detail_b,b)):
                widget.delete('1.0','end'); widget.insert('1.0','<missing>' if value is None else value)
    def export():
        if not all(docs): return
        p = filedialog.asksaveasfilename(title='Export filtered differences',defaultextension='.csv',initialfile='save-diff.csv')
        if p:
            if Path(p).resolve() in [d.path.resolve() for d in docs]: raise ValueError('Choose an export file different from the source saves.')
            export_csv(p,visible); messagebox.showinfo('Exported',f'Exported {len(visible):,} differences.')
    ttk.Label(root,text='Compare two Moonlight Peaks saves',font=('Segoe UI',16,'bold'),padding=10).pack(anchor='w')
    for i in range(2):
        bar = ttk.Frame(root,padding=6); bar.pack(fill='x')
        ttk.Label(bar,text=f'Save {"AB"[i]}',width=8).pack(side='left')
        ttk.Entry(bar,textvariable=paths[i],state='readonly').pack(side='left',fill='x',expand=True)
        ttk.Button(bar,text='Choose file',command=guard(lambda i=i:load(i))).pack(side='left',padx=4)
        ttk.Button(bar,text='Choose folder',command=guard(lambda i=i:load(i,True))).pack(side='left')
    ttk.Label(root,text='Objects match by key; arrays match by index. Added/removed containers appear as one row. Folder selection opens GameData.json.',padding=6).pack(anchor='w')
    bar = ttk.Frame(root,padding=6); bar.pack(fill='x')
    ttk.Label(bar,text='Search').pack(side='left'); entry = ttk.Entry(bar,textvariable=query); entry.pack(side='left',fill='x',expand=True,padx=6)
    box = ttk.Combobox(bar,textvariable=change,state='readonly',values=['All','Changed','Added','Removed','Type changed'],width=15); box.pack(side='left')
    ttk.Checkbutton(bar,text='Ignore $id / $ref fields',variable=ignore,command=guard(compare)).pack(side='left',padx=8)
    ttk.Button(bar,text='Export filtered CSV',command=guard(export)).pack(side='left')
    ttk.Label(root,text='Ignoring reference fields can hide real reference changes. GUID values remain included.',padding=6).pack(anchor='w')
    frame = ttk.Frame(root,padding=6); frame.pack(fill='both',expand=True)
    tree = ttk.Treeview(frame,columns=('status','path','a','b'),show='headings',selectmode='browse')
    for name,label,width in [('status','Change',100),('path','JSON pointer',500),('a','Save A',280),('b','Save B',280)]:
        tree.heading(name,text=label); tree.column(name,width=width,minwidth=80)
    sy = ttk.Scrollbar(frame,command=tree.yview); sx = ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
    tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set); tree.grid(row=0,column=0,sticky='nsew'); sy.grid(row=0,column=1,sticky='ns'); sx.grid(row=1,column=0,sticky='ew'); frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
    tree.bind('<<TreeviewSelect>>',select)
    nav = ttk.Frame(root,padding=6); nav.pack(fill='x')
    ttk.Button(nav,text='Previous page',command=lambda:turn(-1)).pack(side='left'); ttk.Button(nav,text='Next page',command=lambda:turn(1)).pack(side='left')
    ttk.Label(nav,textvariable=status).pack(side='left',padx=10)
    ttk.Label(root,text='Selected difference: full JSON values (A / B)',padding=6).pack(anchor='w')
    details = ttk.Panedwindow(root,orient='horizontal'); details.pack(fill='both',padx=6,pady=6)
    def detail():
        panel=ttk.Frame(details); text=tk.Text(panel,height=8,wrap='word'); scroll=ttk.Scrollbar(panel,command=text.yview); text.configure(yscrollcommand=scroll.set); text.pack(side='left',fill='both',expand=True); scroll.pack(side='right',fill='y'); details.add(panel,weight=1); return text
    detail_a=detail(); detail_b=detail()
    pending = None
    def schedule(*args):
        nonlocal pending
        if pending: root.after_cancel(pending)
        pending = root.after(250,filter_rows)
    query.trace_add('write',schedule); box.bind('<<ComboboxSelected>>',filter_rows)
    if demo:
        def load_demo():
            for i,name in enumerate(('save-a.json','save-b.json')):
                docs[i] = Document(Path(__file__).resolve().parent/'examples'/name)
                paths[i].set('examples/' + name)
            compare()
            if tree.get_children():
                tree.selection_set(tree.get_children()[0])
        root.after(100,load_demo)
    root.mainloop()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo',action='store_true',help='Compare the included synthetic example saves')
    gui(demo=parser.parse_args().demo)
