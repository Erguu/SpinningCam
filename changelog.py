"""User-facing changelog, shown once per new version on startup (see
``ui/dialogs/changelog_window.py``).

Keyed by version string. When you bump ``version.APP_VERSION``, add the matching entry
here with short, operator-facing bullet lines (what changed, not how it was coded).
"""

CHANGELOG = {
    "1.010": [
        "Pass retract is now per operation (Program tab → Retract X/Z): every operation — roughing, finishing, cutting, bending — can retract by its own amount. The old global retract on the Machine tab was removed; existing programs are migrated so each operation keeps the retract it had before.",
        "New per-pass editor in the Pass Table (right-click an operation → Pass Table): edit P1_Z, Extend, Clearance, Angle and Reach for each pass. Use the Fill bar to change many at once — 'Set all' puts one value on every pass, 'Progressive' ramps smoothly from the first pass to the last. Set all P1_Z + Progressive Extend builds an anchored sweep (every pass starts at the same place and reaches a bit further). A live 2D preview at the bottom shows the passes as you edit.",
        "PDF export is now self-documenting: it lists the full operation parameters next to the toolpath plot, so you can compare two parameter sets side by side. When you export, a dialog lets you pick which parameters to include and remembers your choice for next time.",
        "The startup 'What's New' text is shorter and clearer.",
    ],
    "1.009": [
        "Tool-change position can now be set per operation (Program tab → Tool Change): retract to home (default), to an exact X/Z point, or to an offset from the last pass. Only affects operations whose tool differs from the one before.",
        "New 'Simultaneous XZ' option retracts both axes together in one diagonal move; the retract path is collision-checked and warns if a tool could strike the part (advisory only).",
        "Simulation now plays at the program's real feeds and rapid rate, pauses at each tool change to show which tool takes over, and the sim speed is a typed × multiplier with a 'Process time' readout.",
    ],
    "1.008": [
        "SCL export now writes a turret / tool table into every recipe header — set it up in Machine ▸ Turret / Tool Table, or auto-fill it from your tools.",
        "Export is blocked if a program uses a tool not assigned to a turret slot, and tool IDs are limited to 1–255. (Recipes made before this version have no tool table and must be re-exported.)",
        "A tool's color now shows on the roller during simulation, picked from a color drop-down.",
    ],
    "1.007": [
        "Unite (right-click → Unite) combines two or more operations into one — the opposite of Split. Re-joining split chunks restores the original exactly; when operations differ, a dialog lets you choose how each field merges.",
        "PLC Auto-tune (Machine tab) automatically fits the point-reduction tolerance to keep a program under your PLC's line limit, and never reduces clearance below the normal G-code (it warns instead).",
    ],
    "1.006": [
        "Camera controls overhauled: every angle is reachable with on-screen buttons (Horizontal / Vertical / Roll / Zoom), views no longer snap back, and the vertical-tilt and swapped-button bugs are fixed.",
        "Saved Views: store named camera angles and recall them with '＋ Save current view…' or number keys 1–9 (remembered between sessions).",
        "Customize… can now highlight a parameter's label with a colored border.",
    ],
    "1.005": [
        "Undo / Redo for operation-list actions (↶/↷, Ctrl+Z / Ctrl+Y) — up to 50 steps back.",
        "Batch edit one parameter across many operations at once (tick the ☑ column or select rows) as a single undo step; Copy duplicates operations in place; operations can now be named.",
        "Operation Library: save operations under names and reuse them in any program (tool reach re-synced on insert).",
        "Reach controls simplified: a Manual / Follow-blank selector, an exit-mode line, and a clearer Pass Diagram.",
    ],
    "1.004": [
        "Reach authoring reworked: one 'Reach' value per pass, a Reach⟲ estimate from the blank flange, 'Reach follows blank' to track the edge automatically, and a reach factor.",
        "Angle⟲ fills the fan-end angle from the mandrel surface; Continue ⤵ starts a new operation from the previous one's end; Split… breaks a multi-pass operation into editable chunks.",
        "Clamp-zone warning + 3D band marks the counter-press region that must not be machined.",
    ],
}


def _parse(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except (TypeError, ValueError):
        return (0,)


def entries_since(seen_version, current_version):
    """Return ``[(version, [lines]), ...]`` for every changelog version newer than
    ``seen_version`` up to and including ``current_version``, newest first. Empty when the
    user has already seen the current version."""
    seen, cur = _parse(seen_version), _parse(current_version)
    out = [(v, lines) for v, lines in CHANGELOG.items() if seen < _parse(v) <= cur]
    out.sort(key=lambda kv: _parse(kv[0]), reverse=True)
    return out
