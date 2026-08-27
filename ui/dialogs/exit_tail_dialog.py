# -*- coding: utf-8 -*-
"""TODO #100 — per-pass editor for the hand-drawn exit tail.

Opened from the pass table for ONE pass. The operator places the points the
roller passes through after P2; the last one ends the pass (there is no P3).

Two rules shape the whole dialog:

* **Seeded, never blank.** It opens pre-filled with the pass's CURRENT tail
  sampled at a few points, so the operator always starts from a shape that
  already runs and only nudges it. An empty table would be an invitation to
  author a gouge from scratch.
* **A bad edit is rejected on the spot** (user, 2026-08-27). The table never
  holds an illegal value: a change that would put the roller inside the
  clearance is refused and the old value restored, with the reason. Because the
  roller passes THROUGH every point, the whole tail is rebuilt and re-checked on
  every edit — moving one point bows the curve through its neighbours.

FRAME (2026-08-27, bug fix). Everything here is CANONICAL (positive-X) space,
the frame the engine generates in and the frame the stored dx/dz live in — the
same sense as the op's own `p3_x`/`p3_z`, so +dx always means "away from the
axis" whichever side the roller is on. The one thing that is NOT canonical is
`last_calculated_paths`: the engine mirrors X around the mandrel centre at the
very end of `calculate_paths` (path_generator.py:1141) for a negative-side
machine. The seed samples those paths, so it MUST mirror them back — see
`_to_canonical`. Getting this wrong is silent on a positive-side machine and
nonsense on a negative-side one (ΔX seeded at −270 instead of +5).
"""
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np

import exit_waypoints as ew
from i18n import t
from logger_config import logger
from ui import preview_orient
from ui import dialog_sizing

SEED_POINTS = 4          # what a freshly seeded tail starts with


class ExitTailDialog(tk.Toplevel):
    def __init__(self, parent, app, op_index, pass_index, p2_xz, on_apply):
        super().__init__(parent)
        self.app = app
        self.op_index = op_index
        self.pass_index = pass_index
        self.p2x, self.p2z = float(p2_xz[0]), float(p2_xz[1])
        self.on_apply = on_apply

        op = self._op()
        self.title(t("et_title").format(
            name=(op or {}).get("name") or (op or {}).get("type", "?"),
            i=pass_index + 1))
        dialog_sizing.fit(self, 820, 600)
        self.transient(parent)

        self.points = ew.normalize(self._stored_points())
        if not self.points:
            self.points = self._seed_from_current_path()

        # OK / Cancel / Clear packed FIRST, to the bottom (#103): Tk squeezes
        # whatever was packed LAST when the screen is too small, and in a
        # top-down dialog that is always the buttons. This window measured
        # 654 px of content at 125 % DPI against a 600 px window — the missing
        # 54 px was exactly this row. Filled in further down.
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", padx=6, pady=6)

        tk.Label(self, text=t("et_help"), anchor="w", justify="left",
                 fg="#446688", wraplength=780).pack(fill="x", padx=8, pady=(8, 2))

        # Shape (per pass). Straight is the default: the waypoints ARE the path,
        # so N points cost N lines. The curve is kept for a controller that can
        # blend — on this PLC it turns 5 points into ~100.
        srow = ttk.Frame(self)
        srow.pack(fill="x", padx=8, pady=(2, 0))
        ttk.Label(srow, text=t("et_shape")).pack(side="left")
        self.shape_var = tk.StringVar(value=self._stored_shape())
        for val, key in ((ew.SHAPE_STRAIGHT, "et_shape_straight"),
                         (ew.SHAPE_SPLINE, "et_shape_spline")):
            ttk.Radiobutton(srow, text=t(key), value=val, variable=self.shape_var,
                            command=self._on_shape).pack(side="left", padx=(8, 0))

        cols = ("n", "anchor", "dx", "dz", "feed")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=9)
        heads = {"n": ("№", 40), "anchor": (t("et_col_anchor"), 120),
                 "dx": (t("et_col_dx"), 110), "dz": (t("et_col_dz"), 110),
                 "feed": (t("et_col_feed"), 110)}
        for c in cols:
            self.tree.heading(c, text=heads[c][0])
            self.tree.column(c, width=heads[c][1], anchor="center")
        self.tree.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._draw())

        # #102: fixed for the life of the window — see pass_table for the same
        # call and the reason (a sketch that re-orients mid-edit is worse than a
        # slightly stale one).
        self._orient = preview_orient.resolve(self.app)
        self.preview = tk.Canvas(self, height=190, bg="#0e141b", highlightthickness=0)
        self.preview.pack(fill="x", padx=6, pady=(4, 0))
        self.preview.bind("<Configure>", lambda _e: self._draw())

        self.lbl_status = tk.Label(self, anchor="w", justify="left", fg="#204060",
                                   bg="#eef3f8", relief="groove", bd=1,
                                   wraplength=780, text=t("et_hint"))
        self.lbl_status.pack(fill="x", padx=6, pady=(4, 0))

        row = ttk.Frame(self)
        row.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Button(row, text=t("et_btn_add"), command=self._add).pack(side="left", padx=2)
        ttk.Button(row, text=t("et_btn_del"), command=self._delete).pack(side="left", padx=2)
        ttk.Button(row, text=t("et_btn_seed"), command=self._reseed).pack(side="left", padx=8)

        ttk.Button(bar, text=t("et_btn_ok"), command=self._ok).pack(side="right", padx=2)
        ttk.Button(bar, text=t("et_btn_cancel"), command=self.destroy).pack(side="right", padx=2)
        ttk.Button(bar, text=t("et_btn_clear"), command=self._clear).pack(side="left", padx=2)

        self._refresh()
        self.lbl_status.config(text=self._ok_hint())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ── data ───────────────────────────────────────────────────────────
    def _op(self):
        ops = self.app.params.get("operations", [])
        return ops[self.op_index] if self.op_index < len(ops) else None

    def _stored_points(self):
        op = self._op() or {}
        pe = (op.get("pass_edits") or {})
        d = pe.get(str(self.pass_index)) or pe.get(self.pass_index) or {}
        return d.get("exit_points")

    def _stored_shape(self):
        return ew.get_shape(self._op(), self.pass_index)

    def _shape(self):
        """The shape currently selected in the dialog (not yet committed)."""
        try:
            return ew.normalize_shape(self.shape_var.get())
        except Exception:
            return ew.DEFAULT_SHAPE

    def _on_shape(self):
        """Switching shape re-runs the clearance check on the SAME points.

        A point list that is safe as a polyline can gouge as a curve (the spline
        bows outside the chords) and vice versa, so the switch is an edit like
        any other — refused and reverted if the result is not clear.
        """
        if not self._try(self.points, t("et_what_shape")):
            self.shape_var.set(ew.SHAPE_SPLINE if self._shape() == ew.SHAPE_STRAIGHT
                               else ew.SHAPE_STRAIGHT)

    def _clearance(self):
        """What this pass must keep clear — the SAME resolution chain the engine
        and the pass table use (`compute_pass_rows`, `pass_table.py:80`).

        The fallback matters: an op that never had `clearance` written on it
        inherits the machine default, and returning 0.0 there would let this
        dialog accept a tail the engine treats as a gouge — the refusal is the
        only thing standing between a typed number and the part.
        """
        op = self._op() or {}
        pe = (op.get("pass_edits") or {})
        d = pe.get(str(self.pass_index)) or pe.get(self.pass_index) or {}
        for src in (d.get("clearance"), op.get("clearance")):
            try:
                if src not in (None, ""):
                    return float(src)
            except (TypeError, ValueError):
                pass

        p = getattr(self.app, "params", {}) or {}

        def _f(v, dflt=0.0):
            try:
                return float(v) if v not in (None, "") else dflt
            except (TypeError, ValueError):
                return dflt

        if op.get("type") == "finishing":
            return (_f(op.get("finish_allowance"))
                    + _f(p.get("safety_clearance_roller_to_part")))
        return _f(p.get("target_clearance"))

    def _geom(self):
        """(radius_at, center_x, base_offset) for the clearance check, or None."""
        mgr = getattr(self.app, "mandrel_mgr", None)
        if mgr is None:
            return None
        p = self.app.params
        op = self._op() or {}
        try:
            m_min = mgr.props.get("min_z", float('-inf'))
            m_top = mgr.props.get("top_z", float('inf'))
        except Exception:
            return None

        def radius_at(z, _a=m_min, _b=m_top):
            if z < _a or z > _b:
                return None
            return mgr.get_radius_fast(z)

        base = (float(p.get("final_part_thickness_on_mandrel", 2.0))
                + float(p.get("shell_thickness", 0.0))
                + float(op.get("r_tool", 25.0)))
        return radius_at, float(p.get("mandrel_pos_x_offset", 0.0)), base

    # ── frame ──────────────────────────────────────────────────────────
    def _to_canonical(self, x):
        """Real machine X → canonical (positive-X) X.

        Identity on a positive-side machine. On a negative-side one it undoes
        the end-of-calculation mirror around the mandrel centre, which is the
        only reason a calculated path ever disagrees with P2 here.
        """
        p = getattr(self.app, "params", {}) or {}
        if p.get("roller_positive_x_side", True):
            return float(x)
        return 2.0 * float(p.get("mandrel_pos_x_offset", 0.0)) - float(x)

    # ── seeding ────────────────────────────────────────────────────────
    def _seed_from_current_path(self):
        """Sample the pass's CURRENT exit leg into a handful of P2-relative points.

        Uses the real calculated path rather than re-deriving the parametric
        shape, so whatever the op is doing today — bow, curl, arc, plain line —
        is what the operator starts from.

        The sampled path is in MACHINE X, P2 is in canonical X, so every sample
        goes through `_to_canonical` before the subtraction. Without it, a
        negative-side machine seeds ΔX ≈ −(2·P2) and then refuses every sane
        number the operator types, because they resolve to the far side of the
        axis — i.e. inside the part.
        """
        try:
            pg = self.app.path_gen
            paths = getattr(pg, "last_calculated_paths", None) or []
            idxs = [k for k, o in enumerate(getattr(pg, "_path_op_map", []))
                    if o is self._op()]
            if not idxs or self.pass_index >= len(idxs):
                return self._seed_fallback()
            pi = idxs[self.pass_index]
            path = np.asarray(paths[pi], dtype=float)
            split = (getattr(pg, "last_render_split_idx", {}) or {}).get(pi)
            start = split[1] if split else 0          # T2 = end of the P2 fillet
            tail = path[start:]
            if len(tail) < 2:
                return self._seed_fallback()
            # even by arc length so the seed reflects shape, not sampling density
            seg = np.linalg.norm(np.diff(tail[:, [0, 2]], axis=0), axis=1)
            cum = np.concatenate([[0.0], np.cumsum(seg)])
            if cum[-1] <= 1e-9:
                return self._seed_fallback()
            picks = np.linspace(0.0, cum[-1], SEED_POINTS + 1)[1:]   # skip T2 itself
            out = []
            for target in picks:
                k = int(np.argmin(np.abs(cum - target)))
                out.append({"anchor": "p2", "feed": None,
                            "dx": round(self._to_canonical(tail[k][0]) - self.p2x, 3),
                            "dz": round(float(tail[k][2]) - self.p2z, 3)})
            return ew.normalize(out)
        except Exception as e:
            logger.debug(f"#100 seed from path failed: {e}")
            return self._seed_fallback()

    def _seed_fallback(self):
        """No calculated path to copy — lay a short straight tail along the op's
        own p3 direction. Still never an empty table."""
        op = self._op() or {}
        try:
            dx = float(op.get("p3_x", 20.0) or 20.0)
            dz = float(op.get("p3_z", 0.0) or 0.0)
        except (TypeError, ValueError):
            dx, dz = 20.0, 0.0
        return ew.normalize([
            {"anchor": "p2", "dx": round(dx * f, 3), "dz": round(dz * f, 3), "feed": None}
            for f in (0.34, 0.67, 1.0)])

    # ── validation ─────────────────────────────────────────────────────
    def _violations(self, points):
        g = self._geom()
        if g is None or not points:
            return []
        radius_at, center_x, base = g
        curve = ew.build_curve(self.p2x, self.p2z, points, shape=self._shape())
        return ew.check_clearance(curve, radius_at, center_x, base, self._clearance())

    def _try(self, points, what):
        """Accept `points` only if the whole tail stays clear. Returns True when
        applied; on refusal nothing changes and the operator is told why."""
        bad = self._violations(points)
        if bad:
            w = bad[0]
            need = self._clearance()
            # 3 decimals, and the SHORTFALL spelled out. At 2 decimals a small
            # violation printed as "1.70 mm, needs 1.70 mm" — the same number
            # twice, which reads as a bug rather than as a measurement.
            self.lbl_status.config(
                text=t("et_refused").format(
                    what=what, need=f"{need:.3f}",
                    got=f"{w['clearance']:.3f}",
                    short=f"{max(need - w['clearance'], 0.0):.3f}",
                    x=f"{w['x']:.1f}", z=f"{w['z']:.1f}"),
                fg="#a01000", bg="#ffecea")
            self.bell()
            return False
        self.points = points
        self._refresh()
        self.lbl_status.config(text=self._ok_hint(), fg="#204060", bg="#eef3f8")
        return True

    def _ok_hint(self):
        """Status text when all is well — leads with the point COST.

        The reason this feature exists is that the PLC stops at every point and
        has 1000 lines total, so 'what does this tail cost me' is the number the
        operator is actually managing.
        """
        n_emit = len(ew.build_curve(self.p2x, self.p2z, self.points,
                                    shape=self._shape()))
        n_emit = max(n_emit - 1, 0)          # the leading P2/T2 is not the tail's
        return t("et_hint_cost").format(pts=len(self.points), lines=n_emit) \
            + "  " + t("et_hint")

    # ── table ──────────────────────────────────────────────────────────
    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for k, w in enumerate(self.points):
            self.tree.insert("", "end", iid=str(k), values=(
                k + 1,
                t("et_anchor_p2") if w["anchor"] == "p2" else t("et_anchor_prev"),
                f"{w['dx']:.2f}", f"{w['dz']:.2f}",
                "" if w["feed"] is None else f"{w['feed']:.0f}"))
        self._draw()

    def _sel(self):
        s = self.tree.selection()
        return int(s[0]) if s else None

    def _on_double_click(self, event):
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not iid or not col:
            return
        k = int(iid)
        key = {"#2": "anchor", "#3": "dx", "#4": "dz", "#5": "feed"}.get(col)
        if key is None:
            return

        pts = [dict(p) for p in self.points]
        if key == "anchor":
            # Toggling the anchor must not move the point: re-express the same
            # absolute position in the other frame, or the shape jumps on a click.
            abs_now = ew.resolve(self.p2x, self.p2z, self.points)
            ax, az = abs_now[k]
            if pts[k]["anchor"] == "p2" and k > 0:
                bx, bz = abs_now[k - 1]
                pts[k].update(anchor="prev", dx=round(ax - bx, 3), dz=round(az - bz, 3))
            else:
                pts[k].update(anchor="p2", dx=round(ax - self.p2x, 3),
                              dz=round(az - self.p2z, 3))
            self._try(pts, t("et_what_anchor").format(n=k + 1))
            return

        cur = pts[k][key]
        init = "" if cur is None else (f"{cur:.2f}" if key != "feed" else f"{cur:.0f}")
        from tkinter import simpledialog
        val = simpledialog.askstring(t("et_edit_title"),
                                     t("et_edit_prompt").format(field=key, n=k + 1),
                                     initialvalue=init, parent=self)
        if val is None:
            return
        val = val.strip()
        if key == "feed":
            pts[k]["feed"] = None if val == "" else self._num(val)
            if val != "" and pts[k]["feed"] is None:
                return
            self._try(pts, t("et_what_feed").format(n=k + 1))
            return
        num = self._num(val)
        if num is None:
            return
        pts[k][key] = num
        self._try(pts, t("et_what_move").format(n=k + 1))

    def _num(self, s):
        try:
            return float(str(s).replace(",", "."))
        except (TypeError, ValueError):
            self.lbl_status.config(text=t("et_bad_number").format(v=s),
                                   fg="#a01000", bg="#ffecea")
            return None

    def _add(self):
        k = self._sel()
        pts = [dict(p) for p in self.points]
        if not pts:
            pts = self._seed_fallback()
            self._try(pts, t("et_what_add"))
            return
        at = len(pts) - 1 if k is None else k
        # A new point goes HALFWAY to the next one (or repeats the last step at
        # the end), so adding never changes the shape on its own.
        abs_now = ew.resolve(self.p2x, self.p2z, self.points)
        if at + 1 < len(abs_now):
            nx = (abs_now[at][0] + abs_now[at + 1][0]) / 2.0
            nz = (abs_now[at][1] + abs_now[at + 1][1]) / 2.0
        else:
            px, pz = abs_now[at - 1] if at > 0 else (self.p2x, self.p2z)
            nx = abs_now[at][0] + (abs_now[at][0] - px) * 0.5
            nz = abs_now[at][1] + (abs_now[at][1] - pz) * 0.5
        pts.insert(at + 1, {"anchor": "p2", "feed": None,
                            "dx": round(nx - self.p2x, 3),
                            "dz": round(nz - self.p2z, 3)})
        # Any later "prev" point now steps from the new one — re-anchor them to
        # their unchanged absolute positions so inserting cannot move the tail.
        pts = self._rebase(pts, abs_now, at + 1)
        self._try(pts, t("et_what_add"))

    def _rebase(self, pts, abs_before, inserted_at):
        """Keep every pre-existing point where it was after an insert."""
        out = []
        for idx, p in enumerate(pts):
            if idx == inserted_at:
                out.append(p)
                continue
            old = idx if idx < inserted_at else idx - 1
            if p["anchor"] == "prev" and 0 <= old < len(abs_before):
                ax, az = abs_before[old]
                out.append({**p, "anchor": "p2",
                            "dx": round(ax - self.p2x, 3),
                            "dz": round(az - self.p2z, 3)})
            else:
                out.append(p)
        return out

    def _delete(self):
        k = self._sel()
        if k is None or len(self.points) <= 1:
            self.lbl_status.config(text=t("et_need_one"), fg="#a01000", bg="#ffecea")
            return
        abs_now = ew.resolve(self.p2x, self.p2z, self.points)
        pts = [dict(p) for p in self.points]
        pts.pop(k)
        # the survivors keep their absolute places
        out = []
        for idx, p in enumerate(pts):
            old = idx if idx < k else idx + 1
            if p["anchor"] == "prev":
                ax, az = abs_now[old]
                out.append({**p, "anchor": "p2",
                            "dx": round(ax - self.p2x, 3),
                            "dz": round(az - self.p2z, 3)})
            else:
                out.append(p)
        self._try(out, t("et_what_del").format(n=k + 1))

    def _reseed(self):
        if not messagebox.askyesno(t("et_title_seed"), t("et_confirm_seed"), parent=self):
            return
        self._try(self._seed_from_current_path(), t("et_what_seed"))

    def _clear(self):
        if not messagebox.askyesno(t("et_title_clear"), t("et_confirm_clear"), parent=self):
            return
        self.points = []
        self._refresh()

    # ── preview ────────────────────────────────────────────────────────
    def _draw(self):
        c = self.preview
        c.delete("all")
        W = c.winfo_width() or 780
        H = c.winfo_height() or 190
        g = self._geom()
        abs_pts = ew.resolve(self.p2x, self.p2z, self.points)
        curve = ew.build_curve(self.p2x, self.p2z, self.points, shape=self._shape())

        xs = [self.p2x] + [p[0] for p in abs_pts]
        zs = [self.p2z] + [p[1] for p in abs_pts]
        if len(curve):
            xs += list(curve[:, 0]); zs += list(curve[:, 2])
        if not xs:
            return
        x0, x1 = min(xs), max(xs)
        z0, z1 = min(zs), max(zs)
        pad = max((x1 - x0), (z1 - z0)) * 0.18 + 3.0
        x0 -= pad; x1 += pad; z0 -= pad; z1 += pad

        # #102: this window used to draw X across and Z up, while the pass table
        # drew Z across and X up — the same pass, axes swapped, and this one
        # never applied the machine-side mirror either. Both now lay out through
        # the shared helper, which takes its orientation from the 3D camera.
        # (z0/z1 above stay CAM Z: the clearance contour below sweeps real Z.)
        _or = self._orient
        _corners = [preview_orient.to_plane(_or, x, z)
                    for x in (x0, x1) for z in (z0, z1)]
        h0 = min(p[0] for p in _corners); h1 = max(p[0] for p in _corners)
        v0 = min(p[1] for p in _corners); v1 = max(p[1] for p in _corners)
        s = min((W - 40) / max(h1 - h0, 1e-6), (H - 30) / max(v1 - v0, 1e-6))

        def to_c(x, z):
            h, v = preview_orient.to_plane(_or, x, z)
            return (20 + (h - h0) * s, H - 15 - (v - v0) * s)

        # clearance contour — the line the tail may not cross
        if g is not None:
            radius_at, center_x, base = g
            need = self._clearance()
            prev = None
            for zz in np.linspace(z0, z1, 90):
                r = radius_at(float(zz))
                if r is None:
                    prev = None
                    continue
                px = center_x + (r + base + need)
                pt = to_c(px, zz)
                if prev:
                    c.create_line(*prev, *pt, fill="#8b3a3a", dash=(3, 3))
                prev = pt

        if len(curve) > 1:
            flat = []
            for x, _y, z in curve:
                flat.extend(to_c(x, z))
            c.create_line(*flat, fill="#5fd0ff", width=2, smooth=False)

        px, pz = to_c(self.p2x, self.p2z)
        c.create_oval(px - 4, pz - 4, px + 4, pz + 4, fill="#ffd24a", outline="")
        c.create_text(px + 12, pz - 8, text="P2", fill="#ffd24a", anchor="w",
                      font=("Segoe UI", 8))

        sel = self._sel()
        for k, (ax, az) in enumerate(abs_pts):
            cx, cz = to_c(ax, az)
            last = (k == len(abs_pts) - 1)
            col = "#7CFFB2" if last else "#ffffff"
            r = 6 if k == sel else 4
            c.create_oval(cx - r, cz - r, cx + r, cz + r, fill=col, outline="#0e141b")
            c.create_text(cx, cz - 12, text=str(k + 1), fill=col,
                          font=("Segoe UI", 8, "bold"))
        if abs_pts:
            ex, ez = to_c(*abs_pts[-1])
            c.create_text(ex + 14, ez + 10, text=t("et_end_marker"), fill="#7CFFB2",
                          anchor="w", font=("Segoe UI", 8))

    # ── commit ─────────────────────────────────────────────────────────
    def _ok(self):
        bad = self._violations(self.points)
        if bad:
            # Should be unreachable (every edit is checked), but the geometry can
            # change under a dialog left open — never write a known gouge.
            messagebox.showerror(t("et_title"), t("et_refused_commit"), parent=self)
            return
        self.on_apply(list(self.points), self._shape())
        self.destroy()
