import tkinter as tk
from tkinter import ttk
from i18n import t


def _fmt_num(v):
    """Compact number formatting: drop the '.0' on integers, trim noise otherwise."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f):
        return str(int(f))
    return f"{f:g}"


def scroll_not_edit(widget):
    """Make the mouse wheel over an input widget SCROLL the enclosing tab instead
    of changing the widget's value.

    ttk.Spinbox and ttk.Combobox bind <MouseWheel> at the class level to
    increment / cycle their value, so hovering one while scrolling the page
    silently edits it (user report 2026-07-08). Bind a widget-level handler that
    walks up to the nearest Canvas ancestor, scrolls it, and returns "break" so
    the class-level value change never runs. Safe no-op if there is no Canvas
    ancestor."""
    def _on_wheel(event):
        w = widget
        while w is not None:
            if isinstance(w, tk.Canvas):
                w.yview_scroll(int(-1 * (event.delta / 120)), "units")
                break
            w = getattr(w, "master", None)
        return "break"
    widget.bind("<MouseWheel>", _on_wheel)


class UIHelper:
    # Faded hint styling (default value + allowed range shown under a field).
    HINT_COLOR = "#9a9a9a"
    HINT_FONT = ("Arial", 7)

    def __init__(self, tooltip_label):
        self.lbl_info = tooltip_label
        # Every input built here binds a Tk variable that is seeded from
        # app.params ONCE, at build time, and writes back on <FocusOut>. Anything
        # that changes params from OUTSIDE the widget (the calibration dialog's
        # Apply buttons) therefore leaves the box showing the old number — and
        # the next focus-out writes that stale number back over the new one.
        # Registering the variables here lets such a caller re-sync them.
        self._param_vars = []

    def register_param_var(self, key, var, widget, getter=None):
        """Track a Tk variable that mirrors ``app.params[key]``.

        ``getter(params)`` overrides how the display value is derived, for fields
        whose shown value is not simply params[key] (Program End follows Program
        Start while it is unset).
        """
        self._param_vars.append((key, var, widget, getter))

    def refresh_from_params(self, app, keys=None):
        """Re-seed registered inputs from app.params. Returns the keys updated.

        Call after changing params behind the UI's back. Entries whose widget has
        been destroyed (tab rebuilt) are dropped instead of raising.
        """
        done, live = [], []
        for key, var, widget, getter in self._param_vars:
            try:
                if not widget.winfo_exists():
                    continue
            except tk.TclError:
                continue
            live.append((key, var, widget, getter))
            if keys is not None and key not in keys:
                continue
            try:
                val = getter(app.params) if getter else app.params.get(key)
                if val is None or val == "":
                    continue
                cur = var.get()
                new = f"{float(val):.2f}" if isinstance(var, tk.StringVar) else (
                    bool(val) if isinstance(var, tk.BooleanVar) else float(val))
                if isinstance(var, tk.StringVar):
                    if str(cur) != new:
                        var.set(new); done.append(key)
                elif cur != new:
                    var.set(new); done.append(key)
            except (tk.TclError, TypeError, ValueError):
                continue
        self._param_vars = live
        return done

    def _field_hint_text(self, app, key, min_val, max_val):
        """Build the faded hint string: factory default + the range you can move within.

        Example:  'default 2  ·  0 - 20'  (default is 2, adjustable between 0 and 20).
        Uses only Latin-5-safe characters so it never trips the cp1254 console.
        """
        defaults = getattr(app, "factory_defaults", None) or {}
        parts = []
        if key in defaults:
            parts.append(f"{t('hint_default')} {_fmt_num(defaults[key])}")
        parts.append(f"{_fmt_num(min_val)} - {_fmt_num(max_val)}")
        return "  ·  ".join(parts)

    def _add_field_hint(self, parent, app, key, min_val, max_val, side="right"):
        """Pack a small greyed-out hint label onto an input's label row.

        Placed on the same row as the field title (right-aligned) so it never
        adds a line of height / shifts the layout down.
        """
        text = self._field_hint_text(app, key, min_val, max_val)
        if not text:
            return
        tk.Label(parent, text=text, fg=self.HINT_COLOR, font=self.HINT_FONT,
                 anchor="e").pack(side=side, anchor="e", padx=(6, 0))

    def bind_tooltip(self, widget, text):
        if not text: return
        # Collapse newlines/runs of whitespace so the single-line status bar
        # always shows one tidy line. (The bar's height is locked in
        # main_window._setup_layout, so multi-line text would otherwise be
        # clipped mid-sentence.)
        flat = " ".join(text.split())
        widget.bind("<Enter>", lambda e: self.lbl_info.config(text=flat))
        widget.bind("<Leave>", lambda e: self.lbl_info.config(text="Ready. Hover over items for info."))

    def add_section_header(self, parent, text, color="gray"):
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=(15, 5), padx=5)
        lbl = tk.Label(f, text=text, bg=color, fg="white", font=("Arial", 10, "bold"), anchor="w", padx=5)
        lbl.pack(fill="x")

    def add_spinbox(self, parent, app, key, title, min_val, max_val, step, tooltip="", mode="all"):
        f = ttk.Frame(parent)
        f.pack(fill="x", padx=10, pady=2)

        title_row = ttk.Frame(f)
        title_row.pack(fill="x")
        ttk.Label(title_row, text=title).pack(side="left", anchor="w")
        self._add_field_hint(title_row, app, key, min_val, max_val)

        # Tkinter Spinbox works with strings mostly
        var = tk.DoubleVar(value=app.params.get(key, 0.0))

        def on_change(*args):
             app.on_param_change(key, var.get(), mode)

        sb = ttk.Spinbox(f, from_=min_val, to=max_val, increment=step, textvariable=var)
        sb.pack(fill="x")
        sb.bind("<Return>", lambda e: on_change())
        sb.bind("<FocusOut>", lambda e: on_change())
        sb.bind("<Button-1>", lambda event: event.widget.focus_force())
        sb.configure(command=on_change) # Arrows
        scroll_not_edit(sb)   # wheel scrolls the tab, never edits the value
        self.register_param_var(key, var, sb)
        self.bind_tooltip(sb, tooltip)
        self.bind_tooltip(f, tooltip)

    def add_scale(self, parent, app, key, title, min_val, max_val, mode="all", tooltip=""):
        f = ttk.Frame(parent)
        f.pack(fill="x", padx=10, pady=2)

        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text=title).pack(side="left", anchor="w")

        val = app.params.get(key, 0.0)
        var = tk.StringVar(value=f"{float(val):.2f}")

        def on_update(event=None):
            try:
                v = float(var.get())
                app.on_param_change(key, v, mode)
            except ValueError:
                pass

        e = ttk.Entry(row, textvariable=var, width=10, justify="right")
        e.pack(side="right")
        e.bind("<Return>", on_update)
        e.bind("<FocusOut>", on_update)
        e.bind("<Button-1>", lambda event: event.widget.focus_force())
        self._add_field_hint(row, app, key, min_val, max_val)
        self.bind_tooltip(e, tooltip)
        self.bind_tooltip(f, tooltip)
        self.register_param_var(key, var, e)

    def add_checkbox(self, parent, app, key, title, tooltip="", mode="all"):
        f = ttk.Frame(parent)
        f.pack(fill="x", padx=10, pady=2)

        var = tk.BooleanVar(value=bool(app.params.get(key, False)))
        def on_toggle():
            val = var.get()
            app.on_param_change(key, val, mode)
            
        cb = ttk.Checkbutton(f, text=title, variable=var, command=on_toggle)
        cb.pack(anchor="w")
        self.bind_tooltip(cb, tooltip)
        self.bind_tooltip(f, tooltip)

    def add_button(self, parent, text, command, bg_color, tooltip=""):
        # ttk buttons hard to color, using standard tk Button for colors
        btn = tk.Button(parent, text=text, command=command, bg=bg_color, fg="black", font=("Arial", 9, "bold"))
        btn.pack(fill="x", padx=10, pady=5)
        self.bind_tooltip(btn, tooltip)
