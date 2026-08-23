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
    "1.019": [
        ("The recipe no longer begins by pulling the roller back to zero — re-export",
         "An exported recipe used to open with two identical rapids to the zero "
         "position. The machine homes before every run, so at best they did nothing; "
         "but if you had jogged in, or the start cylinder had moved the roller, those "
         "two lines dragged it back to zero before the job began. They are no longer "
         "written into a PLC recipe. Ordinary .nc output is unchanged. Recipes are now "
         "two lines shorter and the header checksum has changed, so export yours "
         "again — a recipe already sitting in the PLC keeps its old checksum and "
         "still runs.",
         "File ▸ Export SCL for TIA Portal (.scl)"),
        ("The tool list now shows Rr, and marks tools that were never calibrated",
         "Rr — the calibrated reach the toolpath actually uses — only appeared in the "
         "editor at the bottom, so you had to click each tool to see it. It is now a "
         "column. A tool with no calibrated Rr reads \"⚠ <number> (uncalibrated)\", "
         "where the number is the disc Radius the path falls back to instead, so you "
         "can see the value in use. Nothing is blocked and no tool behaves "
         "differently. Worth knowing: an uncalibrated tool also skips the "
         "Rr-must-not-be-below-Radius gouge check, which can only run once Rr is set.",
         "Tools ▸ Tool Library..."),
        ("The program is now called SoftSpinner",
         "The name shown in the title bar, the About box and the user guide drops the "
         "EMS prefix — the product name on its own. Licence messages that used to say "
         "\"contact EMS\" now say \"contact your supplier\", which stays correct "
         "whoever you got it from. Nothing about how the program works has changed.",
         "Title bar · Help ▸ About"),
        ("The About box was showing the wrong version number",
         "It read V1.002 no matter which version you were running — the number was "
         "written into the text instead of being read from the build. It now matches "
         "the title bar. Nothing else changes.",
         "Help ▸ About"),
    ],
    "1.018": [
        ("Recipes are now written in blocks of 100 lines — re-export for the current PLC",
         "The PLC could not reliably read a whole recipe in one piece: it reported "
         "success while part of the program arrived empty. Once this ran roughly 900 "
         "zero-length moves with the line counter advancing normally. The recipe is now "
         "written as ten blocks of a hundred lines so the PLC can fetch and check them "
         "one at a time. An .scl exported before this update will not load into the "
         "current PLC project — export your recipes again.",
         "File ▸ Export SCL for TIA Portal (.scl)"),
        ("The recipe database question now shows what you are about to get",
         "One window replaces the old size prompt: total recipe size and lines per "
         "block, with the resulting layout spelled out as you type, plus a warning if "
         "you move away from what the PLC expects. Getting the block size wrong still "
         "passes the TIA compiler but scrambles the recipe, so the export now checks "
         "its own file and refuses to write one that does not add up.",
         "File ▸ Export SCL for TIA Portal (.scl) ▸ Recipe Database Layout"),
        ("The PLC can now tell whether the recipe it loaded is the one you exported",
         "Each recipe carries a checksum over its own lines. The PLC recomputes it "
         "after loading and refuses to run if the two disagree, which catches a recipe "
         "that arrived complete but wrong — something its line-by-line check cannot "
         "see. The number is shown when the export finishes; if the machine ever "
         "refuses a recipe, quote it and export again.",
         "File ▸ Export SCL for TIA Portal (.scl)"),
        ("Opening a program no longer changes your machine settings behind your back",
         "A saved program also stores the machine settings from the day it was saved, "
         "and opening it used to apply them silently — one operator got an old PLC line "
         "limit back this way. The part shape and operations still come from the file, "
         "but machine settings now stay as YOU have them. If the file disagrees, a "
         "window lists each one side by side; every row starts on yours, so pressing OK "
         "without reading changes nothing.",
         "File ▸ Open Project (.ssp)"),
        ("Export stops if the program uses a tool you do not have",
         "The tool library belongs to the computer, not to the program. If an operation "
         "names a tool that is not in your library, its roller reach cannot be refreshed "
         "and the operation keeps a reach calibrated on another machine — which is the "
         "clearance, so the roller could gouge the part or hit the mandrel. Export now "
         "stops and names the tool and the operations using it.",
         "File ▸ Export G-code / Export SCL"),
        ("Each recipe gets its own name, and a wrong slot is caught",
         "The program title now defaults to the data block's number instead of "
         "'SpinningCam Program' for every recipe, so the HMI can tell the operator which "
         "one is loaded. And if the block name and the file name point at different "
         "program numbers, you are asked before saving — importing that would overwrite "
         "the wrong recipe.",
         "File ▸ Export SCL for TIA Portal (.scl)"),
    ],
    "1.017": [
        ("Exported SCL now matches the machine's current PLC — re-export your recipes",
         "After the commissioning in August the PLC keeps recipes in load memory and "
         "copies the selected one across at run time. The data block written by this "
         "program is built for that: it is no longer optimised, it is marked UNLINKED "
         "so it does not eat working memory, and it is stamped version 0.2. An .scl "
         "file exported before this update will not load into the current PLC project, "
         "so export your recipes again.",
         "File ▸ Export SCL for TIA Portal (.scl)"),
        ("A recipe block you cannot watch online is normal now",
         "Because the block lives in load memory, TIA Portal will not show live values "
         "for it — there is nothing to monitor until the PLC copies the recipe into "
         "DB_SelectedRecipe. That is the intended behaviour, not a failed import.",
         "File ▸ Export SCL for TIA Portal (.scl)"),
        ("Recipe database size is still yours to choose — but keep the PLC in step",
         "The size question at export time is unchanged and still defaults to 1000. "
         "The one thing to watch: if you pick anything other than 1000, the array in "
         "DB_SelectedRecipe on the PLC has to be given the same size, otherwise the "
         "recipe copy fails while loading. The prompt and the help page now say so.",
         "File ▸ Export SCL for TIA Portal (.scl) ▸ Recipe Database Size"),
    ],
    "1.016": [
        ("Calibration ▸ Apply now really lands — and can no longer be undone by accident",
         "The Apply buttons did change the setting, but the box on the Machine or "
         "Process tab kept showing the OLD number, so it looked like nothing had "
         "happened. Worse: if you later clicked into that box and clicked away "
         "again, the old number was written back and your calibration was silently "
         "lost. The corrected value now appears in the box immediately and stays "
         "there. Worth re-checking your Program Start X/Z once after updating, in "
         "case an earlier calibration was reverted this way.",
         "Machine ▸ Touch Point Calibration ▸ Apply Correction"),
        ("Apply Blank Thickness now always corrects the real thickness",
         "With 'apply to this pass only' switched on, this one correction could be "
         "written onto a single pass instead of the actual Blank Thickness setting, "
         "leaving the real value untouched. A calibration correction is always "
         "global now, like the other four Apply buttons.",
         "Machine ▸ Touch Point Calibration ▸ Blank Thickness"),
        ("New: a Program End position",
         "The program has always finished by returning to Program Start. You can "
         "now send the roller somewhere else instead — clear of the tailstock for "
         "unloading, say. It stays on 'Same as Program Start' unless you untick "
         "that box, so your existing programs run exactly as before.",
         "Machine ▸ Program End"),
        ("Set the end position here, not in the G-Code Footer",
         "Footer text is sent to the machine exactly as you type it, so a G0 move "
         "written there is raw machine coordinates: it skips the axis direction, "
         "work offset and diameter settings, it does not follow later changes to "
         "the machine profile, and the 3D view never shows it. Program End goes "
         "through the same conversion as every other coordinate and does appear in "
         "the simulation.",
         "Machine ▸ Program End"),
        ("Program Start and Program End now show what you calibrated against",
         "These are program coordinates, so they never look like the reading on "
         "your machine's DRO — which made it hard to tell which calibration a "
         "machine profile was standing on. The last touch reading is now shown "
         "underneath, exactly as you entered it, tagged with the tool and date.",
         "Machine ▸ Program Start / Program End"),
    ],
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
        ("The retract in the exported program now pulls the same way the 3D view does",
         "A retract means 'pull the roller off the work', but the .nc used the sign "
         "you typed literally while the 3D view always pulled away. On this machine "
         "the roller runs on the negative side, so a POSITIVE retract sent the tool "
         "toward the part in the program while the simulation showed it clearing. "
         "The sign is now ignored: you set the distance, the machine decides the "
         "direction. If you ever worked around this by typing a negative number, "
         "your programs are unchanged — that number already pointed the right way.",
         "Program List ▸ any operation ▸ Retract X"),
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
