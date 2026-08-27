# -*- coding: utf-8 -*-
"""SCL Inspector — see what PLC decimation actually does to the toolpath.

The .nc file is always full resolution (2026-07-26c), so a G-code viewer shows
the INTENDED path. The PLC is fed by the SCL export, which is decimated to fit
the recipe line limit — and a curve whose bulge is smaller than the tolerance is
dropped entirely. That difference was previously invisible until the part came
off the machine.

This window shows both paths on top of each other, at the tolerance the SCL
export would REALLY use (auto-fitted when auto-tune is on, the manual
plc_tolerance otherwise), plus a per-pass table that says which features survive.

Read-only: nothing here writes params or touches a toolpath.
"""
import tkinter as tk
from tkinter import ttk

import numpy as np

from i18n import t
from ui import preview_orient
from ui import dialog_sizing


# ── analysis (pure — no Tk, so it can be tested headless) ────────────────────

def _poly_dev(points, poly):
    """Worst distance (mm) from `points` to the polyline `poly` (XZ plane)."""
    pts = np.asarray(points, dtype=float)
    pol = np.asarray(poly, dtype=float)
    if len(pts) == 0 or len(pol) < 2:
        return 0.0
    seg = pol[1:] - pol[:-1]
    L2 = np.einsum("ij,ij->i", seg, seg)
    L2[L2 < 1e-12] = 1e-12
    worst = 0.0
    for q in pts:
        u = np.clip(np.einsum("ij,ij->i", q - pol[:-1], seg) / L2, 0.0, 1.0)
        proj = pol[:-1] + u[:, None] * seg
        d = float(np.min(np.linalg.norm(proj - q, axis=1)))
        if d > worst:
            worst = d
    return worst


def _chord_bulge(points):
    """How far a run of points bulges off its own straight chord (mm).
    This is exactly the quantity RDP compares against the tolerance, so it is
    what decides whether a curve survives decimation at all."""
    pts = np.asarray(points, dtype=float)
    if len(pts) < 3:
        return 0.0
    return _poly_dev(pts[1:-1], np.vstack([pts[0], pts[-1]]))


def _curved_part(points, tol=0.02):
    """The CURVED tail of a run that starts straight.

    An exit leg is `straight T2→M` + `curve M→end`, and measuring the bulge of
    the whole thing would mostly measure the straight part's offset from the
    overall chord — which says nothing about whether the CURVE survives. So walk
    forward from the start along the initial direction and cut where the path
    first departs from it. Returns None when the run never curves.
    """
    pts = np.asarray(points, dtype=float)
    if len(pts) < 4:
        return None
    d0 = pts[1] - pts[0]
    n0 = np.linalg.norm(d0)
    if n0 < 1e-9:
        return None
    d0 = d0 / n0
    dev = np.linalg.norm(np.cross(pts - pts[0], d0), axis=1)
    idx = np.nonzero(dev > tol)[0]
    if len(idx) == 0:
        return None
    m = int(idx[0])
    return pts[m:] if len(pts) - m >= 3 else None


def analyze_plc_output(path_gen, params):
    """Compare the full-resolution paths against what the SCL export would ship.

    Returns a dict; `ok=False` with `reason` when there is nothing to inspect.
    Never mutates `params` or any persistent state.
    """
    full_paths = list(getattr(path_gen, "last_calculated_paths", None) or [])
    if not full_paths:
        return {"ok": False, "reason": "no_paths"}

    center_x = float(params.get("mandrel_pos_x_offset", 0.0) or 0.0)
    budget = int(params.get("plc_target_lines", 0) or 0) or None
    auto = bool(params.get("plc_auto_tune", False)) and bool(params.get("plc_mode", False))

    tol = float(params.get("plc_tolerance", 0.5) or 0.5)
    exit_tol = float(params.get("plc_exit_tolerance", tol) or tol)
    source = "manual"
    status = None

    if auto and budget:
        try:
            from export_manager import ExportManager
            floor = path_gen.measure_min_clearance(full_paths, params)
            res = ExportManager.auto_fit_plc_tolerance(path_gen, params, budget, floor)
            tol = float(res.get("tolerance", tol))
            exit_tol = tol            # auto-tune ties the exit tolerance to the main one
            source = "auto"
            status = res.get("status")
        except Exception:             # fall back to the manual value, still useful
            source = "manual"

    dec_paths = path_gen.decimate_all_paths(tol, exit_tol, center_x, params=params)

    # True SCL recipe line count — parse the same way the exporter does.
    lines = None
    try:
        from recipe_to_scl import GCodeToSCLConverter
        p = dict(params)
        p["plc_mode"] = True
        p["plc_tolerance"] = tol
        p["plc_exit_tolerance"] = exit_tol
        conv = GCodeToSCLConverter()
        conv.parse_gcode(path_gen.generate_gcode(params=p, for_recipe=True))
        lines = len(conv.lines)
    except Exception:
        lines = None

    op_map = getattr(path_gen, "_path_op_map", []) or []
    splits = getattr(path_gen, "last_render_split_idx", {}) or {}

    rows = []
    for i, full in enumerate(full_paths):
        full = np.asarray(full, dtype=float)
        dec = np.asarray(dec_paths[i], dtype=float) if i < len(dec_paths) else full
        op = op_map[i] if i < len(op_map) else None
        name = (op or {}).get("name") or (op or {}).get("type") or "?"

        # Exit section = everything after the P2 fillet (T2). That is where the
        # curl / bow lives and where plc_exit_tolerance applies.
        sp = splits.get(i)
        arc_end = int(sp[1]) if sp else None
        exit_full = full[arc_end:] if (arc_end is not None and arc_end < len(full) - 2) else None

        # Only the CURVED tail of the exit matters for "will my curve survive".
        curve = _curved_part(exit_full) if exit_full is not None else None
        bulge = _chord_bulge(curve) if curve is not None else 0.0

        # Points of the decimated path that fall inside the curved tail.
        kept_curve = 0
        if curve is not None and len(dec):
            d0 = np.linalg.norm(dec - curve[0], axis=1)
            kept_curve = max(len(dec) - int(np.argmin(d0)), 0)

        # RDP's error is ALWAYS <= tolerance, so a big error is never the signal.
        # The signal is whether the feature can survive at all:
        #   flat   — the whole curve bulges less than the tolerance, so RDP is
        #            free to delete it and run a straight line instead.
        #   coarse — it survives, but as 1–2 chords: recognisable, not accurate.
        state = "ok"
        if curve is not None and bulge > 0.02:
            if bulge <= exit_tol:
                state = "flat"
            elif kept_curve <= 3:
                state = "coarse"
        rows.append({
            "i": i, "name": name,
            "kept": len(dec), "full": len(full),
            "kept_exit": kept_curve,
            "worst_dev": _poly_dev(full, dec),
            "bulge": bulge,
            "state": state,
            "flattened": state == "flat",
        })

    return {
        "ok": True, "reason": None,
        "tolerance": tol, "exit_tolerance": exit_tol,
        "source": source, "autotune_status": status,
        "lines": lines, "budget": budget,
        "full_points": int(sum(len(p) for p in full_paths)),
        "dec_points": int(sum(len(p) for p in dec_paths)),
        "passes": rows,
        "full_paths": full_paths, "dec_paths": dec_paths,
        # #99: fillet caps that had to be dropped to keep clearance. Populated by
        # decimate_all_paths above, so it reflects THIS preview's numbers.
        "cap_warnings": list(getattr(path_gen, "last_point_cap_warnings", None) or []),
    }


# ── window ──────────────────────────────────────────────────────────────────

class SclInspectorDialog(tk.Toplevel):
    """Read-only side-by-side of the intended path and the PLC recipe."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title(t("dlg_scl_inspector"))
        dialog_sizing.fit(self, 1000, 680)
        self.minsize(720, 480)
        self._data = None
        self._build()
        self.refresh()
        self.transient(parent)

    # -- ui -------------------------------------------------------------
    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(10, 4))
        self.lbl_head = ttk.Label(top, text="", font=("Arial", 10, "bold"))
        self.lbl_head.pack(side="left")
        ttk.Button(top, text=t("btn_refresh"), command=self.refresh).pack(side="right")

        self.lbl_sub = tk.Label(self, text="", font=("Arial", 8), fg="gray",
                                anchor="w", justify="left", wraplength=960)
        self.lbl_sub.pack(fill="x", padx=10)

        # #102: resolved once, when the window opens — see preview_orient. The
        # paths drawn here are MACHINE coordinates, hence frame=MACHINE.
        self._orient = preview_orient.resolve(self.app, frame=preview_orient.MACHINE)
        self.canvas = tk.Canvas(self, height=300, bg="#0e141b", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=6)
        self.canvas.bind("<Configure>", lambda e: self._draw())

        legend = ttk.Frame(self)
        legend.pack(fill="x", padx=10)
        for colour, key in (("#4a5766", "leg_full"), ("#5cc8ff", "leg_plc"),
                            ("#ff7b72", "leg_flat")):
            box = tk.Canvas(legend, width=13, height=13, highlightthickness=0)
            box.create_rectangle(1, 1, 12, 12, fill=colour, outline=colour)
            box.pack(side="left", padx=(10, 3), pady=2)
            ttk.Label(legend, text=t(key)).pack(side="left")

        cols = ("pass", "op", "kept", "exitpts", "dev", "bulge", "state")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=8)
        widths = {"pass": 55, "op": 190, "kept": 90, "exitpts": 90,
                  "dev": 110, "bulge": 110, "state": 200}
        for c in cols:
            self.tree.heading(c, text=t(f"col_scl_{c}"))
            self.tree.column(c, width=widths[c],
                             anchor="w" if c in ("op", "state") else "center")
        self.tree.pack(fill="both", expand=False, padx=10, pady=(4, 10))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._draw())
        self.tree.tag_configure("flat", foreground="#c04a44")
        self.tree.tag_configure("coarse", foreground="#b8860b")

    # -- data -----------------------------------------------------------
    def refresh(self):
        self._data = analyze_plc_output(self.app.path_gen, self.app.params)
        d = self._data
        self.tree.delete(*self.tree.get_children())
        if not d.get("ok"):
            self.lbl_head.config(text=t("scl_no_paths"))
            self.lbl_sub.config(text="")
            self.canvas.delete("all")
            return

        src = t("scl_src_auto") if d["source"] == "auto" else t("scl_src_manual")
        head = t("scl_head").format(tol=f"{d['tolerance']:.3f}", src=src)
        if d["lines"] is not None:
            head += "    " + (t("scl_lines_budget").format(
                lines=d["lines"], budget=d["budget"],
                pct=(100.0 * d["lines"] / d["budget"]) if d["budget"] else 0)
                if d["budget"] else t("scl_lines").format(lines=d["lines"]))
        self.lbl_head.config(text=head)

        flat_n = sum(1 for r in d["passes"] if r["state"] == "flat")
        coarse_n = sum(1 for r in d["passes"] if r["state"] == "coarse")
        sub = t("scl_points").format(full=d["full_points"], dec=d["dec_points"])
        if flat_n:
            sub += "   ⚠ " + t("scl_flat_warn").format(n=flat_n, tol=f"{d['exit_tolerance']:.3f}")
        if coarse_n:
            sub += "   " + t("scl_coarse_warn").format(n=coarse_n)
        # #99: say so here too — this window is where the cap's effect is visible
        # at all, so it is also where its absence needs explaining.
        _caps = d.get("cap_warnings") or []
        if _caps:
            sub += "   ⚠ " + t("scl_cap_warn").format(n=len(_caps))
        self.lbl_sub.config(text=sub)

        _lbl = {"flat": t("scl_state_flat"), "coarse": t("scl_state_coarse"),
                "ok": t("scl_state_ok")}
        for r in d["passes"]:
            self.tree.insert(
                "", "end", iid=str(r["i"]),
                values=(r["i"] + 1, r["name"], f'{r["kept"]} / {r["full"]}',
                        r["kept_exit"] if r["bulge"] > 0.001 else "—",
                        f'{r["worst_dev"]:.3f} mm',
                        f'{r["bulge"]:.3f} mm' if r["bulge"] > 0.001 else "—",
                        _lbl[r["state"]]),
                tags=(r["state"],))
        self._draw()

    # -- drawing --------------------------------------------------------
    def _draw(self):
        c = self.canvas
        c.delete("all")
        d = self._data
        if not d or not d.get("ok"):
            return
        # winfo_width() is 1 until the widget is actually mapped; fall back to the
        # requested size so a draw triggered before the first <Configure> (or from
        # a headless smoke test) still produces the overlay instead of nothing.
        W, H = c.winfo_width(), c.winfo_height()
        if W <= 1:
            W = c.winfo_reqwidth() or 960
        if H <= 1:
            H = c.winfo_reqheight() or 300
        if W < 60 or H < 60:
            return
        mL, mR, mT, mB = 30, 12, 10, 18

        allpts = np.vstack([np.asarray(p, float) for p in d["full_paths"] if len(p)])
        xs, zs = allpts[:, 0], allpts[:, 2]
        xmin, xmax, zmin, zmax = xs.min(), xs.max(), zs.min(), zs.max()
        xr = max(xmax - xmin, 1.0); zr = max(zmax - zmin, 1.0)
        xmin -= xr * 0.05; xmax += xr * 0.05
        zmin -= zr * 0.05; zmax += zr * 0.05
        dW, dH = W - mL - mR, H - mT - mB

        # #102: same shared orientation as the pass table and the waypoint
        # editor, so all three windows draw a pass the same way up.
        #
        # frame=MACHINE, and it matters: these points come out of
        # `last_calculated_paths`, which the engine already mirrored for a
        # negative-side machine. The other two previews are canonical. Asking
        # for the mirror here would apply it twice — invisible on a
        # positive-side machine, nonsense on a negative-side one.
        _or = self._orient
        _corners = [preview_orient.to_plane(_or, x, z)
                    for x in (xmin, xmax) for z in (zmin, zmax)]
        h0 = min(p[0] for p in _corners); h1 = max(p[0] for p in _corners)
        v0 = min(p[1] for p in _corners); v1 = max(p[1] for p in _corners)
        hr = max(h1 - h0, 1e-6); vr = max(v1 - v0, 1e-6)

        def to_c(x, z):
            h, v = preview_orient.to_plane(_or, x, z)
            return (mL + (h - h0) / hr * dW,
                    mT + (v1 - v) / vr * dH)      # canvas Y grows downward

        sel = None
        s = self.tree.selection()
        if s:
            try:
                sel = int(s[0])
            except (ValueError, TypeError):
                sel = None

        # Intended path first (background), then the PLC recipe over it.
        for p in d["full_paths"]:
            p = np.asarray(p, float)
            if len(p) < 2:
                continue
            co = []
            for q in p:
                co += list(to_c(q[0], q[2]))
            c.create_line(*co, fill="#4a5766", width=1)

        for r in d["passes"]:
            p = np.asarray(d["dec_paths"][r["i"]], float)
            if len(p) < 2:
                continue
            colour = "#ff7b72" if r["flattened"] else "#5cc8ff"
            width = 3 if r["i"] == sel else 1
            co = []
            for q in p:
                co += list(to_c(q[0], q[2]))
            c.create_line(*co, fill=colour, width=width)
            for q in p:                      # retained points = what the PLC gets
                x, y = to_c(q[0], q[2])
                rr = 3 if r["i"] == sel else 2
                c.create_oval(x - rr, y - rr, x + rr, y + rr,
                              fill=colour, outline=colour)

        # #102: say which way this actually got drawn — it is no longer fixed.
        _hz, _hx = t("scl_axis_z"), t("scl_axis_x")
        _h, _v = ((_hz, _hx) if _or.z_horizontal else (_hx, _hz))
        _h += " →" if _or.h_sign > 0 else " ←"
        _v += " ↑" if _or.v_sign > 0 else " ↓"
        c.create_text(mL + 2, H - 8, anchor="w", fill="#5b6673",
                      font=("Arial", 7), text=t("scl_axis_hint").format(h=_h, v=_v))
