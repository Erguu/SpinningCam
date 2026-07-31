"""User-facing changelog, shown once per new version on startup (see
``ui/dialogs/changelog_window.py``).

Keyed by version string. When you bump ``version.APP_VERSION``, add the matching entry
here with short, operator-facing bullet lines (what changed, not how it was coded).

An entry line is either:

* ``"plain string"`` — one bullet, rendered as it always was (versions up to 1.009);
* ``(title, detail, where)`` — preferred. ``title`` is a short bold headline (aim for
  one line), ``detail`` a sentence or two of grey text, ``where`` the click path to
  the thing (``"Program List ▸ right-click an operation ▸ Passes ▦"``). ``detail`` and
  ``where`` are optional, so ``(title,)`` and ``(title, detail)`` are valid.

One idea per line: prefer three short entries over one paragraph. Keep to BMP
characters (▸ ▦ ☑ are fine) — Tk 8.6 mishandles emoji such as 📍.
"""

CHANGELOG = {
    "1.015": [
        ("Bending and cutting now have a real start point and end point",
         "You typed a Z Position and a Plunge X, and that was it — there was no "
         "start, and no end you could see. The tool's starting point was derived "
         "behind your back from the Retract X field, which is why changing the "
         "retract changed how far the tool actually travelled under feed. Both "
         "ends are now ordinary fields you type: Start X/Z and End X/Z.",
         "Program List ▸ a cutting or bending operation"),
        ("Retract now only retracts, exactly like on a roughing pass",
         "It pulls the tool away after the move and has no effect on the distance "
         "travelled. Approach, tool change, speed and feed behave the same way "
         "they do on every other operation type.",
         "Program List ▸ a cutting or bending operation ▸ Retract X / Retract Z"),
        ("Bends can now run along Z, not just straight in",
         "Set End Z different from Start Z and the move goes diagonal or axial — "
         "what a flange bend usually needs. Leave them equal for the old purely "
         "radial plunge.",
         "Program List ▸ a cutting or bending operation ▸ End Z"),
        ("Cutting and bending finally show their Tool Change position",
         "The setting always worked on these operations — the machine honoured it "
         "in the generated program — but the fields were never drawn, so there was "
         "no way to set them. These are usually the operations that trigger the "
         "change, since they bring their own tool. Global / Absolute / Relative "
         "now appear here like on any other operation.",
         "Program List ▸ a cutting or bending operation ▸ Tool Change"),
        ("Your existing programs are converted on load and keep their exact path",
         "An old recipe's hidden start point is written out into the new Start X/Z "
         "fields, so the toolpath is identical — you can now see and change the "
         "number that was always there.",
         "File ▸ Open"),
    ],
    "1.014": [
        ("M-codes are no longer invisible",
         "Custom commands go into every program made for this machine but appeared "
         "nowhere you would look — not the operation list, not the PDF, not the "
         "checks. Preview & Analyze now lists every M-code the program will carry, "
         "in the order the machine runs them, each with its description. If a "
         "command you expected is missing, it shows up as a gap in that list.",
         "Help ▸ Preview & Analyze"),
        ("The back-support cylinder is one list instead of three places",
         "Its extend was a checkbox in its own section while the valve commands "
         "lived in a table further down — so the extend could be switched off "
         "while the valves kept firing at a cylinder that never came out. Extend, "
         "relax and retract are now ordinary rows in one list. Existing setups are "
         "converted automatically; nobody loses their extend.",
         "Machine ▸ Custom Commands"),
        ("New trigger: program start",
         "Fires at the very top of the program, before the tool change and before "
         "the spindle starts — for anything that has to act while the part is still "
         "stationary. A 'pass 1' trigger cannot do this: it runs with the spindle "
         "already turning.",
         "Machine ▸ Custom Commands ▸ When"),
        ("Each command row now reads as a sentence, with its own note",
         "When [pass] = [3] do [M41 P2] note [retract]. One description covers a "
         "whole M-code, so it cannot tell P1 from P2 — the note can. Press ? to "
         "read the full description of the selected row.",
         "Machine ▸ Custom Commands"),
        ("Commands aimed at a pass that does not exist now ask instead of vanishing",
         "A pass trigger is pinned to a pass number, so editing the program list can "
         "leave a command pointing past the end, where it used to be dropped in "
         "silence. Exporting now stops and offers: move it to the last pass, leave "
         "it out of this file, or cancel and fix it. Your command table is never "
         "edited for you.",
         "Export ▸ any format"),
        ("Order matters, so you can now set it",
         "Two commands on the same pass both run, top of the table first. New arrow "
         "buttons move a row up or down.",
         "Machine ▸ Custom Commands ▸ ▲ ▼"),
        ("Fixed: custom commands and M-code descriptions were not being saved",
         "Edits to either table were lost on restart unless you happened to press "
         "Save Machine Profile. They now save as soon as you make them.",
         "Machine ▸ Custom Commands / M-Code Definitions"),
        ("Calculate moved next to the 3D view",
         "It applies to the whole program but used to sit inside the Process tab, so "
         "the Machine tab had no way to recalculate without switching tabs first.",
         "Above the 3D view"),
        ("All exports in one menu",
         "G-code, SCL, recipe CSV, PDF operation sheet and STL were split between "
         "the File menu and buttons at the bottom of the Process tab.",
         "Export ▸"),
        ("'Why is my pass weird?' is now called Preview & Analyze",
         "Same checks, plus the M-code listing — it covers more than passes now.",
         "Help ▸ Preview & Analyze"),
    ],
    "1.013": [
        ("Every number in the pass table now explains itself",
         "Click any cell and a line underneath says where that number came from — "
         "the operation panel, the progressive fan, follow-blank, or set by hand on "
         "that one pass — and what it overrode. Previously the Source column could "
         "only say 'something on this pass is manual', never which value.",
         "Program List ▸ right-click an operation ▸ Passes ▦ ▸ click a cell"),
        ("New: a check that finds settings hiding inside a program",
         "Lists every value that did not come from the operation panel: a reach or "
         "angle set by hand on one pass, old hidden overrides, negative clearances, "
         "and roller reach short enough to dig into the part. Double-click a line to "
         "jump to that operation, or Copy report to send it on.",
         "Help ▸ Why is my pass weird?"),
        ("The value that does not fit is shown in red",
         "A setting changed by hand on EVERY pass is a ramp you built on purpose, so "
         "it stays grey. A setting changed on only SOME passes is the one that "
         "usually causes the surprise — it turns red with a ◆ marker, sorts to the "
         "top of the check, and the ◆ appears on that exact cell in the pass table.",
         "Help ▸ Why is my pass weird?  /  Passes ▦"),
        ("Fixed: the pass table could show a reach the machine never used",
         "On operations that follow the blank edge, the table ignored a rule the "
         "machine applies near the base of the part, so it could display around 10 mm "
         "where the machine actually ran nearly 40 mm. The table now matches.",
         "Program List ▸ right-click an operation ▸ Passes ▦"),
    ],
    "1.012": [
        ("Roughing passes can curl at the end instead of running straight",
         "The exit stays dead straight until a point you choose, then curls away "
         "at the radius you set. The straight part runs smoother and faster on the "
         "machine; the curl near the sheet edge forms a curved side, which is "
         "stiffer than a straight one. Leave the radius empty and nothing changes.",
         "Program List ▸ a roughing operation ▸ Curl Radius"),
        ("The curl can ease in instead of bending all at once",
         "Set an end radius as well and the curve tightens gradually toward the "
         "sheet edge. Leaving the first radius empty starts the curl perfectly "
         "straight and eases into the bend — smoothest on the machine and on the part.",
         "Program List ▸ a roughing operation ▸ Curl R End"),
        ("Saved G-code is no longer affected by PLC mode",
         "The .nc file is now always full resolution, so a G-code viewer shows the "
         "real path. Before, switching PLC mode on also simplified the saved .nc, "
         "which made curves look like straight lines. The PLC still gets its "
         "simplified program from the SCL export, as it always did.",
         "File ▸ Save G-Code"),
        ("New: see exactly what the PLC will receive",
         "Shows the intended path and the PLC recipe on top of each other, with "
         "every point the PLC gets marked, the tolerance and line count in use, and "
         "a warning for any curve too small to survive simplification.",
         "Tools ▸ SCL Inspector"),
    ],
    "1.011": [
        ("The operation table columns can be reordered",
         "Click a column, then move it left or right with the ◀ / ▶ buttons — "
         "bring the ones you watch most to the front instead of scrolling right "
         "to reach them. The order is saved with the program. The ☑ tick column "
         "always stays first.",
         "Program List ▸ Customize… ▸ Column Order"),
        ("This window is easier to read",
         "Each change is now a short headline, a plain sentence, and the place "
         "to click for it.",
         "Shown once after every update"),
    ],
    "1.010": [
        ("Retract is now set per operation",
         "Roughing, finishing, cutting and bending each retract by their own "
         "amount. The old global retract on the Machine tab is gone — existing "
         "programs are migrated and keep the retract they had before.",
         "Program List ▸ select an operation ▸ Retract X / Retract Z"),
        ("Every pass can be edited on its own",
         "Change P1_Z, Extend, Clearance, Angle and Reach for any single pass.",
         "Program List ▸ right-click an operation ▸ Passes ▦"),
        ("Fill many passes at once",
         "\"Set all…\" gives every pass the same value. \"Progressive…\" ramps "
         "smoothly from the first pass to the last. Set all on P1_Z plus "
         "Progressive on Extend builds an anchored sweep — every pass starts in "
         "the same place and reaches a little further.",
         "Passes ▦ ▸ Fill"),
        ("A 2D preview draws the passes as you edit",
         "The picture at the bottom of the pass table updates while you type, "
         "before you apply anything.",
         "Passes ▦ ▸ bottom of the window"),
        ("The exported PDF now lists the parameters",
         "Full operation parameters are printed next to the toolpath plot, so "
         "two parameter sets can be compared side by side. On export you pick "
         "which parameters to include, and the choice is remembered.",
         "Process & Visual ▸ Export PDF"),
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
