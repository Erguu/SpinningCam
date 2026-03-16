import tkinter as tk
from tkinter import ttk

class UIHelper:
    def __init__(self, tooltip_label):
        self.lbl_info = tooltip_label

    def bind_tooltip(self, widget, text):
        if not text: return
        widget.bind("<Enter>", lambda e: self.lbl_info.config(text=text))
        widget.bind("<Leave>", lambda e: self.lbl_info.config(text="Ready. Hover over items for info."))

    def add_section_header(self, parent, text, color="gray"):
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=(15, 5), padx=5)
        lbl = tk.Label(f, text=text, bg=color, fg="white", font=("Arial", 10, "bold"), anchor="w", padx=5)
        lbl.pack(fill="x")

    def add_spinbox(self, parent, app, key, title, min_val, max_val, step, tooltip=""):
        f = ttk.Frame(parent)
        f.pack(fill="x", padx=10, pady=2)
        
        ttk.Label(f, text=title).pack(side="top", anchor="w")
        
        # Tkinter Spinbox works with strings mostly
        var = tk.DoubleVar(value=app.params.get(key, 0.0))
        
        def on_change(*args):
             app.on_param_change(key, var.get(), "all")
        
        sb = ttk.Spinbox(f, from_=min_val, to=max_val, increment=step, textvariable=var)
        sb.pack(fill="x")
        sb.bind("<Return>", lambda e: on_change())
        sb.bind("<FocusOut>", lambda e: on_change())
        sb.bind("<Button-1>", lambda event: event.widget.focus_force())
        sb.configure(command=on_change) # Arrows
        self.bind_tooltip(sb, tooltip)
        self.bind_tooltip(f, tooltip)

    def add_scale(self, parent, app, key, title, min_val, max_val, mode="all", tooltip=""):
        f = ttk.Frame(parent)
        f.pack(fill="x", padx=10, pady=2)
        
        ttk.Label(f, text=title).pack(side="left", anchor="w")
        
        val = app.params.get(key, 0.0)
        var = tk.StringVar(value=f"{float(val):.2f}")
        
        def on_update(event=None):
            try:
                v = float(var.get())
                app.on_param_change(key, v, mode)
            except ValueError:
                pass
                
        e = ttk.Entry(f, textvariable=var, width=10, justify="right")
        e.pack(side="right")
        e.bind("<Return>", on_update)
        e.bind("<FocusOut>", on_update)
        e.bind("<Button-1>", lambda event: event.widget.focus_force())
        self.bind_tooltip(e, tooltip)
        self.bind_tooltip(f, tooltip)

    def add_checkbox(self, parent, app, key, title, tooltip=""):
        f = ttk.Frame(parent)
        f.pack(fill="x", padx=10, pady=2)
        
        var = tk.BooleanVar(value=bool(app.params.get(key, False)))
        def on_toggle():
            val = var.get()
            app.on_param_change(key, val, "all")
            
        cb = ttk.Checkbutton(f, text=title, variable=var, command=on_toggle)
        cb.pack(anchor="w")
        self.bind_tooltip(cb, tooltip)
        self.bind_tooltip(f, tooltip)

    def add_button(self, parent, text, command, bg_color, tooltip=""):
        # ttk buttons hard to color, using standard tk Button for colors
        btn = tk.Button(parent, text=text, command=command, bg=bg_color, fg="black", font=("Arial", 9, "bold"))
        btn.pack(fill="x", padx=10, pady=5)
        self.bind_tooltip(btn, tooltip)
