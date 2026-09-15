"""Where the machine really stops, for the 3D view (user, 2026-09-16).

With continuous-motion export on, most cutting lines blend into the next one and
the machine only stops at some points. The operator asked to SEE that: the pass
keeps its colour, and a dot marks every point where the machine stops. A long
stretch with no dots runs nonstop.

WHERE THE ANSWER COMES FROM — the same chain as the SCL export, never a guess:

    generate_gcode(for_recipe=True)            (with the auto-tune fit, when on)
    -> GCodeToSCLConverter(markers, continuous_motion)
    -> the PLC's own rule for every line:
       a line blends only when it is CMD=2 with F > 0 AND the NEXT recipe line is
       CMD=1 or CMD=2 with F > 0 (letter_spinningcam_velocity_path.md). Every
       other motion line - CMD=1, a CMD=2 before a marker / spindle / rapid, and
       every rapid - ends in a stop.

So the dots cannot disagree with the file that ships.

HOW A RECIPE LINE BECOMES A 3D POINT — by COUNTING, not by coordinates. The
emitter writes path i as one start G0 plus one G1 per point after the first,
in path order (path_generator.generate_gcode). So cut line k of path i is point
k of ``last_plc_paths[i]``, which is a thinned copy of the drawn path in the
same frame. Lines that belong to no toolpath (a Point op's moves, and later the
mandrel-end link) are marked ``exact`` by the converter and skipped. If the
count does not add up, there are NO dots and a warning is logged: a missing
picture is safe, a wrong one is not.

Only stops ON a toolpath are drawn (a pass start reached by a rapid, and every
stopping cut line). The end of a retract in the air is a stop too, but the 3D
rapid lines are drawn from the simulation's own rapid shape, not the recipe's,
so there is no honest place to put that dot. The help text says so.

Nothing here writes to the path generator the app is using: the emission runs
on a shallow copy, and generate_gcode only ever REBINDS its attributes.
"""
import copy
import json
import logging

import numpy as np

from recipe_to_scl import (GCodeToSCLConverter, continuous_settings,
                           CMD_RAPID, CMD_LINEAR, CMD_LINEAR_CONTINUOUS)

logger = logging.getLogger("SpinningCam")

FEED_CMDS = (CMD_LINEAR, CMD_LINEAR_CONTINUOUS)
# params keys that only change what the 3D view shows; editing them must not
# throw away a computed answer (an auto-tune fit can take a while).
_VIEW_PREFIX = "show_"


def stop_flags(lines):
    """One bool per recipe line: True where a MOTION line ends in a stop.

    Mirrors the PLC rule quoted in the module docstring, evaluated on the very
    next recipe line - a marker or spindle line between two cuts ends the run,
    exactly as it does on the machine. Non-motion lines are False.
    """
    n = len(lines)
    out = [False] * n
    for i, ln in enumerate(lines):
        if ln.cmd == CMD_RAPID:
            out[i] = True
        elif ln.cmd in FEED_CMDS:
            nxt = lines[i + 1] if i + 1 < n else None
            blends = (ln.cmd == CMD_LINEAR_CONTINUOUS and ln.f > 0
                      and nxt is not None and nxt.cmd in FEED_CMDS and nxt.f > 0)
            out[i] = not blends
    return out


def map_stops(lines, flags, plc_paths):
    """[(path index, point index)] for every stop that lies on a toolpath, or
    None when the recipe does not line up with ``plc_paths``.

    A pass start (point 0) gets a dot when the motion line that brought the
    roller there stopped and was not the previous pass's own last cut line
    (that dot is already drawn, at the same place - a back pass flowing out of
    its forward pass).
    """
    need = [max(len(p) - 1, 0) if p is not None else 0 for p in (plc_paths or [])]
    out = []
    i, k = 0, 0
    prev_stop, prev_was_cut = False, False
    for idx, ln in enumerate(lines):
        if ln.cmd == CMD_RAPID:
            prev_stop, prev_was_cut = True, False
            continue
        if ln.cmd not in FEED_CMDS:
            continue
        if getattr(ln, "exact", False):
            # A Point op's move (or a link line): on no toolpath.
            prev_stop, prev_was_cut = flags[idx], False
            continue
        while i < len(need) and k >= need[i]:
            i, k = i + 1, 0
        if i >= len(need):
            return None                       # more cut lines than path points
        if k == 0 and prev_stop and not prev_was_cut:
            out.append((i, 0))
        k += 1
        if flags[idx]:
            out.append((i, k))
        prev_stop, prev_was_cut = flags[idx], True
    while i < len(need) and k >= need[i]:
        i, k = i + 1, 0
    if i != len(need):
        return None                           # fewer cut lines than path points
    return out


def compute(path_gen, params):
    """The stops of the program as the SCL export would write it now.

    Returns None when there is nothing honest to draw: continuous motion off,
    no paths, an export error (e.g. a cutting move with F = 0), or a recipe that
    does not line up with the paths. Otherwise a dict:
      points      [(path index, np.array([x, y, z]))]  in the drawn paths' frame
      stops       number of dots
      recipe_lines, tolerance (the auto-tune fit, or None)
    """
    params = params or {}
    cont = continuous_settings(params)
    if cont is None:
        return None
    if not getattr(path_gen, "last_calculated_paths", None):
        return None
    markers = bool(params.get("plc_pass_markers", False)) and bool(params.get("plc_mode", False))

    pg = copy.copy(path_gen)                  # generate_gcode rebinds; the app's stays as is
    p = dict(params)
    tuned = None
    if p.get("plc_auto_tune", False) and p.get("plc_mode", False):
        # Same fit, same inputs as export_scl_action - otherwise the dots would
        # show the manual tolerance while the file ships the fitted one.
        from export_manager import ExportManager
        target = int(p.get("plc_target_lines", 1000) or 1000)
        floor = pg.measure_min_clearance(pg.last_calculated_paths, p)
        fit = ExportManager.auto_fit_plc_tolerance(pg, p, target, floor,
                                                   emit_pass_markers=markers)
        tuned = fit.get("tolerance")
        if tuned is None:
            return None
        p["plc_mode"] = True
        p["plc_tolerance"] = tuned
        p["plc_exit_tolerance"] = tuned

    gcode = pg.generate_gcode(params=p, for_recipe=True)
    conv = GCodeToSCLConverter(emit_pass_markers=markers, continuous_motion=cont)
    conv.parse_gcode(gcode)
    plc = pg.last_plc_paths or []
    flags = stop_flags(conv.lines)
    pairs = map_stops(conv.lines, flags, plc)
    if pairs is None:
        logger.warning("[motion stops] recipe lines do not line up with the toolpaths; "
                       "no stop dots drawn")
        return None
    return {
        "points": [(i, np.asarray(plc[i][k], dtype=float)) for i, k in pairs],
        "stops": len(pairs),
        "recipe_lines": len(conv.lines),
        "tolerance": tuned,
    }


def _params_key(params):
    view_free = {k: v for k, v in (params or {}).items()
                 if not str(k).startswith(_VIEW_PREFIX)}
    return json.dumps(view_free, sort_keys=True, default=str)


class StopCache:
    """Remembers the last answer while the paths and the program are unchanged.

    The paths are compared by IDENTITY (calculate_paths always builds a new
    list), the program by its params minus the ``show_*`` view switches. The
    list itself is held, not its id(), so a recycled id can never match.
    """

    def __init__(self):
        self._paths = None
        self._key = None
        self._value = None

    def get(self, path_gen, params):
        paths = getattr(path_gen, "last_calculated_paths", None)
        key = _params_key(params)
        if paths is not None and paths is self._paths and key == self._key:
            return self._value
        try:
            value = compute(path_gen, params)
        except Exception as e:                # a view aid must never break the view
            logger.error(f"[motion stops] not drawn: {e}")
            value = None
        self._paths, self._key, self._value = paths, key, value
        return value
