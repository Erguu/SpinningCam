"""User-facing changelog, shown once per new version on startup (see
``ui/dialogs/changelog_window.py``).

Keyed by version string. When you bump ``version.APP_VERSION``, add the matching entry
here with short, operator-facing bullet lines (what changed, not how it was coded).
"""

CHANGELOG = {
    "1.008": [
        "SCL export now writes a Turret / Tool Table into every recipe header, so the PLC takes its tool-slot setup straight from the downloaded recipe instead of an HMI-entered mapping. Set it up in Machine ▸ Turret / Tool Table: enter the tool code in each of the 4 slots (0 = empty), or press 'Populate from tool library' to fill them from your tools automatically.",
        "Turret angles: tick 'Auto-space angles' to let the PLC space them evenly (3 slots → 0/120/240), or untick it to type your own measured slot angles.",
        "Safety: if a program uses a tool that isn't assigned to any turret slot, SCL export is now blocked with a clear message (prevents the machine rotating to the wrong tool). Note: recipes generated before this version have no tool table and must be re-exported.",
        "The Tool window now warns and blocks a tool whose ID number is over 255 or 0 — the PLC tool code is a single byte (1–255), and this stops a mistyped code from being silently clamped in the recipe.",
        "A tool's Color now actually shows on the roller during simulation (it was always orange before), and the Color field is a drop-down of named colors plus a custom picker so the options are clear.",
    ],
    "1.007": [
        "Unite: the opposite of Split — select two or more operations (right-click → Unite) to combine them into one. They need not be next to each other; any operations between the picks are kept and slide to after the united operation. Re-joining the adjacent chunks of an earlier Split reproduces the original operation exactly and applies silently.",
        "When the operations you unite differ, a resolver dialog lets YOU choose how each conflicting field is combined — Start/End Z, Pass Angle, Reach, Tilt, Clearance and any other differing setting each get a drop-down (Ramp first→last, or First / Last / Average; Min / Max for Z when picks are out of order). Every default reproduces the automatic merge, so OK just accepts it. Only same-type, same-tool operations can be united, and one Ctrl+Z undoes it.",
        "PLC Auto-tune (Machine tab → PLC Output Mode): tick 'Auto-tune tolerance to line limit' and set a Target Max Lines. On SCL export the point-reduction tolerance is fitted automatically to keep the program under your PLC's line budget — no more hand-tuning the tolerance or answering the array-size prompt.",
        "Auto-tune is safety-guarded: it never lets the simplified path come closer to the mandrel than the normal full-resolution G-code (clearance is measured along the actual straight moves, so a decimated corner-cut is caught). If your target can't be reached without reducing clearance, it warns instead of doing it silently.",
        "Before writing the file, Auto-tune now shows the chosen tolerance (manual → applied), the resulting line count vs. target, and the min clearance vs. the normal path, so you can review and cancel if you disagree.",
    ],
    "1.006": [
        "Camera: every viewing angle is now reachable with the on-screen buttons — no more angles you could only get with the mouse. Separate Horizontal, Vertical, Roll and Zoom buttons (fine ±5° and coarse ±15°).",
        "Camera views now STICK — buttons and presets no longer snap back when the scene redraws.",
        "Fixed vertical tilt flipping upside-down / getting stuck near the top or bottom (it now rotates smoothly all the way around in every direction).",
        "Fixed the Horizontal and Vertical buttons acting swapped/reversed; arrows now match the on-screen motion.",
        "Saved Views: store any number of your own named camera angles with '＋ Save current view…', then recall (Go) or delete (✕) them. Saved views are remembered between sessions.",
        "Number keys 1-9 jump straight to your saved views (1 = first view, and so on). Works while looking at the 3D view; ignored while typing in a field.",
        "Customize…: an optional colored Border can now highlight a parameter's label in the editor, so key fields stand out.",
    ],
    "1.005": [
        "Undo / Redo for operation-list actions (↶/↷ buttons, Ctrl+Z / Ctrl+Y): Split, Delete, Move, Add, Continue ⤵, Reach⟲, Angle⟲, On/Off, library inserts and batch edits — up to 50 steps back.",
        "Batch edit: tick the new ☑ column (or Shift/Ctrl-select rows), then change ONE parameter on all targeted operations at once (+= add / = set / ×= scale) with a live old→new preview. The whole batch is a single undo step.",
        "Choose which parameters the batch dialog offers with the new 'Batch' checkbox in Customize….",
        "Copy duplicates the selected operations in place, ready to edit — no need to misuse 'Save as Default' for copying.",
        "Operations can now be given names (Name field, or right-click → Rename…); the name shows in the list.",
        "Right-click any operation row for a context menu with all row actions.",
        "Operation Library: save operations under names (as many per type as you like) and insert them into any program. Tool reach (Rr) is re-synced from the tool library on insert, so old entries stay safe.",
        "Reach controls simplified: a 'Reach source' selector (Manual / Follow blank). In follow mode the Reach field shows the LIVE auto value (greyed); switch back to Manual any time to unlock it.",
        "An exit-mode line now shows whether the pass exit is ANGULAR (Pass Angle + Reach) or RAW X/Z, and greys the P3 X/Z fields when the engine doesn't use them.",
        "The blank factor field only appears when it actually has an effect (follow-blank mode).",
        "Pass Diagram window: the formula panel now explains the whole reach/angle chain with the selected operation's live values.",
        "Fixes: the Reach display could go stale (showing your typed value while the auto value was used); Customize window checkbox columns now align properly.",
    ],
    "1.004": [
        "Reach authoring reworked: one 'Reach' value per pass, with End Reach / End Angle columns.",
        "Reach⟲ estimates the reach from the remaining blank flange and fills it in.",
        "'Reach follows blank' keeps the reach kissing the blank edge automatically as the end Z changes.",
        "Reach factor (×) biases the auto reach (e.g. 0.90 = stop at 90% of the flange).",
        "Angle⟲ fills the progressive fan-end angle from the mandrel surface (no more assuming 180°).",
        "Continue ⤵ starts a new operation from the previous op's end position / angle / reach.",
        "Split… breaks one multi-pass operation into editable chunk operations.",
        "Clamp-zone warning + 3D band marks the counter-press region that must not be machined.",
        "Pass Info now lists each pass's reach |P2→P3|.",
        "Fixes: the exit no longer folds past 180° or overlaps near the flange; End Angle is shown in your pass-angle frame.",
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
