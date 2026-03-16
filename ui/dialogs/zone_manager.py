import tkinter as tk
from tkinter import ttk

class ZoneManager(tk.Toplevel):
    def __init__(self, parent, app, op_idx):
        super().__init__(parent)
        self.app = app
        self.op_idx = op_idx
        
        if op_idx >= len(self.app.params["operations"]): 
            self.destroy()
            return
            
        self.op = self.app.params["operations"][op_idx]
        if "zones" not in self.op: self.op["zones"] = []
        
        self.title(f"Zones: Op #{op_idx+1}")
        self.geometry("500x400")
        self.focus_force()
        
        self._create_ui()
        
    def _create_ui(self):
        cols = ("Start Z", "End Z", "Speed", "Feed")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols: 
            self.tree.heading(c, text=c)
            self.tree.column(c, width=100)
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.refresh()
        
        f_edit = ttk.Frame(self)
        f_edit.pack(fill="x", padx=5, pady=5)
        
        self.entries = {}
        for c in cols:
            f = ttk.Frame(f_edit)
            f.pack(side="left", padx=2)
            tk.Label(f, text=c, font=("Arial", 8)).pack(anchor="w")
            e = ttk.Entry(f, width=10)
            e.pack()
            self.entries[c] = e
            
        f_act = ttk.Frame(self)
        f_act.pack(pady=5)
        tk.Button(f_act, text="Add Zone", command=self.add_zone, bg="lightgreen").pack(side="left", padx=5)
        tk.Button(f_act, text="Delete Selected", command=self.del_zone, bg="lightcoral").pack(side="left", padx=5)
        
    def refresh(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        # Sort by Start Z
        self.op["zones"].sort(key=lambda z: z.get("start_z", 0.0))
        for z in self.op["zones"]:
            self.tree.insert("", "end", values=(z.get("start_z"), z.get("end_z"), z.get("speed"), z.get("feed")))
            
    def add_zone(self):
        try:
            sz = float(self.entries["Start Z"].get())
            ez = float(self.entries["End Z"].get())
            sp = float(self.entries["Speed"].get())
            fe = float(self.entries["Feed"].get())
            self.op["zones"].append({"start_z": sz, "end_z": ez, "speed": sp, "feed": fe})
            self.refresh()
        except: pass
        
    def del_zone(self):
        sel = self.tree.selection()
        if not sel: return
        idx = self.tree.index(sel[0])
        self.op["zones"].pop(idx)
        self.refresh()
