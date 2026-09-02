# -*- coding: utf-8 -*-
"""Compare two passes side by side (#104).

Two pickers choose any two passes in the program — different operations and a
forward-vs-reverse pair included — and the table below shows every parameter of
both, with the differing rows marked. See pass_compare.py for the model; this
file is display and interaction only.

Editing (user decision 2026-09-02): double-click a value cell to change it.
Edits are STAGED and previewed live, exactly like the pass table, and nothing
touches the program until [Apply], which writes one undo snapshot. Where a
value could be written either as a per-pass pin or as the operation field, the
dialog ASKS rather than picking — an operator comparing pass 3 with pass 7 must
never change twelve passes without being told.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import pass_compare as pc
from i18n import t
from logger_config import logger
from ui import dialog_sizing

# Sentinel: "nothing staged for this cell". None is a real staged value
# ("clear this key / back to default"), so it cannot double as the miss marker.
_NOSTAGE = object()


class PassCompareDialog(tk.Toplevel):
    """Side-by-side pass comparison with staged edits (Apply / Cancel)."""

    def __init__(self, parent, app, program_tab, sel_a=None, sel_b=None):
        super().__init__(parent)
        self.app = app
        self.ptab = program_tab
        self.title(t("pc_title"))
        self.transient(parent)

        self.staged_ops = {}      # {op_index: {key: value}}
        self.staged_pins = {}     # {(op_index, pass_index): {key: value}}
        self._rows = []

        self._ops = pc.list_operations(app.params)
        if not self._ops:
            messagebox.showinfo(t("pc_title"), t("pc_no_ops"), parent=parent)
            self.destroy()
            return

        # Default B to the second pass of the same op, else the next op — so the
        # window opens on a real comparison rather than an op against itself.
        first = (self._ops[0]["op_index"], 0)
        second = ((self._ops[0]["op_index"], 1) if self._ops[0]["n"] > 1
                  else (self._ops[min(1, len(self._ops) - 1)]["op_index"], 0))
        self.sel_a = self._valid(sel_a) or first
        self.sel_b = self._valid(sel_b) or second

        # Button bar packed FIRST, to the bottom (#103): Tk squeezes whatever
        # was packed LAST when the window is short, and in a top-down dialog
        # that is always the row holding [Apply].
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", padx=6, pady=6)

        tk.Label(self, text=t("pc_help"), anchor="w", justify="left",
                 fg="#446688", wraplength=900).pack(fill="x", padx=8, pady=(8, 2))

        self._build_pickers()
        self._build_table()

        self.lbl_foot = tk.Label(self, anchor="w", justify="left", fg="#446688")
        self.lbl_foot.pack(fill="x", padx=8, pady=(2, 0))

        self.lbl_explain = tk.Label(self, anchor="w", justify="left", fg="#204060",
                                    bg="#eef3f8", relief="groove", bd=1,
                                    wraplength=900, text=t("pc_explain_hint"))
        self.lbl_explain.pack(fill="x", padx=6, pady=(4, 0))

        self.btn_apply = ttk.Button(bar, text=t("pt_btn_apply"), command=self._apply)
        self.btn_apply.pack(side="right", padx=2)
        ttk.Button(bar, text=t("pt_btn_cancel"), command=self._cancel).pack(side="right", padx=2)
        ttk.Button(bar, text=t("pc_btn_swap"), command=self._swap).pack(side="left", padx=2)
        ttk.Button(bar, text=t("pc_btn_copy"), command=self._copy).pack(side="left", padx=2)
        ttk.Button(bar, text=t("pt_btn_refresh"), command=self.refresh).pack(side="left", padx=2)

        dialog_sizing.fit(self, 980, 660)
        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    # ── selection plumbing ────────────────────────────────────────────────
    def _op_row(self, op_index):
        return next((o for o in self._ops if o["op_index"] == op_index), None)

    def _valid(self, sel):
        """A seed (op, pass) clamped onto a real pass, or None."""
        try:
            oi, pi = sel
        except (TypeError, ValueError):
            return None
        row = self._op_row(oi)
        if row is None:
            return None
        return (oi, max(0, min(int(pi), row["n"] - 1)))

    def _set_sel(self, side, sel):
        if side == "a":
            self.sel_a = sel
        else:
            self.sel_b = sel

    def _build_pickers(self):
        """Two steps per side: OPERATION, then the pass inside it.

        One flat combobox listing every pass in the program (the first cut) is
        readable with three operations and hopeless with twenty — the operator
        has to scan a list whose length is the whole program to find one pass
        (user 2026-09-02). Picking the operation first cuts the second list to
        that operation's own pass count, which is never more than a dozen.
        """
        outer = ttk.Frame(self)
        outer.pack(fill="x", padx=6, pady=(4, 2))
        op_labels = [o["label"] for o in self._ops]
        self._pick = {}

        for side in ("a", "b"):
            f = ttk.Frame(outer)
            f.pack(fill="x", pady=1)
            if side == "a":
                # Packed FIRST so it keeps its width: Tk squeezes whatever was
                # packed LAST, and a long operation name would otherwise push
                # the filter off the right edge (#103's lesson, sideways).
                self.var_only_diff = tk.BooleanVar(value=False)
                ttk.Checkbutton(f, text=t("pc_only_diff"),
                                variable=self.var_only_diff,
                                command=self.refresh).pack(side="right", padx=(10, 4))

            ttk.Label(f, text=t("pc_pass_a" if side == "a" else "pc_pass_b"),
                      width=8).pack(side="left")
            v_op = tk.StringVar()
            cb_op = ttk.Combobox(f, values=op_labels, textvariable=v_op,
                                 state="readonly", width=38)
            cb_op.pack(side="left", padx=(0, 8))
            cb_op.bind("<<ComboboxSelected>>", lambda _e, s=side: self._on_op_pick(s))

            ttk.Label(f, text=t("pc_pick_pass")).pack(side="left")
            v_p = tk.StringVar()
            cb_p = ttk.Combobox(f, textvariable=v_p, state="readonly", width=9)
            cb_p.pack(side="left", padx=(4, 0))
            cb_p.bind("<<ComboboxSelected>>", lambda _e, s=side: self._on_pass_pick(s))

            self._pick[side] = {"op": v_op, "pass": v_p, "cb_pass": cb_p}
        self._sync_pickers()

    def _sync_pickers(self):
        """Push self.sel_a / self.sel_b into the four comboboxes."""
        for side in ("a", "b"):
            oi, pi = self._sel(side)
            row = self._op_row(oi)
            w = self._pick.get(side)
            if row is None or w is None:
                continue
            w["op"].set(row["label"])
            choices = pc.pass_choices(row["n"])
            w["cb_pass"]["values"] = choices
            w["pass"].set(choices[max(0, min(pi, len(choices) - 1))])
            # A single-pass operation (cutting/bending, or count=1) has nothing
            # to choose: showing a live dropdown there invites a click that
            # cannot do anything.
            w["cb_pass"].state(["disabled"] if len(choices) < 2 else ["!disabled"])

    def _on_op_pick(self, side):
        labels = [o["label"] for o in self._ops]
        try:
            row = self._ops[labels.index(self._pick[side]["op"].get())]
        except (ValueError, KeyError):
            return
        # KEEP the pass number where it fits: stepping through operations to
        # compare their pass 3 is the common move, and resetting to pass 1 on
        # every hop would undo it each time.
        _oi, pi = self._sel(side)
        self._set_sel(side, (row["op_index"], min(pi, row["n"] - 1)))
        self._sync_pickers()
        self.refresh()

    def _on_pass_pick(self, side):
        oi, _pi = self._sel(side)
        row = self._op_row(oi)
        if row is None:
            return
        try:
            pi = pc.pass_choices(row["n"]).index(self._pick[side]["pass"].get())
        except (ValueError, KeyError):
            return
        self._set_sel(side, (oi, pi))
        self.refresh()

    def _swap(self):
        self.sel_a, self.sel_b = self.sel_b, self.sel_a
        self._sync_pickers()
        self.refresh()

    # ── table ─────────────────────────────────────────────────────────────
    def _build_table(self):
        cols = ("param", "a", "b", "delta")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=20)
        heads = {"param": (t("pc_col_param"), 210), "a": (t("pc_col_a"), 230),
                 "b": (t("pc_col_b"), 230), "delta": (t("pc_col_delta"), 90)}
        for c in cols:
            self.tree.heading(c, text=heads[c][0])
            self.tree.column(c, width=heads[c][1], anchor="w" if c == "param" else "center",
                             stretch=(c in ("a", "b")))
        # A section header is a row, not a widget: it has to scroll with what it
        # heads, and Treeview has nowhere else to put it.
        self.tree.tag_configure("header", background="#dde5ee", foreground="#123",
                                font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("diff", background="#fff3d0")
        self.tree.tag_configure("staged", background="#ffe0b0", foreground="#7a3b00")
        self.tree.tag_configure("same", foreground="#667788")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 6), pady=(6, 0))
        self.tree.pack(fill="both", expand=True, padx=(6, 0), pady=(6, 0))
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<ButtonRelease-1>", self._on_click, add="+")

    def _tools(self):
        return getattr(self.app, "tool_library", None) or []

    def _tilt_arm(self):
        ad = getattr(self.app, "active_adapter", None)
        try:
            return ad is not None and ad.get_kinematics() == "tilt_arm"
        except Exception:
            return False

    def refresh(self):
        try:
            self._rows = pc.build_rows(
                self.app.params, self.app.mandrel_mgr, self.sel_a, self.sel_b,
                gui_overrides=getattr(self.app, "gui_pass_overrides", {}),
                staged_ops=self.staged_ops, staged_pins=self.staged_pins,
                tools=self._tools(), tilt_arm=self._tilt_arm())
        except Exception as e:
            logger.warning(f"#104 compare build failed: {e}")
            self._rows = []
        only = self.var_only_diff.get()
        self.tree.delete(*self.tree.get_children())
        n_diff = n_total = 0
        for k, r in enumerate(self._rows):
            if r["kind"] == "header":
                # Suppress a section whose every row was filtered out, so
                # "Only differences" cannot leave a bare heading behind.
                if only and not self._section_has_diff(k):
                    continue
                self.tree.insert("", "end", iid=str(k), tags=("header",),
                                 values=(r["label"], "", "", ""))
                continue
            n_total += 1
            if r["differs"]:
                n_diff += 1
            elif only:
                continue
            st_a = self._staged_value(r, "a") is not _NOSTAGE
            st_b = self._staged_value(r, "b") is not _NOSTAGE
            tags = ["staged"] if (st_a or st_b) else (["diff"] if r["differs"] else ["same"])
            # delta is already "●" when the values are not both numeric — don't
            # print the marker twice.
            mark = "" if not r["differs"] else (
                "●" if r["delta"] in ("", "●") else "● " + r["delta"])
            self.tree.insert("", "end", iid=str(k), tags=tuple(tags), values=(
                r["label"],
                self._cell(r, "a", st_a), self._cell(r, "b", st_b), mark))
        foot = [t("pc_foot_diffs").format(n=n_diff, total=n_total)]
        n_st = pc.staged_count(self.staged_ops, self.staged_pins)
        if n_st:
            foot.append(t("pc_foot_staged").format(n=n_st))
        self.lbl_foot.config(text="   •   ".join(foot))
        self.btn_apply.config(state="normal" if n_st else "disabled")

    def _section_has_diff(self, header_idx):
        for r in self._rows[header_idx + 1:]:
            if r["kind"] == "header":
                return False
            if r["differs"]:
                return True
        return False

    def _cell(self, r, side, staged):
        """Value text plus the two annotations that explain it.

        ``(fan)`` / ``(pin)`` is the priority-chain stage that produced an
        effective number — the whole point of the window is that two passes can
        show the same field with different provenance. ``(default)`` marks a
        value that is not stored on the op at all, so an operator does not go
        looking for a field that was never set.
        """
        val = r["a"] if side == "a" else r["b"]
        src = r["a_src"] if side == "a" else r["b_src"]
        is_def = r["is_default_a"] if side == "a" else r["is_default_b"]
        inert = r.get("inert_a" if side == "a" else "inert_b", False)
        txt = f"✎ {val}" if staged else val
        if src:
            # SHORT tag, not recipe_explain.source_label: that one is a
            # sentence fragment ("the operation setting") written for the
            # explanation bar, and in a cell it swamps the number it annotates.
            # The vocabulary matches the pass table's Source column.
            txt += f"  ({t('pc_src_' + src)})"
        elif is_def and not inert and val != "—":
            # "(not in use)" already says everything about an inert value;
            # stacking "(default)" on top of it just makes the cell unreadable.
            txt += f"  ({t('pc_default_mark')})"
        return txt

    # ── staged-value lookup ───────────────────────────────────────────────
    def _sel(self, side):
        return self.sel_a if side == "a" else self.sel_b

    def _staged_value(self, r, side):
        """The staged value for this cell, or _NOSTAGE. Checks BOTH destinations:
        an op-level stage shows on every pass of that op, including the other
        side of the comparison when both passes come from the same operation."""
        oi, pi = self._sel(side)
        key = r["key"]
        if r["section"] == "effective":
            key = r.get("pin_key") or key
        d = self.staged_pins.get((oi, pi)) or {}
        if key in d:
            return d[key]
        d = self.staged_ops.get(oi) or {}
        if key in d:
            return d[key]
        return _NOSTAGE

    # ── interactions ──────────────────────────────────────────────────────
    def _row_at(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return None, None
        try:
            r = self._rows[int(iid)]
        except (ValueError, IndexError):
            return None, None
        col = self.tree.identify_column(event.x)
        return r, {"#2": "a", "#3": "b"}.get(col)

    def _on_click(self, event):
        """Explain both sides of the clicked row (read-only)."""
        r, _side = self._row_at(event)
        if r is None or r["kind"] == "header":
            return
        field = pc.PROV_FIELD.get(r["key"]) if r["section"] == "effective" else None
        txt = ""
        if field:
            try:
                from recipe_explain import explain_field
                row_a, _ = self._pass_row("a")
                row_b, _ = self._pass_row("b")
                ea = explain_field(row_a, field) if row_a else ""
                eb = explain_field(row_b, field) if row_b else ""
                if ea or eb:
                    txt = t("pc_explain_pair").format(a=ea or "—", b=eb or "—")
            except Exception as e:
                logger.debug(f"#104 explain skipped: {e}")
        if not txt:
            txt = f"{r['label']} —  A: {r['a']}   B: {r['b']}" if r["differs"] \
                else t("pc_explain_hint")
        self.lbl_explain.config(text=txt,
                                fg="#c01000" if r["differs"] else "#204060",
                                bg="#ffecea" if r["differs"] else "#eef3f8")

    def _pass_row(self, side):
        oi, pi = self._sel(side)
        return pc.pass_row(self.app.params, self.app.mandrel_mgr, oi, pi,
                           gui_overrides=getattr(self.app, "gui_pass_overrides", {}),
                           staged_ops=self.staged_ops, staged_pins=self.staged_pins)

    def _op_at(self, side):
        oi, _pi = self._sel(side)
        ops = self.app.params.get("operations", [])
        return ops[oi] if 0 <= oi < len(ops) else {}

    def _on_double_click(self, event):
        r, side = self._row_at(event)
        if r is None or side is None or r["kind"] == "header":
            return
        if not r["editable"]:
            self.lbl_explain.config(text=t("pc_not_editable"), fg="#204060", bg="#eef3f8")
            return
        oi, pi = self._sel(side)
        op = self._op_at(side)
        op_type = op.get("type", "roughing")

        # A parameter outside this op type's universe has no cell to write into
        # on this side — the other side owns that row.
        if r["section"] == "operation":
            from ui.tabs.program_tab import OP_PARAM_UNIVERSE
            if r["key"] not in OP_PARAM_UNIVERSE.get(op_type, ()):
                messagebox.showinfo(t("pc_title"), t("pc_no_such_field"), parent=self)
                return

        scopes = pc.edit_scope_options(r, op_type)
        if not scopes:
            # Effective row on a non-roughing op: the engine reads no pin there,
            # so say so instead of silently doing nothing.
            messagebox.showinfo(t("pc_title"), t("pc_pin_rough_only"), parent=self)
            return

        scope = self._ask_scope(scopes, r, op, oi, pi)
        if scope is None:
            return

        key = (r.get("pin_key") or r["key"]) if scope == "pin" else r["key"]
        ok, value = self._ask_value(r, side)
        if not ok:
            return
        pc.stage_edit(self.staged_ops, self.staged_pins, scope, oi, pi, key, value)
        self.refresh()

    def _ask_scope(self, scopes, r, op, oi, pi):
        """Which destination to write to. None = the operator backed out.

        With one honest destination there is nothing to choose, but an op-wide
        write still gets a confirmation naming the operation and its pass count
        — that is the surprise this window would otherwise cause.
        """
        n = pc.pass_count(op)
        opname = op.get("name") or f"#{oi + 1} {op.get('type', 'roughing')}"
        if len(scopes) == 1:
            if scopes[0] == "pin" or n <= 1:
                return scopes[0]
            if not messagebox.askyesno(
                    t("pc_scope_title"),
                    t("pc_scope_op_only").format(label=r["label"], opname=opname, n=n),
                    parent=self):
                return None
            return "op"
        ans = messagebox.askyesnocancel(
            t("pc_scope_title"),
            t("pc_scope_q").format(label=r["label"], opname=opname, p=pi + 1, n=n),
            parent=self)
        if ans is None:
            return None
        return "pin" if ans else "op"

    def _ask_value(self, r, side):
        """Prompt for the new value. Returns (ok, value); value None = clear."""
        cur = self._staged_value(r, side)
        if cur is _NOSTAGE:
            cur = r["a_raw"] if side == "a" else r["b_raw"]
        if isinstance(cur, bool):
            cur = t("pc_yes") if cur else t("pc_no")
        prompt = t("pc_edit_prompt").format(
            side=t("pc_col_a") if side == "a" else t("pc_col_b"), label=r["label"])
        if r["kind"] == "enum" and r["choices"]:
            prompt += "\n" + t("pc_edit_choices").format(opts=" / ".join(r["choices"]))
        elif r["kind"] == "bool":
            prompt += "\n" + t("pc_edit_choices").format(
                opts=f"{t('pc_yes')} / {t('pc_no')}")
        txt = simpledialog.askstring(t("pc_title"), prompt,
                                     initialvalue="" if cur is None else str(cur),
                                     parent=self)
        if txt is None:
            return False, None
        ok, val = pc.parse_value(txt, r["kind"])
        if not ok:
            messagebox.showerror(t("pc_title"), t("pt_bad_number"), parent=self)
            return False, None
        if r["kind"] == "enum" and val is not None and val not in (r["choices"] or []):
            messagebox.showerror(
                t("pc_title"), t("pc_edit_choices").format(opts=" / ".join(r["choices"] or [])),
                parent=self)
            return False, None
        return True, val

    # ── commit ────────────────────────────────────────────────────────────
    def _apply(self):
        if not pc.staged_count(self.staged_ops, self.staged_pins):
            return
        # BEFORE the mutation: _push_undo snapshots the CURRENT ops list, so
        # pushing afterwards would record the already-changed state.
        try:
            self.ptab._push_undo(t("pc_undo_label"))
        except Exception as e:
            logger.debug(f"#104 undo snapshot skipped: {e}")
        pc.apply_edits(self.app.params, self.staged_ops, self.staged_pins)
        self.staged_ops, self.staged_pins = {}, {}
        try:
            self.ptab.refresh_ops_tree()
            self.ptab.on_op_select(None, _flush=False)
            self.ptab._schedule_auto_calc()
        except Exception as e:
            logger.debug(f"#104 post-apply refresh skipped: {e}")
        self.refresh()

    def _cancel(self):
        if pc.staged_count(self.staged_ops, self.staged_pins) and not messagebox.askyesno(
                t("pc_title"), t("pt_discard_confirm"), parent=self):
            return
        self.staged_ops, self.staged_pins = {}, {}
        self.destroy()

    def _copy(self):
        txt = pc.format_report(self._rows, only_diff=self.var_only_diff.get())
        try:
            self.clipboard_clear()
            self.clipboard_append(txt)
            self.lbl_explain.config(text=t("pc_copied"), fg="#204060", bg="#eef3f8")
        except Exception as e:
            logger.debug(f"#104 clipboard unavailable: {e}")
