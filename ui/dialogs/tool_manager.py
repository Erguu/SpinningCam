import tkinter as tk
from tkinter import ttk, messagebox

class ToolManager(tk.Toplevel):
    def __init__(self, parent, ui_manager):
        super().__init__(parent)
        self.ui = ui_manager
        self.editing_id = None  # Track which tool is being edited
        
        self.title("Tool Manager")
        self.geometry("600x450")
        
        self._create_ui()
        
    def _create_ui(self):
        # Treeview
        cols = ("ID", "Name", "Radius", "Type", "Color")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols: 
            self.tree.heading(c, text=c)
            self.tree.column(c, width=80)
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Bind double-click to edit
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        
        self.refresh()
        
        # Edit Frame
        f_edit = ttk.LabelFrame(self, text="Tool Editor")
        f_edit.pack(fill="x", padx=5, pady=5)
        
        # Entry fields (Horizontal Layout)
        f_entries = ttk.Frame(f_edit)
        f_entries.pack(fill="x", padx=5, pady=5)
        
        self.entries = {}
        for c in cols:
            f = ttk.Frame(f_entries)
            f.pack(side="left", padx=2)
            tk.Label(f, text=c, font=("Arial", 8)).pack(anchor="w")
            e = ttk.Entry(f, width=10)
            e.pack()
            self.entries[c] = e

        # Buttons
        f_btns = ttk.Frame(f_edit)
        f_btns.pack(fill="x", pady=5)
        
        self.btn_add = tk.Button(f_btns, text="Add New Tool", command=self.add_tool, bg="lightgreen", width=14)
        self.btn_add.pack(side="left", padx=5)
        
        self.btn_update = tk.Button(f_btns, text="Save Changes", command=self.update_tool, bg="gold", width=14)
        self.btn_update.pack(side="left", padx=5)
        
        self.btn_clear = tk.Button(f_btns, text="Clear Fields", command=self.clear_fields, bg="lightgray", width=12)
        self.btn_clear.pack(side="left", padx=5)
        
        self.btn_delete = tk.Button(f_btns, text="Delete Selected", command=self.del_tool, bg="lightcoral", width=14)
        self.btn_delete.pack(side="right", padx=5)
        
        # Status label
        self.lbl_status = tk.Label(f_edit, text="Double-click a tool to edit, or fill fields and click 'Add New Tool'", fg="gray")
        self.lbl_status.pack(pady=2)

    def refresh(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        for tool in self.ui.tool_library:
            self.tree.insert("", "end", values=(tool.get("id"), tool.get("name"), tool.get("radius"), tool.get("type"), tool.get("color")))
    
    def on_select(self, event):
        """Load selected tool into entry fields."""
        sel = self.tree.selection()
        if not sel: return
        item = self.tree.item(sel[0])
        vals = item["values"]
        if len(vals) < 5: return
        
        self.entries["ID"].delete(0, tk.END)
        self.entries["ID"].insert(0, vals[0])
        self.entries["Name"].delete(0, tk.END)
        self.entries["Name"].insert(0, vals[1])
        self.entries["Radius"].delete(0, tk.END)
        self.entries["Radius"].insert(0, vals[2])
        self.entries["Type"].delete(0, tk.END)
        self.entries["Type"].insert(0, vals[3])
        self.entries["Color"].delete(0, tk.END)
        self.entries["Color"].insert(0, vals[4])
        
        self.editing_id = vals[0]
        self.lbl_status.config(text=f"Editing: {vals[0]} - Click 'Save Changes' to update", fg="blue")
    
    def on_double_click(self, event):
        """Same as select but more explicit."""
        self.on_select(event)
        
    def clear_fields(self):
        """Clear all entry fields and reset edit mode."""
        for e in self.entries.values():
            e.delete(0, tk.END)
        self.editing_id = None
        self.lbl_status.config(text="Fields cleared. Ready to add new tool.", fg="gray")
            
    def add_tool(self):
        try:
            rad = float(self.entries["Radius"].get())
        except: rad = 0.0
        
        new_id = self.entries["ID"].get()
        if not new_id:
            messagebox.showwarning("Missing ID", "Tool ID is required.")
            return
        
        # Check for duplicate ID
        for t in self.ui.tool_library:
            if t["id"] == new_id:
                messagebox.showwarning("Duplicate ID", f"Tool ID '{new_id}' already exists. Use 'Save Changes' to update.")
                return
        
        new_t = {
            "id": new_id,
            "name": self.entries["Name"].get() or "Unnamed",
            "radius": rad,
            "type": self.entries["Type"].get() or "roller",
            "color": self.entries["Color"].get() or "red"
        }
        
        self.ui.tool_library.append(new_t)
        self.ui.save_tools()
        self.refresh()
        self.clear_fields()
        self.lbl_status.config(text=f"Added new tool: {new_id}", fg="green")
    
    def update_tool(self):
        """Update existing tool with current field values."""
        if not self.editing_id:
            messagebox.showinfo("Select Tool", "Select a tool to edit first (click on it in the list).")
            return
        
        try:
            rad = float(self.entries["Radius"].get())
        except: rad = 0.0
        
        new_id = self.entries["ID"].get()
        if not new_id:
            messagebox.showwarning("Missing ID", "Tool ID is required.")
            return
        
        # Find and update the tool
        for t in self.ui.tool_library:
            if t["id"] == self.editing_id:
                t["id"] = new_id
                t["name"] = self.entries["Name"].get() or "Unnamed"
                t["radius"] = rad
                t["type"] = self.entries["Type"].get() or "roller"
                t["color"] = self.entries["Color"].get() or "red"
                break
        
        self.ui.save_tools()
        self.refresh()
        self.lbl_status.config(text=f"Updated tool: {new_id}", fg="green")
        self.editing_id = new_id  # In case ID changed
        
    def del_tool(self):
        sel = self.tree.selection()
        if not sel: 
            messagebox.showinfo("Select Tool", "Select a tool to delete first.")
            return
        item = self.tree.item(sel[0])
        tid = item["values"][0]
        
        if messagebox.askyesno("Confirm Delete", f"Delete tool '{tid}'?"):
            self.ui.tool_library = [t for t in self.ui.tool_library if t["id"] != tid]
            self.ui.save_tools()
            self.refresh()
            self.clear_fields()
            self.lbl_status.config(text=f"Deleted tool: {tid}", fg="red")
