# -*- coding: utf-8 -*-
"""TODO #102 — per-pass editor for break points on the exit leg.

Opened from the pass table for ONE pass. Each row is "at X % along the exit,
bend the rest by Y degrees" — the thing operators were already doing with the
single `exit_mid_t` / `exit_mid_rotation` pair, now as a list.

WHY THERE IS NO 3D PREVIEW HERE, unlike the waypoint editor: a break is a
position along a leg the operation already defines, not a point in space. The
numbers ARE the shape, and the pass table and 3D view behind this window redraw
as soon as it is applied.

THE RAMP (user, 2026-08-28). "Apply to all passes" writes the same list to every
pass. With the ramp on, each row instead walks from its Angle on the first pass
to its "@ last pass" angle on the last one, in equal steps — the same arithmetic
as the pass table's Progressive button (`pass_table.py:789`), which is the fill
idiom operators already know.

The ramp is an AUTHORING action, not a stored mode: it writes N concrete lists
and is then finished. That is deliberate — the engine keeps one meaning for
`exit_breaks` (this pass bends by these angles) instead of gaining a second,
pass-count-dependent one, and an operator can always fix up a single pass
afterwards without fighting a rule that regenerates it.

CLEARANCE IS ADVISORY HERE, not a refusal — the opposite of the waypoint editor,
and for a reason. A waypoint IS a position, so a bad one is simply wrong and can
be rejected on the spot. A break is a rotation applied to a leg the engine builds
later; if it swings the tail into the part, the engine's safety floor pushes the
whole pass outward and nothing is gouged. That is safe but surprising — the
contact point moves with it — so this window says so rather than either refusing
a legal edit or letting the pass quietly relocate.
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import numpy as np

import exit_breaks as eb
import exit_waypoints as ew
from i18n import t
from logger_config import logger
from ui import dialog_sizing


class BreakPointsDialog(tk.Toplevel):
    def __init__(self, parent, app, op_index, pass_index, on_apply):
        super().__init__(parent)
        self.app = app
        self.op_index = op_index
        self.pass_index = pass_index
        self.on_apply = on_apply

        op = self._op() or {}
        self.n_passes = max(1, int(op.get("count", 1) or 1))
        self.title(t("bp_title").format(
            name=op.get("name") or op.get("type", "?"), i=pass_index + 1))
        dialog_sizing.fit(self, 720, 480)
        self.transient(parent)

        # Seeded, never blank — same rule as the waypoint editor. A pass with no
        # list of its own shows the op's legacy single break, which is what it is
        # ACTUALLY running right now; pressing OK is what converts it.
        # `has_own_list`, not `stored()`: a pass that was emptied on purpose has a
        # stored list that is empty, and asking the truthiness of that would call
        # it legacy-seeded. It happens to come out right today only because
        # `self.rows` is empty too — a coincidence, not a reason.
        self.rows = [dict(r, ramp=None) for r in eb.get_breaks(op, pass_index)]
        self._seeded_legacy = bool(self.rows) and not eb.has_own_list(op, pass_index)

        # OK / Cancel is packed FIRST, to the bottom (#103). Tk hands out space
        # in packing order, so on a screen too small for the content it is
        # whatever was packed LAST that gets squeezed off — in a dialog built
        # top-down, always the buttons. Reserving their space here makes the
        # table above shrink instead. The bar is filled in further down.
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", padx=6, pady=6)

        tk.Label(self, text=t("bp_help"), anchor="w", justify="left",
                 fg="#446688", wraplength=690).pack(fill="x", padx=8, pady=(8, 4))

        cols = ("n", "pos", "angle", "ramp")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=9)
        for c, (head, w) in zip(cols, (("№", 40), (t("bp_col_pos"), 150),
                                       (t("bp_col_angle"), 150),
                                       (t("bp_col_ramp"), 200))):
            self.tree.heading(c, text=head)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self.tree.bind("<Double-1>", self._on_double_click)

        row = ttk.Frame(self)
        row.pack(fill="x", padx=6)
        ttk.Button(row, text=t("bp_btn_add"), command=self._add).pack(side="left", padx=2)
        ttk.Button(row, text=t("bp_btn_del"), command=self._delete).pack(side="left", padx=2)
        ttk.Button(row, text=t("bp_btn_clear"), command=self._clear).pack(side="left", padx=8)

        scope = ttk.Frame(self)
        scope.pack(fill="x", padx=6, pady=(8, 0))
        ttk.Label(scope, text=t("bp_scope")).pack(side="left")
        self.scope_var = tk.StringVar(value="this")
        ttk.Radiobutton(scope, text=t("bp_scope_this"), value="this",
                        variable=self.scope_var, command=self._sync_ramp
                        ).pack(side="left", padx=(6, 0))
        ttk.Radiobutton(scope, text=t("bp_scope_all").format(n=self.n_passes),
                        value="all", variable=self.scope_var, command=self._sync_ramp
                        ).pack(side="left", padx=(6, 0))
        self.ramp_var = tk.BooleanVar(value=False)
        self.chk_ramp = ttk.Checkbutton(scope, text=t("bp_ramp_on"),
                                        variable=self.ramp_var, command=self._sync_ramp)
        self.chk_ramp.pack(side="left", padx=(16, 0))

        self.lbl_status = tk.Label(self, anchor="w", justify="left", fg="#204060",
                                   bg="#eef3f8", relief="groove", bd=1,
                                   wraplength=690)
        self.lbl_status.pack(fill="x", padx=6, pady=(8, 0))

        ttk.Button(bar, text=t("bp_btn_ok"), command=self._ok).pack(side="right", padx=2)
        ttk.Button(bar, text=t("bp_btn_cancel"), command=self.destroy).pack(side="right", padx=2)

        self._sync_ramp()
        self._refresh()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ── data ───────────────────────────────────────────────────────────
    def _op(self):
        ops = self.app.params.get("operations", [])
        return ops[self.op_index] if self.op_index < len(ops) else None

    def _clean_full(self):
        """Rows normalized ONE AT A TIME, each keeping its own ramp end.

        Normalizing the list wholesale would sort and possibly drop rows, and
        then the ramp column — read from `self.rows` by index — would be paired
        with the wrong break. Normalizing per row keeps the pairing structural
        instead of relying on the two lists happening to stay in step.
        """
        out = []
        for r in self.rows:
            n = eb.normalize([{"t": r["t"], "angle": r["angle"]}])
            if n:
                out.append(dict(n[0], ramp=r.get("ramp")))
        out.sort(key=lambda d: d["t"])
        return out

    def _clean(self):
        """The rows as the engine would see them (no ramp field)."""
        return [{"t": r["t"], "angle": r["angle"]} for r in self._clean_full()]

    # ── ramp availability ──────────────────────────────────────────────
    def _sync_ramp(self):
        """The ramp only means anything across passes, so it follows the scope.

        Greying it out (rather than silently ignoring it) is what stops an
        operator filling in a whole column that will never be read.
        """
        can_ramp = self.scope_var.get() == "all" and self.n_passes >= 2
        self.chk_ramp.state(["!disabled"] if can_ramp else ["disabled"])
        if not can_ramp:
            self.ramp_var.set(False)
        self._refresh()

    def _ramping(self):
        return bool(self.ramp_var.get()) and self.scope_var.get() == "all" \
            and self.n_passes >= 2

    # ── table ──────────────────────────────────────────────────────────
    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        ramping = self._ramping()
        for k, r in enumerate(self.rows):
            ramp = "" if not ramping else (
                f"{r['angle']:.1f}" if r.get("ramp") is None else f"{r['ramp']:.1f}")
            self.tree.insert("", "end", iid=str(k), values=(
                k + 1, f"{r['t'] * 100:.0f}", f"{r['angle']:.1f}", ramp))
        self._status()

    def _status(self, extra=None, bad=False):
        parts = []
        if extra:
            parts.append(extra)
        if not self.rows:
            parts.append(t("bp_hint_empty"))
        else:
            parts.append(t("bp_hint").format(n=len(self.rows)))
            if len(self.rows) > eb.MAX_BREAKS:
                parts.append(t("bp_too_many").format(n=len(self.rows), max=eb.MAX_BREAKS))
        if self._ramping():
            parts.append(t("bp_ramp_hint").format(n=self.n_passes))
        if self._seeded_legacy and self.rows:
            r = self.rows[0]
            parts.append(t("bp_legacy_seed").format(t=f"{r['t'] * 100:.0f}",
                                                    a=f"{r['angle']:.1f}"))
        warn = None if bad else self._clearance_warning()
        if warn:
            parts.append(warn)
        hot = bad or bool(warn)
        self.lbl_status.config(text="  ".join(parts),
                               fg="#a01000" if hot else "#204060",
                               bg="#ffecea" if hot else "#eef3f8")

    # ── advisory clearance ─────────────────────────────────────────────
    def _clearance_warning(self):
        """Bend THIS pass's real exit leg and see whether it still clears.

        Reuses the leg the engine last calculated (the seeding trick from the
        waypoint editor) rather than re-deriving the shape, so bow / arc / plain
        line are all covered, and reuses `exit_waypoints.check_clearance` for the
        measurement so there is one implementation of "too close".

        Advisory only — see the module docstring. Any failure here returns None:
        an advisory that cannot be computed must never block an edit.
        """
        rows = self._clean()
        if not rows:
            return None
        try:
            leg = self._current_leg()
            if leg is None or len(leg) < 3:
                return None
            mgr = getattr(self.app, "mandrel_mgr", None)
            if mgr is None:
                return None
            p = self.app.params
            op = self._op() or {}
            m_min = mgr.props.get("min_z", float("-inf"))
            m_top = mgr.props.get("top_z", float("inf"))

            def radius_at(z, _a=m_min, _b=m_top):
                return None if (z < _a or z > _b) else mgr.get_radius_fast(z)

            base = (float(p.get("final_part_thickness_on_mandrel", 2.0))
                    + float(p.get("shell_thickness", 0.0))
                    + float(op.get("r_tool", 25.0)))
            need = self._clearance()
            bad = ew.check_clearance(eb.apply(leg, rows), radius_at,
                                     float(p.get("mandrel_pos_x_offset", 0.0)),
                                     base, need)
            if not bad:
                return None
            # Which break is responsible: the last one before the violation.
            frac = bad[0]["index"] / max(len(leg) - 1, 1)
            return t("bp_clear_warn").format(
                pct=f"{min(frac, 1.0) * 100:.0f}", got=f"{bad[0]['clearance']:.2f}",
                need=f"{need:.2f}")
        except Exception as e:
            logger.debug(f"#102 clearance advisory unavailable: {e}")
            return None

    def _current_leg(self):
        """This pass's exit leg from the last calculation, in CANONICAL X.

        `last_calculated_paths` is in MACHINE X — the engine mirrors it at the end
        of `calculate_paths` for a negative-side machine. The breaks are applied
        in canonical space, so the leg has to be mirrored back first or the
        advisory measures a tail on the wrong side of the axis (the exact bug
        #100 hit, see exit_tail_dialog._to_canonical).
        """
        pg = getattr(self.app, "path_gen", None)
        if pg is None:
            return None
        paths = getattr(pg, "last_calculated_paths", None) or []
        idxs = [k for k, o in enumerate(getattr(pg, "_path_op_map", []))
                if o is self._op()]
        if not idxs or self.pass_index >= len(idxs):
            return None
        pi = idxs[self.pass_index]
        if pi >= len(paths):
            return None
        path = np.asarray(paths[pi], dtype=float)
        split = (getattr(pg, "last_render_split_idx", {}) or {}).get(pi)
        if split is not None:
            leg = path[split[1]:]
        else:
            # A reverse pass is stored back-to-front and the engine drops its
            # split index, so the exit leg is the array's HEAD, read backwards.
            # `last_reverse_split_idx` carries the remapped pair for exactly this.
            rev = (getattr(pg, "last_reverse_split_idx", {}) or {}).get(pi)
            if rev is None:
                # Not "assume the whole path is the leg" — that measured the
                # advisory across the approach arm too AND re-applied breaks the
                # array already contained. No leg means no advisory.
                return None
            leg = path[:rev[0] + 1][::-1]
        if len(leg) < 3:
            return None
        p = getattr(self.app, "params", {}) or {}
        if not p.get("roller_positive_x_side", True):
            leg = leg.copy()
            leg[:, 0] = 2.0 * float(p.get("mandrel_pos_x_offset", 0.0)) - leg[:, 0]
        return leg

    def _clearance(self):
        """What this pass must keep clear — the same resolution chain the engine,
        the pass table and the waypoint editor use."""
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

    # ── editing ────────────────────────────────────────────────────────
    def _sel(self):
        s = self.tree.selection()
        return int(s[0]) if s else None

    def _num(self, s):
        try:
            return float(str(s).replace(",", "."))
        except (TypeError, ValueError):
            self._status(t("bp_bad_number").format(v=s), bad=True)
            return None

    def _on_double_click(self, event):
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not iid or not col:
            return
        k = int(iid)
        if col == "#2":
            self._edit_pos(k)
        elif col == "#3":
            self._edit_angle(k)
        elif col == "#4" and self._ramping():
            self._edit_ramp(k)

    def _edit_pos(self, k):
        val = simpledialog.askstring(
            t("bp_edit_title"),
            t("bp_edit_pos").format(n=k + 1, a=int(eb.T_MIN * 100), b=int(eb.T_MAX * 100)),
            initialvalue=f"{self.rows[k]['t'] * 100:.0f}", parent=self)
        if val is None:
            return
        v = self._num(val)
        if v is None:
            return
        want = v / 100.0
        got = min(max(want, eb.T_MIN), eb.T_MAX)
        self.rows[k]["t"] = got
        self.rows.sort(key=lambda r: r["t"])
        self._refresh()
        if abs(got - want) > 1e-9:
            self._status(t("bp_pos_clamped").format(v=f"{got * 100:.0f}"))

    def _edit_angle(self, k):
        val = simpledialog.askstring(
            t("bp_edit_title"), t("bp_edit_angle").format(n=k + 1),
            initialvalue=f"{self.rows[k]['angle']:.1f}", parent=self)
        if val is None:
            return
        v = self._num(val)
        if v is None:
            return
        self.rows[k]["angle"] = v
        self._refresh()

    def _edit_ramp(self, k):
        cur = self.rows[k].get("ramp")
        val = simpledialog.askstring(
            t("bp_edit_title"), t("bp_edit_ramp").format(n=k + 1),
            initialvalue="" if cur is None else f"{cur:.1f}", parent=self)
        if val is None:
            return
        val = val.strip()
        if val == "":
            self.rows[k]["ramp"] = None
        else:
            v = self._num(val)
            if v is None:
                return
            self.rows[k]["ramp"] = v
        self._refresh()

    def _add(self):
        """A new break goes halfway between its neighbours, at 0° — so adding a
        row never changes the cut until an angle is typed."""
        rows = self.rows
        if not rows:
            new_t = 0.5
        else:
            k = self._sel()
            at = len(rows) - 1 if k is None else k
            nxt = rows[at + 1]["t"] if at + 1 < len(rows) else eb.T_MAX
            new_t = min(max((rows[at]["t"] + nxt) / 2.0, eb.T_MIN), eb.T_MAX)
        rows.append({"t": new_t, "angle": 0.0, "ramp": None})
        rows.sort(key=lambda r: r["t"])
        self._refresh()

    def _delete(self):
        k = self._sel()
        if k is None or k >= len(self.rows):
            return
        self.rows.pop(k)
        self._refresh()

    def _clear(self):
        if self.rows and not messagebox.askyesno(t("bp_edit_title"),
                                                 t("bp_clear_confirm"), parent=self):
            return
        self.rows = []
        self._seeded_legacy = False
        self._refresh()

    # ── apply ──────────────────────────────────────────────────────────
    def _ok(self):
        full = self._clean_full()
        rows = [{"t": r["t"], "angle": r["angle"]} for r in full]
        if self.scope_var.get() != "all":
            self.on_apply({self.pass_index: rows})
            self.destroy()
            return

        n = self.n_passes
        if self._ramping():
            # Same arithmetic as the pass table's Progressive fill: the row's
            # Angle on pass 1, its "@ last pass" angle on pass n, equal steps
            # between. A row with no ramp end stays constant across all passes.
            per_pass = {}
            for i in range(n):
                f = i / (n - 1)
                per_pass[i] = [
                    {"t": r["t"],
                     "angle": round(r["angle"]
                                    + ((r["ramp"] if r["ramp"] is not None
                                        else r["angle"]) - r["angle"]) * f, 4)}
                    for r in full]
        else:
            per_pass = {i: [dict(r) for r in rows] for i in range(n)}

        self.on_apply(per_pass)
        self.destroy()
