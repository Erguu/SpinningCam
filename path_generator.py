import datetime
import numpy as np
import math
import time
import re
from OCC.Core.gp import gp_Pnt, gp_Dir, gp_Ax1, gp_Trsf
from OCC.Core.TColgp import TColgp_Array1OfPnt
from OCC.Core.GeomAPI import GeomAPI_PointsToBSpline
from logger_config import logger
from kinematics import get_kinematics
import exit_waypoints
import exit_breaks

# #100: how far the iterative safety floor may move a pass that carries a
# hand-drawn tail before the operator is told. The tail is measured FROM P2, so
# it travels with any such shift; past a millimetre or so the contact point is
# no longer where it was drawn and the pass may be doing less work than intended.
TAIL_SHIFT_REPORT_MM = 1.0

# CSS (constant surface speed, G96) is DISABLED — user decision 2026-08-31,
# "we don't use it".
#
# The PLC recipe protocol has no CSS mode: CMD=20 carries a fixed RPM target
# (Param = RPM / 10, CAM_INTERFACE_SPEC §5). recipe_to_scl reads the S word and
# nothing else, so a CSS operation's surface speed was being shipped to the
# machine AS IF it were RPM — "200 m/min" ran as 200 RPM, silently. Until a real
# CSS→RPM conversion exists, every operation is read as RPM.
#
# Legacy ops that still carry speed_mode="CSS" keep their stored number and are
# read as RPM. That is exactly what the machine has been doing all along, so no
# recipe changes value; what changes is that the UI, the .nc and the time
# estimate now say the same thing the PLC does.
#
# To re-enable: flip this to True and CSS reappears in the Program-tab combo.
# Nothing else needs touching — every read goes through resolve_speed_mode().
CSS_SPEED_MODE_ENABLED = False


def speed_mode_choices():
    """Speed modes offered in the UI. Mirrors CSS_SPEED_MODE_ENABLED."""
    return ["CSS", "RPM"] if CSS_SPEED_MODE_ENABLED else ["RPM"]


def zero_spindle_ops(params):
    """Enabled operations that would command the spindle to STOP.

    ``CMD=20`` sets the speed TARGET, and ``Param = rpm // 10``. So a recipe
    line with ``Param=0`` does not mean "no speed given" — it means "run at zero
    RPM", and the spindle stays stopped for that whole operation. A cut-off or
    bending pass on a spinning machine needs the part turning, so this is a
    broken program rather than an unusual one.

    Caught in the field: DB_RecipeProgram2.scl shipped four of them (two cutting
    ops, a roughing op and a bending op), and nothing anywhere said so.

    The threshold is ``< 10``, not ``== 0``: integer division means 9 RPM also
    encodes to Param 0, so testing for zero alone would miss the sneakier half
    of the same fault.

    Note none of the CAM's own defaults can produce this — clearing the Speed
    box REMOVES the key and falls back to the global speed, a new operation
    starts at 300 RPM, and the suggester clamps to 60. A zero is always a value
    someone entered or a preset carried in, which is exactly why the program
    cannot tell it apart from a mistake and has to ask.

    Returns ``[{'index', 'name', 'type', 'rpm'}, ...]``, empty when all is well.
    Read-only; never alters params.
    """
    out = []
    for i, op in enumerate((params or {}).get("operations", []) or []):
        if not op.get("enabled", True):
            continue
        try:
            rpm = float(op.get("speed", params.get("surface_speed_m_min", 200)))
        except (TypeError, ValueError):
            continue        # not a number: a different problem, not this one
        if rpm < 10.0:
            op_type = str(op.get("type", "roughing") or "roughing")
            out.append({"index": i,
                        "name": op.get("name") or op_type.upper(),
                        "type": op_type,
                        "rpm": rpm})
    return out


def resolve_speed_mode(op):
    """An operation's spindle speed mode — THE SINGLE SOURCE OF TRUTH.

    Every consumer (emitter, simulator, time estimate, live monitor, SCL header,
    the editor combo) must call this instead of reading ``op["speed_mode"]``, or
    the kill switch above would be honoured in some places and not others: the
    file would say G96 while the recipe ran a fixed RPM.
    """
    mode = str((op or {}).get("speed_mode", "RPM") or "RPM").upper()
    if mode == "CSS" and not CSS_SPEED_MODE_ENABLED:
        return "RPM"
    return mode


def op_builds_back_pass(op):
    """True when each of this op's forward passes is followed by a back pass.

    THE SINGLE SOURCE OF TRUTH for that question. `calculate_paths` branches on
    it, and so must every consumer that maps a toolpath index back to a pass —
    the 3D renderer, the pass colouring, the per-pass tool radius, the PDF. They
    are indexing arrays the engine built; a different rule means different
    indices, and the arrays do not complain.

    `back_pass_enabled` on its own is NOT that rule:

    * a cutting/bending op emits one feed line and never a back pass;
    * a REVERSE pass already IS the return stroke, so the engine builds no
      second one even with the box ticked (#49, user 2026-08-29).

    The reverse case is why this function exists rather than staying inline. It
    WAS inline, in six places, as "back_pass_enabled and not cutting/bending".
    When reverse stopped building a back pass (2026-08-30) the engine changed
    and those six did not, so a reverse op with the box still ticked left every
    consumer counting one phantom path per pass: measured 4 paths emitted
    against 6 expected, which slid the colours, the tool radius and the
    active-pass highlight one entry further out of phase with each pass.
    """
    if not (op or {}).get("back_pass_enabled", False):
        return False
    if op.get("type", "roughing") in ("cutting", "bending"):
        return False
    if op.get("direction", "forward") == "reverse":
        return False
    return True


def op_toolpath_entries(op):
    """How many toolpath-list entries this op contributes.

    The layout `calculate_paths` produces: a cutting/bending op is always ONE
    feed line (its `count` is ignored), any other type emits `count` forward
    passes, and each forward pass is followed by a back pass exactly when
    `op_builds_back_pass` says so.

    Disabled ops emit nothing; skipping them is the caller's job, because every
    caller already has to do it before this point.
    """
    op = op or {}
    if op.get("type", "roughing") in ("cutting", "bending"):
        return 1
    try:
        n = int(op.get("count", 1) or 1)
    except (TypeError, ValueError):
        n = 1
    return max(n, 0) * (2 if op_builds_back_pass(op) else 1)


def representative_feed_mm_min(op, path, params, center_x=0.0):
    """Resolve an operation's cutting feed to mm/min, for SIMULATION pacing.

    The 3D sim now moves the roller along the toolpath at the machine's real
    linear feed so pass-to-pass speeds are truthful. An ``mm_min`` feed is used
    directly; an ``mm_rev`` feed is converted with a representative spindle rpm
    (RPM directly, or derived from CSS using the pass's mean diameter, capped at
    the spindle limit — the same relation ``generate_gcode`` uses). Always
    returns a positive value, falling back to the global default feed.
    """
    default_feed = float(params.get("feed_rate_mm_min", 300.0) or 300.0)
    try:
        feed = float(op.get("feed", default_feed))
    except (TypeError, ValueError):
        feed = default_feed
    if feed <= 0:
        feed = default_feed

    if str(op.get("feed_mode", "mm_min")) != "mm_rev":
        return feed

    # mm/rev → mm/min needs an rpm.
    try:
        spd = float(op.get("speed", params.get("surface_speed_m_min", 200.0)))
    except (TypeError, ValueError):
        spd = 200.0
    if resolve_speed_mode(op) == "RPM":
        rpm = spd
    else:
        # CSS (m/min) → rpm using the pass's mean diameter as a stand-in.
        try:
            xs = [abs(float(p[0]) - center_x) for p in path]
            r_rep = max(1.0, sum(xs) / len(xs)) if xs else 50.0
        except (TypeError, ValueError, IndexError):
            r_rep = 50.0
        dia_mm = 2.0 * r_rep
        rpm = (spd * 1000.0) / (math.pi * dia_mm) if dia_mm > 0 else 0.0
        rpm = min(rpm, float(params.get("spindle_speed_limit_rpm", 3000.0)))
    return feed * max(1.0, rpm)


def effective_clamp_length(params):
    """Clamp / counter-press zone length in effect (mm, measured UP from the mandrel
    base). TODO #62. The per-part override ``clamp_zone_length`` wins when > 0; otherwise
    the machine-level ``clamp_zone_baseline`` applies. 0 = no clamp zone.

    Note: 0 for the per-part value means "inherit the machine baseline", so a per-part
    value cannot force-disable a non-zero baseline in phase 1 (documented tradeoff)."""
    def _f(v):
        try:
            return float(v or 0.0)
        except (TypeError, ValueError):
            return 0.0
    v = _f(params.get("clamp_zone_length", 0.0))
    if v <= 0.0:
        v = _f(params.get("clamp_zone_baseline", 0.0))
    return max(0.0, v)


# ── Per-op tool-change position (2026-07-21) ─────────────────────────────────
# The tool-change retract target is normally the global machine home (Program
# Start). An operation may override it: "absolute" pins an explicit X/Z; "relative"
# offsets from the previous pass's end. Default "global" = unchanged behavior.
# resolve_tool_change_point returns the target in the SAME coordinate frame as the
# prev_end / home_pt passed in (canonical in calculate_paths, global/pre-transform
# in generate_gcode), so BOTH emission sites stay in sync from this one function.
TOOL_CHANGE_MODES = ("global", "absolute", "relative")
# Advisory swing clearance (mm): a custom change point closer than this to the
# outermost part/blank obstacle is flagged (M6 rotates the turret — warn only).
TOOL_CHANGE_SWING_MARGIN_MM = 5.0


def resolve_tool_change_point(op, prev_end, home_pt, center_x=None, side=1.0):
    """Return the tool-change retract target ``[x, y, z]`` for ``op``.

    The user enters X / ΔX in the REAL machine frame (what they read in the
    G-code): the value is applied with its LITERAL SIGN — a positive ΔX increases
    X, a negative ΔX decreases it. No abs() — the operator picks the direction.

    op        operation dict; reads ``tool_change_mode`` + ``tool_change_x/z``
              (absolute) or ``tool_change_dx/dz`` (relative).
    prev_end  end point of the previous pass (used by "relative").
    home_pt   machine home in the CALLER's frame (fallback / "global").
    center_x  mandrel X center. Pass it ONLY from the 3D sim, whose frame is the
              canonical positive-X side that later gets mirrored around center_x
              for a negative-side roller. Then the real-frame X the user typed is
              converted INTO that canonical frame so it lands correctly after the
              mirror. The G-code emitter already works in the real frame, so it
              passes ``center_x=None`` and no conversion happens.
    side      +1 = positive-X roller (no mirror), -1 = negative-X roller. Only
              used with ``center_x`` to flip the X offset into the sim frame.
    """
    def to_frame_x(real_x):
        # real machine X -> caller frame X. Identity in the G-code emitter
        # (center_x is None); in the sim it undoes the end-of-pass X mirror so
        # the value the user typed survives it: canonical = center + side*(x-center).
        if center_x is None:
            return real_x
        return center_x + side * (real_x - center_x)

    mode = str(op.get("tool_change_mode", "global") or "global").lower()
    if mode == "absolute":
        x = float(op.get("tool_change_x", home_pt[0]))
        z = float(op.get("tool_change_z", home_pt[2]))
        return np.array([to_frame_x(x), home_pt[1], z])
    if mode == "relative":
        dx = float(op.get("tool_change_dx", 0.0))
        dz = float(op.get("tool_change_dz", 0.0))
        # prev_end is already in the caller frame; the offset just needs the same
        # X-direction flip as the frame (side) so +ΔX means +X in the real frame.
        return np.array([prev_end[0] + side * dx, prev_end[1], prev_end[2] + dz])
    # global (default) — unchanged behavior
    return np.array([home_pt[0], home_pt[1], home_pt[2]])


def resolve_pass_retract(op, params):
    """Per-op pass-retract offsets ``(retract_x, retract_z)`` — #90.

    Falls back to the GLOBAL machine retract (``params["retract_x/z"]``) when the
    op carries no override, so operations without the keys behave exactly as
    before. Scope is pass-retract only: the forming-pass retract and its back
    pass honor this; cutting/bending keep using the global (handled separately).

    Returned RAW (unsigned): the 3D sim applies ``abs()`` for its canonical
    positive-X frame exactly as it does for the global value, while the G-code
    emitter uses the values as-is — so BOTH sites keep their existing arithmetic
    and only the SOURCE of the number changes.
    """
    def _pick(k):
        v = op.get(k, None)
        try:
            if v not in (None, ""):
                return float(v)
        except (TypeError, ValueError):
            pass
        return float(params.get(k, 50.0))
    return _pick("retract_x"), _pick("retract_z")


def resolve_program_end(params):
    """Program END park point ``(x, z)`` in CAM coordinates.

    Defaults to Program Start (``home_x``/``home_z``) — the point the final move
    has always used — so a recipe or machine profile without the keys emits
    byte-identical G-code. Set ``end_use_home`` False to park somewhere other
    than where the program began (clear of the tailstock for unloading, say).

    Why this is a real parameter and not a line in the G-Code Footer: the footer
    template is written out VERBATIM, while every coordinate the engine emits
    goes through the post-processor transform (axis inversion, G54 offset,
    diameter mode). A hand-typed footer move is therefore raw machine
    coordinates that silently stop matching once the machine profile changes,
    and it never reaches the 3D simulation at all.
    """
    hx = float(params.get("home_x", 300.0))
    hz = float(params.get("home_z", 150.0))
    if params.get("end_use_home", True):
        return hx, hz

    def _pick(k, dflt):
        v = params.get(k, None)
        try:
            if v not in (None, ""):
                return float(v)
        except (TypeError, ValueError):
            pass
        return dflt

    return _pick("end_x", hx), _pick("end_z", hz)


def retract_x_offset_real(retract_x, side):
    """Pass-retract X offset in the REAL machine frame, always pointing AWAY from
    the part. ``side`` = +1 positive-X roller, -1 negative-X roller.

    A retract only ever means "pull the roller off the work", so the user sets the
    MAGNITUDE and the direction follows the machine: +X on a positive-side roller,
    -X on a negative-side one (the engine mirrors X around the mandrel center for
    the latter). The sign the user types is therefore ignored.

    Why this exists: the 3D sim got this right for free — it builds every path in
    the canonical positive-X frame using ``abs(retract_x)`` and mirrors the whole
    path at the end, which lands the retract at ``end + side*|retract_x|`` in the
    real frame. The G-code emitter works directly in the real frame and used the
    LITERAL sign, so ``end + retract_x``. On a negative-side machine those two
    disagree unless the user happens to type a negative number: a positive
    retract_x drove the tool INTO the part in the .nc while the simulation showed
    it pulling clear — same recipe, opposite directions, no warning. This helper
    is what makes the emitter agree with the sim.

    Note this is pass retract only. The per-op TOOL-CHANGE offsets
    (``resolve_tool_change_point``) keep their literal sign on purpose: that point
    is a position the operator aims at, not a "get clear" move, and both call
    sites already convert it into the right frame.
    """
    return abs(float(retract_x)) * (1.0 if side >= 0 else -1.0)


# ── Axis motion order (2026-09-03) ───────────────────────────────────────────
# How a two-axis move travels: one coordinated diagonal, or one axis at a time.
# Shared vocabulary for the Point operation and the pass retract so the operator
# meets ONE set of words, and the two features cannot drift into describing the
# same shape differently.
#
# Not a new machine capability: the tool-change block has emitted separate
# single-axis G0 lines since 2026-07-21 (`tool_change_simultaneous`), so the PLC
# already runs them in production.
AXIS_MOTION_MODES = ("synchronized", "x_first", "z_first")


def _norm_motion(value):
    """Normalise a stored motion mode. Unknown values -> "synchronized".

    Falls back to the coordinated diagonal because that is what every move in
    this program did before the feature existed: an unreadable value must not
    silently turn one move into two, which is a different path through the part.
    """
    mode = str(value or "synchronized").lower()
    return mode if mode in AXIS_MOTION_MODES else "synchronized"


def motion_waypoints(from_pt, target, motion):
    """Waypoints for a two-axis move, ``[from, ...corner..., target]``.

    Two points for a coordinated diagonal, three when one axis leads. Pure — the
    3D sim and the G-code emitter both call this so the picture and the machine
    cannot describe different shapes.

    The corner point is the ONLY thing that differs between the modes:
      x_first -> corner at (target.x, from.z)   move X across, then Z
      z_first -> corner at (from.x, target.z)   move Z along, then X
    """
    from_pt = np.asarray(from_pt, dtype=float)
    target = np.asarray(target, dtype=float)
    mode = _norm_motion(motion)
    if mode == "x_first":
        corner = np.array([target[0], from_pt[1], from_pt[2]])
    elif mode == "z_first":
        corner = np.array([from_pt[0], from_pt[1], target[2]])
    else:
        return [from_pt, target]
    return [from_pt, corner, target]


def resolve_retract_motion(op):
    """Motion order for this op's PASS RETRACT. Default "synchronized".

    The default matters more here than anywhere else in this feature: every
    recipe ever written by this program retracts with a single diagonal G0, and
    that must stay byte-identical for anyone who does not opt in.

    ``z_first`` is offered but is the dangerous one — see
    ``retract_motion_is_risky``.
    """
    return _norm_motion(op.get("retract_motion", "synchronized"))


def retract_motion_is_risky(motion):
    """True when this retract order drags the roller ALONG the part before
    pulling it clear.

    A retract starts ON the work. ``z_first`` therefore travels the whole Z
    offset while the roller is still in contact — a scratch or a gouge down the
    length of that move — and only then lifts in X. ``x_first`` pulls clear
    first and is the safe split; ``synchronized`` leaves immediately.

    Note the TOOL-CHANGE block uses Z-then-X and is fine, because by then the
    pass retract has already lifted the roller off the work. Same order, totally
    different starting condition — which is exactly why this is warned about
    here and not there.

    Warn-only by user decision (2026-09-03): metal-spinning setups vary and an
    operator who has measured their fixture may legitimately want it.
    """
    return _norm_motion(motion) == "z_first"


def resolve_point_motion(op):
    """The Point op's motion mode, normalised. Unknown values -> "synchronized"."""
    return _norm_motion(op.get("point_motion", "synchronized"))


# What a Point op's position is measured FROM (2026-09-03b).
#
# "absolute" is the original behaviour and stays the default, so every Point op
# written before this existed lands exactly where it did.
#
# The others exist because a pass does NOT work this way: you give a pass its
# Z and the engine derives its X from the mandrel (`p2_x = center + radius(z) +
# r_tool + blank + clearance`). A pass therefore follows the part when the
# mandrel or the sheet thickness changes; an absolute Point does not. "surface"
# gives a Point the same behaviour.
POINT_MODES = ("absolute", "surface", "relative", "home")


def resolve_point_mode(op):
    """The Point op's reference mode, normalised. Unknown values -> "absolute".

    Falls back to absolute because that is the mode that needs no context: it
    cannot silently resolve against a mandrel or a previous pass that is not
    what the operator had in mind.
    """
    mode = str(op.get("point_mode", "absolute") or "absolute").lower()
    return mode if mode in POINT_MODES else "absolute"


def point_surface_x(op, params, mandrel_mgr, z, mandrel_center):
    """REAL-frame radial distance for a "surface" Point: how far the tool
    reference sits from the mandrel axis at height ``z``.

    Deliberately the SAME stack a forming pass uses (see the ``total_off`` line
    in ``calculate_paths``), so "standoff 0" on a Point puts the roller exactly
    where a pass with zero clearance would put it:

        radius(z) + shell + sheet thickness + r_tool + standoff

    Returns the radial distance only — the caller adds the mandrel centre and
    the roller side.
    """
    def _f(v, dflt):
        try:
            return float(v) if v not in (None, "") else float(dflt)
        except (TypeError, ValueError):
            return float(dflt)

    params = params or {}
    r_contact = 0.0
    if mandrel_mgr is not None:
        try:
            r_contact = float(mandrel_mgr.get_radius_fast(z))
        except Exception:
            r_contact = 0.0
    r_contact += _f(params.get("shell_thickness"), 0.0)
    return (r_contact
            + _f(params.get("final_part_thickness_on_mandrel"), 2.0)
            + _f(op.get("r_tool"), 0.0)
            + _f(op.get("point_standoff"), 0.0))


def resolve_point_target(op, center_x=None, side=1.0, params=None,
                         mandrel_mgr=None, prev_end=None, home_pt=None):
    """Return the Point op's target ``[x, y, z]`` in the CALLER's frame.

    Four modes (``point_mode``):

    absolute  ``point_x`` / ``point_z`` verbatim. ``point_x`` is the REAL
              machine X the operator reads off the DRO — the same convention as
              cutting/bending ``plunge_*`` — used with its literal sign, never
              abs()'d. This is a position somebody aimed at, not a "get clear"
              move like the pass retract.
    surface   ``point_z`` plus ``point_standoff``; X follows the mandrel exactly
              the way a pass does. See ``point_surface_x``.
    relative  ``point_dx`` / ``point_dz`` from ``prev_end``.
    home      ``point_dx`` / ``point_dz`` from ``home_pt``.

    FRAMES — the part that is silent when wrong:

    center_x / side  Pass these ONLY from the 3D sim, which builds in the
                     canonical positive-X frame and mirrors around ``center_x``
                     at the end. ``center_x=None`` means the caller (the G-code
                     emitter) is already in the real frame. Same trick, and same
                     reason, as ``resolve_tool_change_point``.

    ``prev_end`` and ``home_pt`` must arrive ALREADY in the caller's frame — the
    offset then only needs the X-direction flip, exactly like the tool-change
    "relative" mode. ``point_x`` and the surface geometry are real-frame and go
    through the conversion.

    Note ``side`` is needed even by the emitter for "surface": the radial
    distance has to be added on the roller's side of the axis. Getting that
    wrong is invisible on a positive-side machine.
    """
    def _num(key, dflt):
        v = op.get(key, None)
        try:
            if v not in (None, ""):
                return float(v)
        except (TypeError, ValueError):
            pass
        return float(dflt)

    def to_frame_x(real_x):
        return real_x if center_x is None else center_x + side * (real_x - center_x)

    # TWO different uses of `side`, and conflating them is silent on a
    # positive-side machine:
    #
    #   side       the ROLLER side. Geometry ("surface") needs it, in both
    #              callers, to add the radial distance on the correct side.
    #   frame_flip the FRAME conversion factor. An offset added to an anchor that
    #              is already in the caller's frame must flip only when that
    #              frame is mirrored — i.e. never in the emitter. This is why
    #              resolve_tool_change_point is called from the emitter without a
    #              `side` argument at all; here the emitter has to pass one for
    #              the geometry, so the distinction must be explicit.
    frame_flip = 1.0 if center_x is None else side

    mode = resolve_point_mode(op)
    # The mandrel axis. Same number as `center_x` when the sim calls, but a
    # SEPARATE role: this positions geometry, `center_x` decides whether a frame
    # conversion happens at all.
    m_center = float((params or {}).get("mandrel_pos_x_offset", 0.0))

    if mode == "surface":
        z = _num("point_z", 0.0)
        d = point_surface_x(op, params, mandrel_mgr, z, m_center)
        return np.array([to_frame_x(m_center + side * d), 0.0, z])

    if mode in ("relative", "home"):
        anchor = prev_end if mode == "relative" else home_pt
        if anchor is None:
            # No previous pass (a Point as the first op) / no home supplied:
            # fall back to absolute rather than resolving against nothing.
            anchor = np.array([to_frame_x(_num("point_x", 0.0)), 0.0,
                               _num("point_z", 0.0)])
            return anchor
        anchor = np.asarray(anchor, dtype=float)
        return np.array([anchor[0] + frame_flip * _num("point_dx", 0.0), 0.0,
                         anchor[2] + _num("point_dz", 0.0)])

    # absolute (default)
    return np.array([to_frame_x(_num("point_x", 0.0)), 0.0, _num("point_z", 0.0)])


def retract_segments(end_pt, dx, dz, motion):
    """Rapid segments for a pass retract from ``end_pt`` by ``(dx, dz)``.

    Returns a list of ``[[from], [to]]`` numpy pairs — one for a coordinated
    diagonal, two when an axis leads. Zero-length legs are dropped, so a retract
    with no Z offset never emits a second line whatever the mode says.

    ``dx`` must ALREADY carry its machine direction (``retract_x_offset_real``
    in the emitter, ``abs()`` in the canonical sim frame). This function only
    decides the SHAPE of the move, never which way it goes.

    Single source of truth for five call sites — two in ``generate_gcode``
    (forward pass, back pass) and three in ``calculate_paths`` (forward pass,
    back pass, cutting/bending). They must agree or the 3D view shows a path the
    machine does not run.
    """
    end_pt = np.asarray(end_pt, dtype=float)
    target = np.array([end_pt[0] + float(dx), end_pt[1], end_pt[2] + float(dz)])
    pts = motion_waypoints(end_pt, target, motion)
    return [np.array([a, b]) for a, b in zip(pts, pts[1:])
            if np.linalg.norm(np.asarray(b) - np.asarray(a)) > 1e-9]


def resolve_point_feed(op, params):
    """``(is_rapid, feed_mm_min)`` for a Point op.

    Default is a rapid: a positioning move is what this op is for, and a rapid is
    what the operator means by "go there". Unticking ``point_rapid`` runs the
    move at the op's own feed instead — for easing into a fixture rather than
    slamming at G0 speed.

    The feed is only meaningful when ``is_rapid`` is False; the recipe format
    requires F=0 on every command except LINEAR (CAM_INTERFACE_SPEC §5).
    """
    is_rapid = bool(op.get("point_rapid", True))
    try:
        feed = float(op.get("feed", params.get("feed_rate_mm_min", 300.0)))
    except (TypeError, ValueError):
        feed = float(params.get("feed_rate_mm_min", 300.0))
    return is_rapid, feed


def resolve_bend_points(op, retract_x_abs=50.0, default_end_x=50.0):
    """Start and end point of a cutting / bending move: ``((sx, sz), (ex, ez))``.

    The op is an ordinary two-point feed line — rapid to START, G1 to END at the
    op's own feed. Both ends are typed by the user, so retract/approach behave
    like they do on a roughing pass and no longer decide the travelled distance.

    LEGACY FALLBACK: recipes written before the split carry only ``z_pos`` (the Z
    of the whole move) and ``plunge_x`` (its END X), with the start derived as
    ``plunge_x + abs(retract_x)``. That is reproduced exactly here, so an
    un-migrated op still runs bit-identical — which matters for op presets and
    ops_library entries, since those stores never pass through migration.
    """
    def _num(key):
        v = op.get(key, None)
        try:
            if v not in (None, ""):
                return float(v)
        except (TypeError, ValueError):
            pass
        return None

    end_x = _num("plunge_end_x")
    if end_x is None:
        _legacy_x = _num("plunge_x")
        end_x = _legacy_x if _legacy_x is not None else float(default_end_x)
    end_z = _num("plunge_end_z")
    if end_z is None:
        _legacy_z = _num("z_pos")
        end_z = _legacy_z if _legacy_z is not None else 0.0

    start_x = _num("plunge_start_x")
    if start_x is None:
        start_x = end_x + abs(float(retract_x_abs))
    start_z = _num("plunge_start_z")
    if start_z is None:
        start_z = end_z
    return (start_x, start_z), (end_x, end_z)


def exit_end_direction(path_pts, span=5.0):
    """Direction the pass is travelling AT ITS TIP, as ``(dx, dz)`` in the X/Z plane.

    Used only by the predicted sheet-edge overlay, to decide which way the leftover
    flange points. The tip is what matters: the operator's rule is that a STRAIGHT pass
    leaves the sheet lying along the roller line, while a CURVED exit bends the free edge
    further than the P2→P3 chord would suggest. Reading the built path captures the curve,
    any auto-align rotation, and a hand-drawn exit tail, without re-deriving any of them.

    Walks back ``span`` mm from the last point before measuring, so the tangent is not
    taken from two adjacent, near-coincident discretisation points. Falls back to the
    whole path when it is shorter than that. Returns ``None`` when there is nothing
    measurable (fewer than 2 points, or a degenerate zero-length path).

    Points are ``[x, y, z]``; this reads the CANONICAL +X frame, i.e. it must be called
    inside ``calculate_paths`` before the final machine-X mirroring.
    """
    pts = np.asarray(path_pts, dtype=float)
    if pts.ndim != 2 or len(pts) < 2 or pts.shape[1] < 3:
        return None
    end = pts[-1]
    j = len(pts) - 2
    while j > 0 and math.hypot(end[0] - pts[j][0], end[2] - pts[j][2]) < span:
        j -= 1
    dx, dz = float(end[0] - pts[j][0]), float(end[2] - pts[j][2])
    return None if math.hypot(dx, dz) < 1e-9 else (dx, dz)


class PathGenerator:
    def __init__(self):
        self.last_calculated_paths = []
        self.last_plc_paths = None         # decimated paths from the last PLC-mode G-code (for clearance/line checks)
        self.last_mandrel_mgr = None
        self.last_tilt_angles = None       # per-path tilt arrays (tilt_arm machines) or None
        self.last_kinematic_warnings = []  # reachability issues from last G-code generation
        self._path_op_map = []             # toolpath index → op dict (parallel to last_calculated_paths)
        self.last_op_end_z = {}            # op-index → CAM Z the op's last forming pass reaches (incl. p2_z_extend)
        self.last_blank_edge = []          # per forming pass: (contact_z, edge_radius) — see calculate_paths
        self.last_tool_change_warnings = []  # custom tool-change points near the turret swing envelope
        self.last_retract_motion_warnings = []  # ops whose retract drags along the part before lifting (z_first)
        self.last_point_warnings = []      # surface-mode Point ops whose Z falls off the mandrel profile
        self.last_point_markers = []       # Point ops: {op_index, x, z, motion, rapid, mode} for the 3D triangle marker
        self.last_point_cap_warnings = []  # #99/#101: fillet or exit caps refused because they would cost clearance
        self.last_waypoint_warnings = []   # #100: hand-drawn exit tails closer than the op clearance
        self.last_waypoint_ignored = []    # #100: tails that are stored but this op cannot use
        self.last_waypoint_shifted = []    # #100: tail passes the safety floor moved outward
        self.last_waypoint_abs = {}        # #100: path index → resolved waypoints for feed emission
        self.last_exit_verbatim = set()    # #100: path indices whose exit tail must NOT be decimated
        self.last_exit_break_counts = {}   # #102: path index → how many breaks shaped its exit leg
        self.last_break_flatten_warnings = []  # #102: exit caps that blunted a break

    def _tc_radial_gap(self, pt, center_x, mandrel_mgr, params, r_tool):
        """Radial clearance (mm) between the roller contact at ``pt`` and the
        outermost part/blank obstacle at that Z. Negative = the roller/tool is
        inside the part envelope (penetration)."""
        try:
            surf_r = float(mandrel_mgr.get_radius_fast(float(pt[2])))
        except Exception:
            surf_r = 0.0
        blank_r     = float(params.get("blank_radius", 0.0) or 0.0)
        blank_thick = float(params.get("final_part_thickness_on_mandrel", 0.0) or 0.0)
        shell       = float(params.get("shell_thickness", 0.0) or 0.0)
        obstacle_r  = max(surf_r, blank_r) + blank_thick + shell
        radial      = abs(float(pt[0]) - center_x)  # roller-center radial pos
        return radial - obstacle_r - float(r_tool)

    def _tool_change_swing_check(self, path_pts, center_x, mandrel_mgr, params, r_tool):
        """Advisory collision check for a CUSTOM tool-change retract. ``path_pts`` is
        the ordered list of waypoints the roller actually travels (2 points for a
        simultaneous diagonal, 3 for the Z-first / X-second split). Returns
        ``(dest_gap, path_min_gap)``:

          dest_gap      radial clearance at the FINAL point — where M6 rotates the
                        turret; a small value means a tool could strike on the swing.
          path_min_gap  the smallest clearance ANYWHERE along the sampled traverse —
                        the retract starts at the part surface, so only a NEGATIVE
                        value (the move dips into the part, e.g. a diagonal cutting a
                        convex corner) signals a rapid-crash. Warn-only — never clips."""
        def gap(pt):
            return self._tc_radial_gap(pt, center_x, mandrel_mgr, params, r_tool)
        pts = [np.asarray(p, dtype=float) for p in path_pts]
        dest_gap = gap(pts[-1])
        mins = [dest_gap]
        for a, b in zip(pts[:-1], pts[1:]):
            for f in np.linspace(0.0, 1.0, 11):
                mins.append(gap(a + (b - a) * f))
        return dest_gap, min(mins)

    def _ensure_ops_dict(self, params):
        """The operation list to run: the caller's, or a legacy migration.

        AN EMPTY LIST IS AN ANSWER, NOT A MISSING ONE. A pre-ops file (and the
        headless callers that still drive the engine through
        `num_sweeping_passes`) has no "operations" key at all, and that is what
        the migration below is for. `operations: []` means something else
        entirely: the operator deleted every operation.

        Until 2026-08-30 both went down the migration, so clearing the program
        did not clear the toolpath — it built a full roughing op out of
        `num_sweeping_passes`, a parameter today's UI does not even show.
        Measured on a real recipe: 12 passes and 1036 lines of motion out of an
        empty list, with nothing on screen to explain where they came from.
        `del_op` has no last-op guard, so it was one Delete key away.

        A non-list value still migrates — that is a malformed file, not an
        instruction.
        """
        ops = params.get("operations", None)
        if isinstance(ops, list):
            return ops

        # Legacy Migration
        ops = []
        
        # 1. Roughing
        num_rough = int(params.get("num_sweeping_passes", 3))
        if num_rough > 0:
            ops.append({
                "type": "roughing",
                "enabled": True,
                "count": num_rough,
                "tool_id": params.get("rough_tool_number", "T0101"),
                "r_tool": params.get("roller_visual_radius", 25.0),
                "start_z": params.get("first_pass_p2_contact_z_abs", 10.0),
                "p1_x": params.get("p1_p3_x_offset_from_p2", 40.0),
                "p1_z": params.get("p1_z_offset_from_p2", 50.0),
                "p3_z": params.get("p3_z_offset_from_p2", -20.0),
                "rot": params.get("y_rotation_degrees", 10.0),
                "step": params.get("roughing_step_radial", 1.0),
                "proj_extend_bottom": 0.0,
                "proj_extend_top": 0.0,
            })

        # 2. Finishing
        num_finish = int(params.get("num_finishing_passes", 0))
        if num_finish > 0:
             ops.append({
                "type": "finishing",
                "enabled": True,
                "count": num_finish,
                "tool_id": params.get("finish_tool_number", "T0202"),
                "r_tool": params.get("finish_tool_radius", 25.0),
                "start_z": params.get("first_pass_p2_contact_z_abs", 10.0), 
                "p1_x": params.get("finish_p1_p3_x_offset_from_p2", 10.0),
                "p1_z": params.get("finish_p1_z_offset_from_p2", 10.0),
                "p3_z": params.get("finish_p3_z_offset_from_p2", -10.0),
                "rot": params.get("finish_y_rotation_degrees", 0.0),
                "step": params.get("finish_step_radial", 0.0)
            })
        
        return ops

    def calculate_paths(self, params, overrides, mandrel_mgr, visual_roller_pos=None):
        toolpaths = []
        projections = []
        control_points = []
        deviations = []
        rapids = []
        sequence = [] # Ordered execution list for simulation
        debug_lines = [] # Analysis Lines for Visualization
        self.last_back_pass_meta = {}  # {path_list_index: {"feed": ...}}
        # Back passes asked for on a reverse op and deliberately not built (#49).
        self.last_back_pass_ignored = []
        self.last_render_split_idx = {}  # {path_list_index: (line_end_idx, arc_end_idx)}
        # Same pair remapped onto a REVERSED pass's array — advisory/UI only, see
        # the reverse block below for why it is not merged into the dict above.
        self.last_reverse_split_idx = {}
        self.last_waypoint_warnings = []  # #100: hand-drawn exit tails closer than the op clearance
        self.last_waypoint_ignored = []   # #100: tails that are stored but this op cannot use
        self.last_waypoint_shifted = []   # #100: tail passes the safety floor moved outward
        self.last_waypoint_abs = {}  # #100: path index → resolved waypoints [{x,z,feed}] for feed emission
        self.last_exit_verbatim = set()  # #100: path indices whose exit tail is the operator's own points
        self.last_exit_break_counts = {}  # #102: path index → break count on its exit leg
        self._path_op_map = []  # toolpath index → op dict, synced as paths are appended
        self.last_op_end_z = {}  # op-index → CAM Z the op's last forming pass actually reaches
        self.last_blank_edge = []  # (contact_z, edge_radius) per forming pass — 3D blank-edge overlay
        self.last_op_reach = {}       # op-index → exit reach magnitude of last forming pass (#61)
        self.last_op_end_angle = {}   # op-index → exit angle (deg from +X) of last forming pass (#61)
        self.last_clamp_warnings = []  # ops whose start_z sits inside the clamp zone (#62)
        self.last_flatness_warnings = []  # straight-line finishing ops over a non-constant-angle surface
        self.last_tool_change_warnings = []  # custom tool-change points near the turret swing envelope
        self.last_retract_motion_warnings = []  # z_first retracts (drag along the part) — warn-only
        self.last_point_warnings = []  # surface-mode Points whose Z falls off the mandrel
        # Point ops (2026-09-03). Stored in CANONICAL X — mirrored with everything
        # else at the end of this function, so the marker lands where the move
        # actually goes on a negative-side machine.
        self.last_point_markers = []

        props = mandrel_mgr.props
        top_z = props["top_z"]

        # Clamp / counter-press zone (#62): the base region held by the counter-press is
        # not machined. Phase 1 = warning only (no clipping); flag ops that start inside it.
        clamp_len = effective_clamp_length(params)
        clamp_top_z = (props.get("min_z", 0.0) + clamp_len) if clamp_len > 0 else None
        center_x = params.get("mandrel_pos_x_offset", 0.0)
        blank_thick = params.get("final_part_thickness_on_mandrel", 2.0)
        shell_offset = params.get("shell_thickness", 0.0)

        # Rapids Simulation Params (Match generate_gcode defaults)
        home_x = params.get("home_x", 300.0)
        home_z = params.get("home_z", 150.0)
        # Pass retract is now PER-OP (#90): resolved per operation inside the loop
        # via resolve_pass_retract (op_retract_x_can / op_retract_z).

        # Roller approach side: +1 = positive X (default), -1 = negative X (roller below/behind mandrel)
        # Generation always happens in canonical (positive X) frame; mirrored at the end if side==-1.
        side = 1.0 if params.get("roller_positive_x_side", True) else -1.0
        home_x_can = center_x + abs(home_x - center_x)   # canonical safe home X (positive)

        # Convert visual_roller_pos to canonical coords if on negative side
        if visual_roller_pos is not None and side == -1:
            visual_roller_pos = (2.0 * center_x - visual_roller_pos[0], visual_roller_pos[1], visual_roller_pos[2])

        operations = self._ensure_ops_dict(params)
        global_pass_idx = 0

        # Initial Position (Home) — canonical coordinates
        current_pt = np.array([home_x_can, 0, home_z])
        current_tool = None

        # [NEW] Initial Homing Visualization if visual pos differs from Home
        if visual_roller_pos is not None:
             start_vis = np.array(visual_roller_pos)
             
             # G-Code Header: G0 Z150 (Move Z to Home Z), then G0 X300 (Move X to Home X)
             # Simulate this sequence from visual start.
             
             # 1. Move Z to Home Z (keeping Visual X)
             step1 = np.array([start_vis[0], 0, home_z]) 
             
             # 2. Move X to Home X (at Home Z) -> [Home.X, 0, Home.Z]
             step2 = np.array([home_x_can, 0, home_z])
             
             add_homing = False
             
             # Check if we are far enough to matter
             if np.linalg.norm(start_vis - step1) > 1.0:
                 rapids.append(np.array([start_vis, step1]))
                 sequence.append(("rapid", np.array([start_vis, step1])))
                 add_homing = True
                 
             if np.linalg.norm(step1 - step2) > 1.0:
                 rapids.append(np.array([step1, step2]))
                 sequence.append(("rapid", np.array([step1, step2])))
                 add_homing = True
             
             if add_homing:
                 current_pt = step2

        for op_index, op in enumerate(operations):
            if not op.get("enabled", True): continue

            count = int(op.get("count", 1))
            is_finish = (op.get("type") == "finishing")
            r_tool = float(op.get("r_tool", 25.0))
            # Per-op pass retract (#90, pure per-op): EVERY op type (roughing,
            # finishing, cutting, bending) carries its own retract_x/retract_z;
            # resolve_pass_retract falls back to the legacy global / 50 mm for any
            # un-migrated op. abs() keeps X in the canonical positive frame.
            op_retract_x_raw, op_retract_z = resolve_pass_retract(op, params)
            op_retract_x_can = abs(op_retract_x_raw)
            # Motion order for this op's retract (2026-09-03). Default
            # "synchronized" reproduces the single diagonal every recipe has
            # always used. z_first drags the roller ALONG the part before
            # lifting — warn-only, never clipped (user decision).
            op_retract_motion = resolve_retract_motion(op)
            if retract_motion_is_risky(op_retract_motion):
                self.last_retract_motion_warnings.append({
                    "op_index": op_index,
                    "op_type": op.get("type", "op"),
                    "op_name": op.get("name") or "",
                    "motion": op_retract_motion,
                    "dz": float(op_retract_z),
                })
            # Unified clearance = gap between the roller contact and the blank surface.
            # Single source of truth for EVERY pass type (roughing & finishing alike), so
            # the same value always yields the same contact standoff. Legacy recipes (no
            # `clearance` key) fall back to the old split knobs so their toolpaths are
            # unchanged: finishing = finish_allowance + safety; roughing = target_clearance
            # (the value its old correction loop forced the contact to).
            op_clearance = op.get("clearance")
            if op_clearance is None:
                if is_finish:
                    op_clearance = float(op.get("finish_allowance", 0.0)) + float(params.get("safety_clearance_roller_to_part", 0.0))
                else:
                    op_clearance = float(params.get("target_clearance", 0.0))
            op_clearance = float(op_clearance)
            op_tool_id = op.get("tool_id", "T0101")
            
            # [UPDATED] Tool Change Logic
            # Always simulate movement if ID changes, regardless of M6 flag
            need_tool_change = (op_tool_id != current_tool) or (current_tool is None)
            
            if need_tool_change and current_tool is not None:
                # Resolve the retract target: global home (default), an absolute
                # point, or a point relative to the previous pass end. Same helper
                # the G-code emitter uses, so the 3D sim and the NC program agree.
                # RELATIVE reference = the previous pass's FORMING endpoint
                # (toolpaths[-1][-1]), NOT current_pt (which is the post-per-pass-
                # retract position). This mirrors the emitter's
                # paths_to_use[idx-1][-1] exactly, so sim and NC land on the same
                # tool-change point. The retract MOVE below still starts from
                # current_pt (where the roller physically sits).
                prev_forming_end = (np.asarray(toolpaths[-1][-1], dtype=float)
                                    if len(toolpaths) > 0 else current_pt)
                home_pt = np.array([home_x_can, 0, home_z])
                # Sim frame = canonical (mirrored around center_x at pass end for a
                # negative-side roller). Pass center_x + side so the user's real-frame
                # X/ΔX survives the mirror and matches the G-code exactly.
                tc_target = resolve_tool_change_point(
                    op, prev_forming_end, home_pt, center_x=center_x, side=side)

                end_pt = np.array([tc_target[0], 0, tc_target[2]])
                simultaneous = bool(op.get("tool_change_simultaneous", False))

                if simultaneous:
                    # Single coordinated diagonal move — both axes travel together.
                    # Faster, but the straight line can cut a convex corner, so the
                    # traverse is collision-checked below.
                    tc_waypoints = [current_pt, end_pt]
                    if np.linalg.norm(current_pt - end_pt) > 1.0:
                        r_seg = np.array([current_pt, end_pt])
                        rapids.append(r_seg)
                        sequence.append(("rapid", r_seg))
                else:
                    # Split move: Z first (keeping current X), then X — keeps the
                    # roller clear of the part axially before traversing in X.
                    safe_mid = np.array([current_pt[0], 0, tc_target[2]])
                    tc_waypoints = [current_pt, safe_mid, end_pt]
                    if np.linalg.norm(current_pt - safe_mid) > 1.0:
                        r_seg1 = np.array([current_pt, safe_mid])
                        rapids.append(r_seg1)
                        sequence.append(("rapid", r_seg1))
                    if np.linalg.norm(safe_mid - end_pt) > 1.0:
                        r_seg2 = np.array([safe_mid, end_pt])
                        rapids.append(r_seg2)
                        sequence.append(("rapid", r_seg2))

                current_pt = end_pt

                # Sim-only marker: a brief on-screen cue + dwell at the change point
                # so a fast playback shows WHERE the tool change happens and which
                # tool takes over. Ignored by the G-code emitter (which reads paths,
                # not the sequence). Fires for every tool change, any mode.
                sequence.append(("toolchange",
                                 np.array([end_pt[0], 0.0, end_pt[2]]),
                                 str(current_tool), str(op_tool_id)))

                # Warn-only guard for a custom (non-global) change point: (a) the
                # destination may sit in the turret swing envelope (M6 strike), and
                # (b) the retract traverse may dip into the part (rapid crash — only
                # possible with the diagonal move). Advisory — never clips.
                if str(op.get("tool_change_mode", "global") or "global").lower() != "global":
                    dest_gap, path_min_gap = self._tool_change_swing_check(
                        tc_waypoints, center_x, mandrel_mgr, params, r_tool)
                    if dest_gap < TOOL_CHANGE_SWING_MARGIN_MM or path_min_gap < 0.0:
                        self.last_tool_change_warnings.append({
                            "op_index": op_index,
                            "op_type": op.get("type", "op"),
                            "mode": str(op.get("tool_change_mode", "global")),
                            "simultaneous": simultaneous,
                            "x": float(end_pt[0]), "z": float(end_pt[2]),
                            "gap": float(dest_gap),
                            "path_gap": float(path_min_gap),
                        })

            current_tool = op_tool_id

            op_type_str = op.get("type", "roughing")

            # --- Point: go to ONE typed position and stop ---------------------
            # Contributes NO toolpath and does NOT advance global_pass_idx — see
            # the module comment on AXIS_MOTION_MODES. generate_gcode skips it
            # the same way, so the shared path index stays aligned.
            #
            # No retract: a retract runs after the move and would immediately
            # undo the position the operator just asked for. Leaving a point in a
            # controlled way is a second Point op, visible in the list rather
            # than hidden in a field (user decision 2026-09-03).
            if op_type_str == "point":
                # "relative" measures from the previous pass's FORMING end
                # (toolpaths[-1][-1]), NOT from current_pt. current_pt includes
                # the retract, and the emitter has no equivalent of it — using
                # it here would make the 3D view and the .nc disagree. This is
                # the same anchor, chosen for the same reason, as the
                # tool-change "relative" mode.
                _pt_prev = (np.asarray(toolpaths[-1][-1], dtype=float)
                            if len(toolpaths) > 0 else None)
                pt_target = resolve_point_target(
                    op, center_x=center_x, side=side, params=params,
                    mandrel_mgr=mandrel_mgr, prev_end=_pt_prev,
                    home_pt=np.array([home_x_can, 0.0, home_z]))
                pt_mode = resolve_point_mode(op)

                # Surface mode with a Z off the end of the mandrel would read a
                # clamped radius and drive somewhere the operator did not mean.
                # Warn-only, like every other advisory here.
                if pt_mode == "surface":
                    _mz = float(props.get("min_z", 0.0))
                    _tz = float(props.get("top_z", 0.0))
                    _pz = float(pt_target[2])
                    if not (min(_mz, _tz) - 1e-6 <= _pz <= max(_mz, _tz) + 1e-6):
                        self.last_point_warnings.append({
                            "op_index": op_index,
                            "z": _pz, "min_z": _mz, "top_z": _tz,
                        })
                pt_motion = resolve_point_motion(op)
                pt_rapid, pt_feed = resolve_point_feed(op, params)
                waypoints = motion_waypoints(current_pt, pt_target, pt_motion)

                for a, b in zip(waypoints, waypoints[1:]):
                    seg = np.array([a, b])
                    if np.linalg.norm(b - a) <= 1e-6:
                        continue
                    if pt_rapid:
                        rapids.append(seg)
                        sequence.append(("rapid", seg))
                    else:
                        # A fed Point still is not a toolpath — it removes no
                        # material and must not be coloured or counted as a pass.
                        # The sim gets it as a "cut" only so playback runs it at
                        # the commanded feed instead of rapid speed.
                        sequence.append(("cut", seg, r_tool, op_tool_id, pt_feed))

                current_pt = pt_target
                self.last_point_markers.append({
                    "op_index": op_index,
                    "x": float(pt_target[0]), "z": float(pt_target[2]),
                    "motion": pt_motion, "rapid": bool(pt_rapid),
                    "mode": pt_mode,
                })
                # "Where this op ended" for the Real End Z column / Continue⤵.
                self.last_op_end_z[op_index] = float(pt_target[2])
                continue

            # --- Cutting / Bending: one feed line from START to END, single pass ---
            # Both ends are typed by the user (resolve_bend_points); the retract
            # below is the plain per-op retract, same as any roughing pass.
            if op_type_str in ("cutting", "bending"):
                (start_x, start_z), (end_x, end_z) = resolve_bend_points(
                    op, op_retract_x_can, center_x + 50.0)

                prev_paths_len = len(toolpaths)
                path = np.array([[start_x, 0.0, start_z],
                                 [end_x,   0.0, end_z]])
                toolpaths.append(path)
                projections.append(np.array([[end_x, 0.0, end_z]]))
                control_points.append(np.array([[end_x, 0.0, end_z]]))
                deviations.append(np.array([0.0, 0.0]))

                if len(toolpaths) > prev_paths_len:
                    start_pt = path[0]
                    end_pt   = path[-1]
                    for seg in self._safe_rapid_segments(current_pt, start_pt, current_pt[0]):
                        rapids.append(seg)
                        sequence.append(("rapid", seg))
                    sequence.append(("cut", path, r_tool, op_tool_id,
                                     representative_feed_mm_min(op, path, params, center_x)))
                    for r_seg in retract_segments(end_pt, op_retract_x_can,
                                                  op_retract_z, op_retract_motion):
                        rapids.append(r_seg)
                        sequence.append(("rapid", r_seg))
                        current_pt = r_seg[-1]

                while len(self._path_op_map) < len(toolpaths):
                    self._path_op_map.append(op)
                # Cutting/bending "reach" is where the feed line ends.
                self.last_op_end_z[op_index] = end_z
                global_pass_idx += 1
                continue

            # Op Params
            def_p1_x = float(op.get("p1_x", 40.0)); def_p1_z = float(op.get("p1_z", 50.0))
            def_p3_x = float(op.get("p3_x", def_p1_x))
            def_p3_z = float(op.get("p3_z", -20.0)); def_rot = float(op.get("rot", 0.0))
            start_h = float(op.get("start_z", 10.0))

            # Clamp-zone advisory (#62): warn (do not clip) if this op begins inside the
            # counter-press region. Uses a small epsilon so a start exactly at the top edge
            # is fine.
            if clamp_top_z is not None and start_h < clamp_top_z - 1e-6:
                # Soften the advisory when start-fillet straightening is enabled AND this
                # op is one that straightening applies to (roughing, or straight-line
                # finishing): the low start is then intentional (starting behind the
                # radius), so surface it as a calm note rather than the amber alarm/modal.
                # Sweeping/adaptive finishing is NOT straightened, so its low start still
                # gets the full warning.
                _op_straightened = params.get("straighten_start_fillet", False) and (
                    (not is_finish)
                    or (op.get("straight_line_mode", False)
                        and not params.get("finish_trace_mandrel_profile", False)))
                self.last_clamp_warnings.append({
                    "op_index": op_index,
                    "op_type": op.get("type", "roughing"),
                    "start_z": start_h,
                    "clamp_top_z": clamp_top_z,
                    "softened": bool(_op_straightened),
                })

            # end_z operasyona özeldir; tanımlıysa kullan, yoksa mandrel tepesine git
            op_end_z = op.get("end_z", None)
            end_h = float(op_end_z) if op_end_z is not None else top_z

            # Straight-line finishing flatness advisory: the 2-point line is only
            # clearance-correct on a constant-angle (conical) span. Warn (do NOT change
            # the path) if the surface between start_z and end_z bows off that chord.
            # Only when the straight_line branch will actually run (finishing + not the
            # global adaptive/trace mode).
            if (is_finish and op.get("straight_line_mode", False)
                    and not params.get("finish_trace_mandrel_profile", False)
                    and params.get("straight_line_flatness_warn", True)):
                _fl_tol = float(params.get("straight_line_flatness_tol", 0.15))
                _fl_dev = self._straight_line_flatness_dev(mandrel_mgr, start_h, end_h, shell_offset)
                if _fl_dev is not None and abs(_fl_dev) > _fl_tol:
                    self.last_flatness_warnings.append({
                        "op_index": op_index,
                        "op_type": op.get("type", "finishing"),
                        "start_z": start_h,
                        "end_z": end_h,
                        "max_dev": _fl_dev,   # + = bulges toward tool (clearance loss)
                        "tol": _fl_tol,
                    })

            # Record the CAM Z where this op's LAST forming pass actually reaches,
            # for the Program-tab "Real End Z" column. This mirrors the per-pass
            # target_z/contact_z math below (lines ~294-300) for the last pass:
            #   roughing: contact = target_z + p2_z_extend, where target_z is
            #             start_h for a single pass, else end_h (the last pass).
            #   finishing: sweeps the whole zone start_h→end_h, so its end is end_h
            #             (no p2_z_extend — it is forced to 0 for finishing).
            if is_finish:
                self.last_op_end_z[op_index] = end_h
            else:
                _last_target_z = start_h if count <= 1 else end_h
                self.last_op_end_z[op_index] = _last_target_z + float(op.get("p2_z_extend", 0.0))


            # Auto-Align Feature: Read from params
            auto_align = params.get("auto_calc_angle", True)
            
            for i in range(count):
                ovr = overrides.get(global_pass_idx, {})
                if is_finish:
                     p1_x    = ovr.get("finish_p1_p3_x_offset_from_p2", def_p1_x)
                     p1_z    = ovr.get("finish_p1_z_offset_from_p2", def_p1_z)
                     p3_x    = p1_x
                     p3_z    = ovr.get("finish_p3_z_offset_from_p2", def_p3_z)
                     base_rot = ovr.get("finish_y_rotation_degrees", def_rot)
                else:
                     p1_x    = ovr.get("p1_p3_x_offset_from_p2", def_p1_x)
                     p1_z    = ovr.get("p1_z_offset_from_p2",    def_p1_z)
                     p3_x    = def_p3_x
                     p3_z    = ovr.get("p3_z_offset_from_p2",    def_p3_z)
                     base_rot = ovr.get("y_rotation_degrees",    def_rot)
                
                
                # Normalize p3_z to positive convention: op stores it negative (e.g. -20) as a user
                # convenience but _create_and_store_pass now uses it signed (+ = forward in Z).
                p3_z = abs(p3_z)

                # ── Per-pass pins (pass_edits) — read BEFORE target_z: the per-pass
                # Anchor Z pin overrides target_z, and the follow-blank reach needs
                # this pass's Z. #89 Phase 2 per-pass editor keys: target_z (anchor),
                # p2_z_extend (extend), clearance, plus the existing pass_angle / reach.
                # LENGTH priority : pass pin > follow-blank > progressive fan > reach > |p3|.
                # DIRECTION prio. : pass pin > progressive angle fan > pass_angle.
                # All roughing-only; absent by default → identical to before.
                _pe_all = op.get("pass_edits") or {}
                _pe = _pe_all.get(str(i)) or _pe_all.get(i) or {}
                def _pe_f(_k, _d=_pe):
                    _v = _d.get(_k, None)
                    try:
                        return float(_v) if _v not in (None, "") else None
                    except (TypeError, ValueError):
                        return None
                _edit_angle     = _pe_f("pass_angle") if not is_finish else None
                _edit_reach     = _pe_f("reach") if not is_finish else None
                _edit_clearance = _pe_f("clearance") if not is_finish else None
                _edit_target_z  = _pe_f("target_z") if not is_finish else None
                _edit_p2ext     = _pe_f("p2_z_extend") if not is_finish else None
                eff_clearance = _edit_clearance if _edit_clearance is not None else op_clearance

                # Per-pass contact anchor (target Z). Normally stepped start_h→end_h; a
                # per-pass Anchor Z pin overrides it — set every pass equal (pass-table
                # Set-all) and ramp Extend (Progressive) to build an anchored sweep by hand.
                if count <= 1:
                    target_z = start_h
                else:
                    target_z = start_h + (i / (count - 1) * (end_h - start_h))
                if _edit_target_z is not None:
                    target_z = _edit_target_z

                # Reach (#61): single authoritative exit-stroke magnitude |P2→P3|. Unset or
                # <=0 keeps the legacy behavior EXACTLY (magnitude implied by p3_x/p3_z).
                # When set, direction comes from pass_angle (below) or, in raw mode, from the
                # p3_x/p3_z ratio (which is scaled to this length, ratio preserved).
                _reach_v = op.get("reach", None)
                try:
                    _reach_v = float(_reach_v) if _reach_v not in (None, "") else None
                except (TypeError, ValueError):
                    _reach_v = None
                if _reach_v is not None and _reach_v <= 0:
                    _reach_v = None

                # ── Exit DIRECTION for this pass, settled BEFORE any length is chosen.
                # Direction and length are independent (#61 Option B). It moved up here
                # because follow-blank now needs the direction to work out how long the
                # leaning flange is. Nothing between here and the pass-angle block below
                # touches p1_x/p1_z/p3_x/p3_z or _edit_angle, so the block reuses these
                # instead of recomputing them — one derivation, not two.
                # θ_A = angle of P2→P1 from +X in XZ. θ_B = θ_A + pass_angle.
                # linear_approach/linear_full: θ_A is always -90° (pure -Z entry).
                _pa_deg = op.get("pass_angle", None)
                _eff_angle = _theta_B = None
                if _pa_deg is not None:
                    _eff_angle = float(_pa_deg)
                    if op.get("progressive_angle_enabled", False) and count > 1:
                        # Fan target: last pass reaches progressive_angle_end (default
                        # 180° = laid along the surface). Any end value is allowed —
                        # smaller than 180 stops the fan early, smaller than pass_angle
                        # fans downward.
                        try:
                            _prog_end = float(op.get("progressive_angle_end", 180.0))
                        except (TypeError, ValueError):
                            _prog_end = 180.0
                        _eff_angle += i * (_prog_end - _eff_angle) / (count - 1)
                    if _edit_angle is not None:
                        _eff_angle = _edit_angle   # pinned pass: manual beats auto (R2)
                    _shape = op.get("pass_shape", "spline")
                    if _shape in ("linear_approach", "linear_full"):
                        _theta_A = -math.pi / 2
                    else:
                        _px, _pz = abs(p1_x), abs(p1_z)
                        _theta_A = math.atan2(-_pz, _px) if _px > 0.001 else -math.pi / 2
                    _theta_B = _theta_A + math.radians(_eff_angle)
                    _exit_dir = (math.cos(_theta_B), math.sin(_theta_B))
                else:
                    # Raw exit mode: direction is the p3_x/p3_z ratio, untouched.
                    _exit_dir = (p3_x, p3_z)

                _follow_reach = None
                if not is_finish and op.get("reach_follow_blank", False):
                    _R_blank = float(params.get("blank_radius", 0.0) or 0.0)
                    if _R_blank > 0:
                        try:
                            from process_planner import (estimate_flange_reach,
                                                         flange_slant_length)
                            _fr = estimate_flange_reach(mandrel_mgr, _R_blank, target_z)
                        except Exception:
                            _fr = 0.0
                        if _fr > 0:
                            # FLAT → SLANT. estimate_flange_reach answers "how far does
                            # the sheet stick out SIDEWAYS". The stroke does not travel
                            # sideways, it travels along the EXIT, and the same material
                            # leaning that way is LONGER. Without this the pass stops
                            # short of the sheet edge, and the shortfall grows with the
                            # pass angle: 0% flat, ~6% at 40°, ~14% at 60°, ~41% at 90°.
                            # That is what operators were cancelling out by hand when they
                            # typed 1.2 / 1.5 into the blank factor. Flat exits return the
                            # identical number, so those programs do not move.
                            # `reach_blank_flat_legacy` restores the old short stroke for
                            # a program already proven on the machine.
                            if not op.get("reach_blank_flat_legacy", False):
                                try:
                                    _fr = flange_slant_length(
                                        mandrel_mgr.get_radius_fast(target_z) + shell_offset,
                                        _fr, *_exit_dir)[0]
                                except Exception:
                                    pass
                            try:
                                _fb_fac = float(op.get("reach_blank_factor") or 1.0)
                            except (TypeError, ValueError):
                                _fb_fac = 1.0
                            try:
                                _fb_off = float(op.get("reach_blank_offset") or 0.0)
                            except (TypeError, ValueError):
                                _fb_off = 0.0
                            _follow_reach = max(_fr * _fb_fac + _fb_off, 0.0)
                            # Degenerate-flange guard (2026-07-22): at the very base
                            # estimate_flange_reach collapses to ~(blank - r_base). On a
                            # barely-oversized blank that residual is only a few mm, so it
                            # would make ONLY the first pass a short stub while every pass
                            # above (where the model already returns 0) falls back to the
                            # full progressive reach — the "short first pass" bug. Treat a
                            # sub-floor residual as exhausted (None) so the first pass
                            # falls back like the rest. Follow-blank is already opt-in and
                            # healthy flanges (tens of mm, smoothly decreasing) are well
                            # above the floor, so they are untouched. Over-reaching outward
                            # is the safe direction (away from the part; clearance is still
                            # checked on the real mandrel).
                            #
                            # Below the base (target_z <= min_z) there is NO part and so no
                            # flange: the estimate is unphysical there and actually GROWS as
                            # you go more negative (it would sneak back above the floor and
                            # re-shorten the pass). So also fall back for any target at/below
                            # min_z. Healthy recipes never place a forming pass there, so
                            # this changes nothing for them.
                            _fb_min = float(op.get("reach_follow_min", 10.0) or 0.0)
                            _min_z = mandrel_mgr.props.get("min_z", 0.0)
                            if _follow_reach < _fb_min or target_z <= _min_z:
                                _follow_reach = None

                # Pass Angle override — Option B: L3 = |P2→P3| preserved, only direction rotates.
                # p3 = L3 * (cos θ_B, sin θ_B). θ_B (and the progressive fan and the pin
                # that feed it) is resolved once, above the follow-blank block.
                if _pa_deg is not None:
                    _L3 = _reach_v if _reach_v is not None else math.sqrt(p3_x ** 2 + abs(p3_z) ** 2)
                    # Progressive reach: sweep the P2→P3 stroke length across passes,
                    # independent of the direction sweep (progressive_angle). First pass
                    # keeps the current reach, last pass reaches progressive_reach_end.
                    # Orthogonal to the angle fan: θ_B sets direction, _L3 sets length.
                    if op.get("progressive_reach_enabled", False) and count > 1:
                        try:
                            _reach_end = float(op.get("progressive_reach_end", _L3))
                        except (TypeError, ValueError):
                            _reach_end = _L3
                        _L3 = max(_L3 + i * (_reach_end - _L3) / (count - 1), 0.0)
                    if _follow_reach is not None:
                        _L3 = _follow_reach        # follow-blank supersedes fan/reach
                    if _edit_reach is not None:
                        _L3 = _edit_reach          # pinned pass: manual beats all (R2)
                    if _L3 > 0.001:
                        p3_x = _L3 * math.cos(_theta_B)
                        p3_z = _L3 * math.sin(_theta_B)
                        _dbg_warn = " ← p3_x<0: clearance correction will dominate, further angle increase has diminishing effect" if p3_x < 0 else ""
                        logger.info(
                            f"[PARAM_DEBUG] '{op.get('type','?')} {i+1}' (global pass {global_pass_idx+1}): "
                            f"pass_angle={_pa_deg:.1f}° | "
                            f"θ_A={math.degrees(_theta_A):.1f}° + {_pa_deg:.1f}° = θ_B={math.degrees(_theta_B):.1f}° | "
                            f"P3 offset → X={p3_x:+.2f}mm Z={p3_z:+.2f}mm{_dbg_warn}"
                        )
                else:
                    # Raw exit mode (no pass angle): reach scales the (p3_x, p3_z) vector
                    # length, preserving its X/Z ratio (direction). Unset reach → unchanged.
                    # Same length priority as polar: pin > follow-blank > reach.
                    _raw_len = _reach_v
                    if _follow_reach is not None:
                        _raw_len = _follow_reach
                    if _edit_reach is not None:
                        _raw_len = _edit_reach
                    if _raw_len is not None:
                        _cur = math.sqrt(p3_x ** 2 + p3_z ** 2)
                        if _cur > 1e-6:
                            _s = _raw_len / _cur
                            p3_x *= _s
                            p3_z *= _s

                # Record this pass's exit reach + angle for the LAST forming pass so the
                # Program tab can show end-reach / end-angle beside Real End Z (#61).
                if not is_finish and i == count - 1:
                    _fr = math.sqrt(p3_x ** 2 + p3_z ** 2)
                    self.last_op_reach[op_index] = _fr
                    # Report the end angle in the SAME frame the operator authors in.
                    # In pass-angle mode that is _eff_angle (the last pass's pass_angle,
                    # incl. the progressive fan end) measured relative to the approach
                    # direction θ_A — directly comparable to the Pass Angle field.
                    # In raw exit mode there is no pass-angle frame, so fall back to the
                    # absolute exit direction from +X.
                    if _pa_deg is not None:
                        self.last_op_end_angle[op_index] = _eff_angle
                    else:
                        self.last_op_end_angle[op_index] = (
                            math.degrees(math.atan2(p3_z, p3_x)) if _fr > 1e-6 else 0.0)

                # (target_z is computed above the reach block — the per-pass follow
                # reach needs it before P3 is resolved.)
                p2_z_extend = float(op.get("p2_z_extend", 0.0)) if not is_finish else 0.0
                if _edit_p2ext is not None:
                    # #89 per-pass Extend pin (pass table): overrides p2_z_extend for
                    # THIS pass, so its contact reaches target_z + this extend.
                    p2_z_extend = _edit_p2ext
                contact_z   = target_z + p2_z_extend
                # Keep Real End Z correct when the LAST pass's anchor/extent is pinned
                # (Continue-from-previous reads this). Same value as before when unpinned.
                if not is_finish and i == count - 1:
                    self.last_op_end_z[op_index] = contact_z

                # Start edge-fillet straightening (opt-in): below the fillet→wall
                # transition, follow the extrapolated straight wall instead of the
                # small start radius. No-op above the transition or on curved mandrels.
                if params.get("straighten_start_fillet", False):
                    r_contact = mandrel_mgr.get_straightened_radius(contact_z) + shell_offset
                    nx, nz = mandrel_mgr.get_straightened_normal(contact_z)
                else:
                    r_contact = mandrel_mgr.get_radius_fast(contact_z) + shell_offset
                    nx, nz = mandrel_mgr.get_normal_at_z(contact_z)

                # Predicted unformed blank EDGE for this pass — RECORD ONLY, read by the
                # 3D overlay (main.update_blank_edge). Nothing here feeds the toolpath.
                # HOW MUCH sheet is left over is settled here, at contact_z (where the
                # roller actually forms), NOT at the anchor target_z, so it stays correct
                # when Extend is used. WHERE that sheet points is settled after the pass
                # is built, from the real exit curve — see the append below.
                _edge_pending = None
                if not is_finish:
                    try:
                        _R_bl = float(params.get("blank_radius", 0.0) or 0.0)
                        if _R_bl > 0:
                            from process_planner import estimate_flange_reach
                            _edge_pending = (r_contact, contact_z,
                                             estimate_flange_reach(mandrel_mgr, _R_bl,
                                                                   contact_z))
                    except Exception:
                        _edge_pending = None

                total_off = r_tool + blank_thick + eff_clearance
                # Per-op conformal flag: normal-projected P2 placement. Falls back to global conformal_clearance_all_operations.
                conformal = op.get("conformal_clearance_operation_specific", params.get("conformal_clearance_all_operations", False))
                if conformal:
                    p2_x = center_x + r_contact + nx * total_off
                    p2_z = contact_z + nz * total_off
                else:
                    p2_x = center_x + r_contact + total_off
                    p2_z = contact_z

                # Reach is clearance-independent (#61, user 2026-07-05): when reach is set,
                # anchor the exit END to the ZERO-clearance contact reference so two passes
                # with the same reach land at the SAME absolute P3 regardless of clearance.
                # P2 carries the clearance standoff (radial in non-conformal, along the normal
                # in conformal); shifting the P3 offset inward by that clearance component
                # cancels it out of the endpoint. NOTE: exact for base_rot=0 (linear approach
                # / rotation off); auto-rotated splines rotate P3 about P2, so it is
                # approximate there (documented; verify per case). Applies whenever an
                # explicit length is in force — op reach, per-pass follow, or a pin.
                if (_reach_v is not None or _follow_reach is not None
                        or _edit_reach is not None):
                    # GUARD (fold-back + overlap): the clearance cancellation must not push a
                    # forward exit PAST the commanded direction. Near a ~180° fan the exit X
                    # shrinks to ~0; subtracting the full clearance would flip it negative
                    # (fold past vertical, >180° effective). Do NOT clamp the component to 0
                    # either — that would collapse every sub-clearance near-vertical pass onto
                    # the SAME vertical line (overlapping passes). Instead subtract the
                    # clearance ONLY while the component stays >= 0; otherwise KEEP the
                    # commanded exit, so each pass retains its distinct angle. Reach becomes
                    # slightly clearance-dependent at those extreme angles (accepted:
                    # distinctness/geometry wins over exact anchoring there).
                    if conformal:
                        if p3_x - eff_clearance * nx >= 0.0:
                            p3_x -= eff_clearance * nx
                        if p3_z - eff_clearance * nz >= 0.0:
                            p3_z -= eff_clearance * nz
                    else:
                        if p3_x - eff_clearance >= 0.0:
                            p3_x -= eff_clearance

                # [PARAM_DEBUG2] Consolidated FINAL per-pass geometry (read-only trace):
                # contact radius, resolved P2, effective angle, and the final P3 offset
                # AFTER the clearance cancellation above. Use this to compare the first
                # pass against the rest (p2 radius / pass angle / p3x / p3z).
                if not is_finish:
                    _dbg_eff_ang = _eff_angle if _pa_deg is not None else float('nan')
                    _dbg_final_reach = math.hypot(p3_x, p3_z)
                    _dbg_p2_radius = p2_x - center_x
                    logger.info(
                        f"[PARAM_DEBUG2] '{op.get('type','?')} {i+1}' (global pass {global_pass_idx+1}): "
                        f"contact_z={contact_z:.2f} r_contact={r_contact:.3f} "
                        f"P2 radius(X-center)={_dbg_p2_radius:+.3f} P2_z={p2_z:.3f} | "
                        f"pass_angle={('%.1f' % _pa_deg) if _pa_deg is not None else 'raw'}° "
                        f"eff_angle={_dbg_eff_ang:.1f}° | "
                        f"P3 X={p3_x:+.3f} Z={p3_z:+.3f} reach={_dbg_final_reach:.3f}"
                    )

                pass_label = f"{op.get('type').capitalize()} {i+1}"
                
                prev_paths_len = len(toolpaths)
                
                m_min_z = mandrel_mgr.props.get("min_z", 0.0)
                m_top_z = mandrel_mgr.props.get("top_z", 100.0)

                if is_finish:
                    adaptive_mode = params.get("finish_trace_mandrel_profile", False)
                    if adaptive_mode:
                        # NOTE: `straighten_start_fillet` is NOT applied to sweeping /
                        # adaptive (trace-mandrel-profile) finishing. Those modes are meant
                        # to hug the real surface point-by-point, so extrapolating the wall
                        # over the fillet would defeat their purpose. Straightening is
                        # intentionally scoped to STRAIGHT-LINE finishing + ROUGHING only
                        # (see main.py "straighten_start_fillet" and the branches below).
                        conf_start = max(m_min_z, start_h)
                        conf_end   = min(m_top_z, end_h)
                        self._create_adaptive_pass(conf_start, conf_end, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, pass_label, toolpaths, projections, control_points, deviations, params, additional_radial_offset=op_clearance)
                    elif op.get("straight_line_mode", False):
                        total_off = r_tool + blank_thick + op_clearance
                        # Start edge-fillet straightening (opt-in): if start_h sits in the
                        # fillet, sample the extrapolated straight wall so the 2-point line
                        # holds the surface angle instead of tilting into the radius.
                        _straighten = params.get("straighten_start_fillet", False)
                        if _straighten:
                            r_s = mandrel_mgr.get_straightened_radius(start_h) + shell_offset
                            nx_s, nz_s = mandrel_mgr.get_straightened_normal(start_h)
                            r_e = mandrel_mgr.get_straightened_radius(end_h) + shell_offset
                            nx_e, nz_e = mandrel_mgr.get_straightened_normal(end_h)
                        else:
                            r_s = mandrel_mgr.get_radius_fast(start_h) + shell_offset
                            nx_s, nz_s = mandrel_mgr.get_normal_at_z(start_h)
                            r_e = mandrel_mgr.get_radius_fast(end_h) + shell_offset
                            nx_e, nz_e = mandrel_mgr.get_normal_at_z(end_h)
                        p_s = np.array([center_x + r_s + nx_s * total_off, 0.0, start_h + nz_s * total_off])
                        p_e = np.array([center_x + r_e + nx_e * total_off, 0.0, end_h + nz_e * total_off])
                        toolpaths.append(np.array([p_s, p_e]))
                        projections.append(np.array([[center_x + r_s, 0.0, start_h], [center_x + r_e, 0.0, end_h]]))
                        control_points.append(np.array([]))
                        deviations.append(np.array([0.0, 0.0]))
                    else:
                        # (sweeping finishing — surface-hugging, `straighten_start_fillet`
                        # deliberately NOT applied here; see the adaptive-branch note above.)
                        self._create_sweeping_pass(start_h, end_h, mandrel_mgr, center_x, r_tool, blank_thick, op_clearance, shell_offset, pass_label, toolpaths, projections, control_points, deviations, safety_clearance=0.0)
                else:
                    # effective_p1_z extends the approach arm so its START stays at target_z - p1_z
                    # while its END reaches contact_z = target_z + p2_z_extend.
                    effective_p1_z = p1_z + p2_z_extend
                    # #100: this pass's hand-drawn exit tail, if any. get_points
                    # applies the D10 exclusions itself, so a reverse or back-pass
                    # op yields [] even if a hand-edited .ssp carries points.
                    _wp = exit_waypoints.get_points(op, i)
                    # A tail the operator drew that this op cannot use (reverse /
                    # back pass / a pass_shape that ignores it) is dropped in
                    # silence otherwise — the very thing the research flagged.
                    if not _wp:
                        _n_stored = exit_waypoints.stored_count(op, i)
                        if _n_stored:
                            self.last_waypoint_ignored.append({
                                "op_name": (op or {}).get("name")
                                           or (op or {}).get("type", "?"),
                                "pass_name": pass_label,
                                "n_points": _n_stored,
                                "reason": exit_waypoints.excluded_reason(op) or "?",
                            })
                    # #102: this pass's break points. Its own list when it has
                    # one, otherwise the op's legacy single exit_mid break — so
                    # a program saved before this feature cuts identically.
                    _brk = exit_breaks.get_breaks(op, i)
                    self._create_and_store_pass(p1_x, effective_p1_z, p3_z, p3_x, gp_Pnt(p2_x, 0, p2_z), base_rot, auto_align, toolpaths, projections, control_points, deviations, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, pass_label, params, debug_lines, op=op, op_clearance=eff_clearance, exit_points=_wp, exit_shape=exit_waypoints.get_shape(op, i), breaks=_brk)

                # Lay the leftover flange along the exit the roller ACTUALLY drove, taken
                # as the END tangent of the generated path rather than the P2→P3 chord.
                # Operator's rule (2026-09-03): a STRAIGHT pass leaves the sheet following
                # the roller line — chord and tangent agree, so those are unchanged — but a
                # CURVED exit bends the free edge FURTHER, which is deliberate (it stiffens
                # the sheet). Reading the built path also picks up auto-align rotation and
                # any hand-drawn exit tail for free. Still RECORD ONLY.
                if _edge_pending is not None and len(toolpaths) > prev_paths_len:
                    try:
                        from process_planner import flange_edge_along_exit
                        _dir = exit_end_direction(toolpaths[-1])
                        _r_c, _c_z, _fr_e = _edge_pending
                        # A used-up flange has no free EDGE to draw. Without this the ring
                        # collapses onto the mandrel surface and reads as "the sheet edge
                        # is here", when the truth is that there is no loose sheet left —
                        # which is what a pass anchored at the mandrel nose produces.
                        if _dir is not None and _fr_e > 0.5:
                            _e_r, _e_z = flange_edge_along_exit(_r_c, _c_z, _fr_e, *_dir)
                            self.last_blank_edge.append((float(_e_z), float(_e_r)))
                    except Exception:
                        pass

                # Check newly added path for Rapids
                if len(toolpaths) > prev_paths_len:
                    new_path = toolpaths[-1]
                    if len(new_path) > 0:

                        # ── Reverse direction: traverse this pass in the inverse
                        # direction (e.g. top→root). Geometry is identical — only the
                        # point order flips, so G-code/SCL emission, the rapid
                        # approach/retract ends, and simulation all run inverted. This
                        # is cut-direction-only: the pass-to-pass progression order
                        # (set by the outer `for i in range(count)` loop) is untouched.
                        # The straight-arm/exit-curve split index no longer maps after
                        # reversal, so drop it and let rendering/PLC fall back to corner
                        # detection (geometrically identical for a reversed point set).
                        if op.get("direction", "forward") == "reverse":
                            _rev_idx = len(toolpaths) - 1
                            _fwd_split = self.last_render_split_idx.get(_rev_idx)
                            new_path = np.array(new_path, dtype=float)[::-1]
                            toolpaths[-1] = new_path
                            if len(projections[-1]) > 0:
                                projections[-1] = np.array(projections[-1])[::-1]
                            if len(deviations[-1]) > 0:
                                deviations[-1] = np.array(deviations[-1])[::-1]
                            self.last_render_split_idx.pop(_rev_idx, None)
                            # ADVISORY ONLY (#102 on reverse passes, 2026-08-29).
                            # The dropped split is what tells a UI which slice of
                            # the array is the exit leg; without it the break-point
                            # editor measured its clearance advisory across the
                            # WHOLE path and re-applied the breaks to a leg that
                            # already had them. Remapped here (index i of an
                            # n-point array becomes n-1-i, so the pair also swaps
                            # ends) into a SEPARATE dict, deliberately not back
                            # into `last_render_split_idx`: the decimator reads
                            # that one, and handing it a split for reverse passes
                            # would switch them to 3-region RDP and wake up the
                            # #99/#101 point caps — a real change to what ships to
                            # the machine, which is TODO #82's call to make, not
                            # this one's.
                            #
                            # No back-pass caveat needed: a reverse op no longer
                            # builds one at all (see the block below), so nothing
                            # downstream rebuilds or swaps these arrays and the
                            # mapping keeps describing `toolpaths[_rev_idx]`.
                            if _fwd_split is not None:
                                _n_rev = len(new_path)
                                self.last_reverse_split_idx[_rev_idx] = (
                                    _n_rev - 1 - _fwd_split[1],
                                    _n_rev - 1 - _fwd_split[0],
                                )

                        # ── Compute back pass path first (needed before sequence so swap can be applied) ──
                        _bp_path = None
                        _bp_feed = None
                        _bp_proj = None
                        _bp_devs = None
                        # A back pass is a RETURN STROKE: the reverse half of a
                        # forward pass, run continuously without stopping. So
                        # "the back pass of a reverse pass" is not a thing —
                        # a reverse pass IS the return (user, 2026-08-29, closing
                        # the question TODO #49 left open: "confirm that's
                        # acceptable or gate it").
                        #
                        # It was not merely redundant, it was wrong: the split
                        # index is dropped above, so the branch below fell into
                        # the whole-path mirror meant for spline shapes and the
                        # stroke retraced the P1→P2 positioning arm — which on a
                        # tapered mandrel pushed the whole return 15 mm off the
                        # part, doing no work at all. Reported rather than
                        # dropped in silence; see TODO #82's sibling finding.
                        if (op.get("back_pass_enabled", False)
                                and op.get("direction", "forward") == "reverse"):
                            self.last_back_pass_ignored.append({
                                "op_name": op.get("name") or op.get("type", "?"),
                                "pass_name": pass_label,
                            })
                            logger.info(
                                f"[#49] '{pass_label}' back pass NOT built: this is a "
                                f"reverse pass, which already IS the return stroke")
                        elif op_builds_back_pass(op):
                            _bp_feed = float(op.get("back_pass_feed", float(op.get("feed", 100.0))))
                            bp_arc_x    = float(op.get("back_pass_arc_x", 0.0))
                            bp_arc_z    = float(op.get("back_pass_arc_z", 0.0))
                            _fwd_idx    = len(toolpaths) - 1
                            _fwd_splits = self.last_render_split_idx.get(_fwd_idx)

                            if _fwd_splits is not None:
                                # True mirror: reuse the forward FORMING portion verbatim,
                                # reversed. new_path[_line_end:] is T1 → (P2 fillet) → exit
                                # → P3, so the back pass follows p2_radius and the exit
                                # curve exactly — bp_arc=0 gives a bit-exact reverse of the
                                # forward forming stroke. The straight approach arm
                                # (new_path[:_line_end], parallel to the mandrel axis) is
                                # intentionally excluded: it is pure positioning, an ironing
                                # back-stroke should not retrace it, and on tapered mandrels
                                # its lower end forced the whole pass outward.
                                _line_end, _ = _fwd_splits
                                forming_part = np.array(new_path[_line_end:], dtype=float)
                                _bp_path = forming_part[::-1].copy()

                                # bp_arc_x/z: smooth parabolic bow of the curve, zero at the
                                # P3 and T1 endpoints (so continuity with the approach/retract
                                # and the fillet tangency are preserved), peaking at mid-span.
                                if (abs(bp_arc_x) > 1e-9 or abs(bp_arc_z) > 1e-9) and len(_bp_path) >= 3:
                                    _tt = np.linspace(0.0, 1.0, len(_bp_path))
                                    _w  = 4.0 * _tt * (1.0 - _tt)
                                    _bp_path = _bp_path + np.outer(_w, np.array([bp_arc_x, 0.0, bp_arc_z]))

                                # Clearance correction via the same uniform-radial-shift
                                # principle the forward spline pass uses (segment-aware, no
                                # Z-range blind spot), so the back pass obeys the exact same
                                # clearance guarantee even after a bp_arc bow.
                                _bp_target_clearance = eff_clearance
                                _bp_path = self._correct_clearance_uniform(
                                    _bp_path, mandrel_mgr, center_x, r_tool, blank_thick,
                                    shell_offset, _bp_target_clearance)
                            else:
                                # Shapes with no tracked straight-line boundary (e.g.
                                # "spline"): mirror the forward path as a whole.
                                _bp_path = np.array(new_path)[::-1]

                                if (abs(bp_arc_x) > 1e-9 or abs(bp_arc_z) > 1e-9) and len(_bp_path) >= 3:
                                    _tt = np.linspace(0.0, 1.0, len(_bp_path))
                                    _w  = 4.0 * _tt * (1.0 - _tt)
                                    _bp_path = _bp_path + np.outer(_w, np.array([bp_arc_x, 0.0, bp_arc_z]))

                                _bp_target_clearance = eff_clearance
                                _bp_path = self._correct_clearance_uniform(
                                    _bp_path, mandrel_mgr, center_x, r_tool, blank_thick,
                                    shell_offset, _bp_target_clearance)

                            _bp_proj, _bp_devs = self._compute_proj_and_devs(
                                _bp_path, mandrel_mgr, center_x,
                                shell_offset, blank_thick, r_tool, op)

                        # ── Swap: old back pass becomes new forward, old forward becomes new back ──
                        # When swapped, the back pass arc (P3→P2) is reversed to run P2→P3 as the
                        # first stroke; the original forward path is reversed (P3→P1) as the second.
                        _swapped = op.get("back_pass_swapped", False) and _bp_path is not None
                        if _swapped:
                            fwd_path = _bp_path[::-1]
                            bck_path = np.array(new_path)[::-1]
                            bck_feed = _bp_feed
                            fwd_proj = np.array(projections[-1]) if len(projections[-1]) > 0 else np.array([])
                            fwd_devs = np.array(deviations[-1]) if len(deviations[-1]) > 0 else np.array([])
                            bck_proj = _bp_proj if len(_bp_proj) > 0 else np.array([])
                            bck_devs = _bp_devs if len(_bp_devs) > 0 else np.array([])
                            toolpaths[-1]   = fwd_path
                            projections[-1] = fwd_proj
                            deviations[-1]  = fwd_devs
                        else:
                            fwd_path = new_path
                            bck_path = _bp_path
                            bck_feed = _bp_feed
                            bck_proj = _bp_proj
                            bck_devs = _bp_devs

                        start_pt = fwd_path[0]
                        end_pt   = fwd_path[-1]

                        # 1. Rapid to Start — X is already retracted; use retract X as clearance, not full home X
                        for seg in self._safe_rapid_segments(current_pt, start_pt, current_pt[0]):
                            rapids.append(seg)
                            sequence.append(("rapid", seg))

                        # Cut Path
                        sequence.append(("cut", fwd_path, r_tool, op_tool_id,
                                         representative_feed_mm_min(op, fwd_path, params, center_x)))
                        current_pt = end_pt

                        # Back pass (or swapped back pass)
                        if bck_path is not None:
                            # No retract between forward and back pass — the forward ends
                            # at P3 and the (mirror) back pass starts at the same P3, so the
                            # roller flows straight into the return stroke. Only bridge with
                            # a safe move if a bp_arc bow / clearance shift moved the back
                            # pass start away from the forward end.
                            self.last_back_pass_meta[len(toolpaths)] = {"feed": bck_feed}
                            toolpaths.append(bck_path)
                            projections.append(bck_proj)
                            control_points.append(np.array([]))
                            deviations.append(bck_devs)
                            bp_s = bck_path[0]
                            bp_e = bck_path[-1]
                            if np.linalg.norm(current_pt - bp_s) > 1e-3:
                                for seg in self._safe_rapid_segments(current_pt, bp_s, current_pt[0]):
                                    rapids.append(seg)
                                    sequence.append(("rapid", seg))
                            sequence.append(("cut", bck_path, r_tool, op_tool_id,
                                             representative_feed_mm_min({**op, "feed": bck_feed},
                                                                        bck_path, params, center_x)))
                            for r_seg in retract_segments(bp_e, op_retract_x_can,
                                                          op_retract_z, op_retract_motion):
                                rapids.append(r_seg)
                                sequence.append(("rapid", r_seg))
                                current_pt = r_seg[-1]
                        else:
                            # No back pass: retract after the forward pass as usual.
                            for r_seg in retract_segments(end_pt, op_retract_x_can,
                                                          op_retract_z, op_retract_motion):
                                rapids.append(r_seg)
                                sequence.append(("rapid", r_seg))
                                current_pt = r_seg[-1]

                # Keep the path→op map in sync with everything appended during
                # this pass (forward + optional back pass), whatever the branch.
                while len(self._path_op_map) < len(toolpaths):
                    self._path_op_map.append(op)
                global_pass_idx += 1

        # [NEW] Final Return to Home
        # User requested roller to return to Safety Home Position at end.
        # The target is the Program End point, which defaults to Program Start —
        # so with no end point set this is the same move it always was. Built in
        # the canonical positive-X frame like everything else here, then mirrored
        # below with the rest of the paths when the roller sits on the -X side.
        end_x_cam, end_z_cam = resolve_program_end(params)
        end_x_can = center_x + abs(end_x_cam - center_x)
        home_pt = np.array([end_x_can, 0, end_z_cam])

        if np.linalg.norm(current_pt - home_pt) > 1.0:
            for seg in self._safe_rapid_segments(current_pt, home_pt, home_x_can):
                rapids.append(seg)
                sequence.append(("rapid", seg))
        
        # Mirror all X coordinates if roller is on negative X side
        if side == -1.0:
            def _mirror_pts(arr):
                """Mirror numpy array (N,3) in X around center_x."""
                a = np.array(arr, dtype=float)
                a[:, 0] = 2.0 * center_x - a[:, 0]
                return a

            toolpaths = [_mirror_pts(p) for p in toolpaths]
            projections = [_mirror_pts(p) for p in projections]

            mirrored_cp = []
            for cp in control_points:
                mc = np.array(cp, dtype=float)
                if mc.ndim == 2:
                    mc[:, 0] = 2.0 * center_x - mc[:, 0]
                mirrored_cp.append(mc)
            control_points = mirrored_cp

            mirrored_rapids = []
            for seg in rapids:
                s = np.array(seg, dtype=float)
                s[:, 0] = 2.0 * center_x - s[:, 0]
                mirrored_rapids.append(s)
            rapids = mirrored_rapids

            mirrored_debug = []
            for seg in debug_lines:
                # format: [p_pass, p_mandrel, status, clearance_value]
                p0 = np.array(seg[0], dtype=float); p0[0] = 2.0 * center_x - p0[0]
                p1 = np.array(seg[1], dtype=float); p1[0] = 2.0 * center_x - p1[0]
                mirrored_debug.append([p0, p1] + list(seg[2:]))
            debug_lines = mirrored_debug

            mirrored_seq = []
            for item in sequence:
                kind = item[0]
                if kind == "rapid":
                    s = np.array(item[1], dtype=float)
                    s[:, 0] = 2.0 * center_x - s[:, 0]
                    mirrored_seq.append(("rapid", s))
                elif kind == "cut":
                    mirrored_seq.append(("cut", _mirror_pts(item[1]), item[2]) + item[3:])
                elif kind == "toolchange":
                    p = np.array(item[1], dtype=float)
                    p[0] = 2.0 * center_x - p[0]
                    mirrored_seq.append(("toolchange", p) + tuple(item[2:]))
                else:
                    mirrored_seq.append(item)
            sequence = mirrored_seq

            # Point markers were stored canonical, like every other X above. The
            # triangle has to land where the move actually goes, or the 3D view
            # points at the mirror image of the operator's own setpoint.
            for _m in self.last_point_markers:
                _m["x"] = 2.0 * center_x - _m["x"]

        # ── Per-point tilt angles (tilt-arm machines only, e.g. ID112) ──────
        # Built AFTER mirroring: tilt derives from each point's Z in both modes
        # (mirror-invariant, direction-invariant — back passes need no special
        # handling, the same Z always yields the same angle).
        kin = get_kinematics(params)
        if kin is not None:
            self.last_tilt_angles = [
                self._compute_tilt_for_path(
                    np.array(pth, dtype=float),
                    self._path_op_map[idx] if idx < len(self._path_op_map) else None,
                    mandrel_mgr, kin,
                )
                for idx, pth in enumerate(toolpaths)
            ]
        else:
            self.last_tilt_angles = None

        if self.last_clamp_warnings:
            _w = self.last_clamp_warnings[0]
            logger.warning(
                f"[CLAMP] {len(self.last_clamp_warnings)} op(s) start inside the clamp zone "
                f"(top Z={_w['clamp_top_z']:.1f}); first: op #{_w['op_index'] + 1} "
                f"'{_w['op_type']}' start_z={_w['start_z']:.1f}")

        if self.last_flatness_warnings:
            _f = self.last_flatness_warnings[0]
            logger.warning(
                f"[FLATNESS] {len(self.last_flatness_warnings)} straight-line finishing op(s) "
                f"over a non-constant-angle surface; first: op #{_f['op_index'] + 1} "
                f"Z {_f['start_z']:.1f}->{_f['end_z']:.1f} max_dev={_f['max_dev']:+.2f}mm "
                f"(tol {_f['tol']:.2f})")

        if self.last_point_warnings:
            _pw = self.last_point_warnings[0]
            logger.warning(
                f"[POINT] {len(self.last_point_warnings)} surface-mode Point op(s) "
                f"with a Z off the mandrel; first: op #{_pw['op_index'] + 1} "
                f"Z={_pw['z']:.1f} (profile {_pw['min_z']:.1f}..{_pw['top_z']:.1f})")

        if self.last_retract_motion_warnings:
            _rm = self.last_retract_motion_warnings[0]
            logger.warning(
                f"[RETRACT] {len(self.last_retract_motion_warnings)} op(s) retract "
                f"Z-first, dragging the roller along the part before it lifts; "
                f"first: op #{_rm['op_index'] + 1} dz={_rm['dz']:+.1f}mm")

        if self.last_tool_change_warnings:
            _tc = self.last_tool_change_warnings[0]
            logger.warning(
                f"[TOOLCHG] {len(self.last_tool_change_warnings)} custom tool-change "
                f"point(s) with a collision risk; first: op #{_tc['op_index'] + 1} "
                f"'{_tc['mode']}' X={_tc['x']:.1f} Z={_tc['z']:.1f} "
                f"dest_gap={_tc['gap']:+.1f}mm path_gap={_tc.get('path_gap', _tc['gap']):+.1f}mm")

        self.last_calculated_paths = toolpaths
        self.last_calculated_sequence = sequence
        self.last_mandrel_mgr = mandrel_mgr
        return toolpaths, projections, control_points, deviations, rapids, debug_lines

    def _compute_tilt_for_path(self, pts, op, mandrel_mgr, kin):
        """CANONICAL tilt source — per-point tilt (deg) for any point array.

        Works on the full stored path AND on a PLC-decimated subset, so the 3D
        view, the simulation and the emitted G-code always agree:
          - "normal" mode derives tilt from the surface normal at each point's
            Z (clamped into the mandrel range, same principle as
            _correct_clearance_uniform) plus the op's lead/lag tilt_offset;
          - "interp" mode ties the angle to SURFACE POSITION: tilt_start at
            the op's start_z, tilt_end at its end_z, linear in the point's Z
            in between (clamped to the zone). The angle is a property of where
            on the surface the roller is, not of pass progress — so every pass
            of a multi-pass op, and back passes running in reverse, all agree.
        All values are clamped to the machine's B travel via kin.clamp_tilt.
        """
        pts = np.asarray(pts, dtype=float)
        n = len(pts)
        if n == 0:
            return np.zeros(0)
        op = op or {}
        mode = op.get("tilt_mode", "normal")

        if mode == "interp":
            t0 = float(op.get("tilt_start", 0.0))
            t1 = float(op.get("tilt_end", 0.0))
            z0 = float(op.get("start_z", mandrel_mgr.props.get("min_z", 0.0)))
            z1 = float(op.get("end_z",   mandrel_mgr.props.get("top_z", 0.0)))
            span = z1 - z0
            if abs(span) < 1e-9:
                raw = np.full(n, t0)
            else:
                frac = np.clip((pts[:, 2] - z0) / span, 0.0, 1.0)
                raw = t0 + frac * (t1 - t0)
        else:  # "normal"
            off = float(op.get("tilt_offset", 0.0))
            m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
            m_top_z = mandrel_mgr.props.get("top_z", float('inf'))
            raw = np.empty(n)
            for i in range(n):
                zc = min(max(pts[i][2], m_min_z), m_top_z)
                nx, nz = mandrel_mgr.get_normal_at_z(zc)
                # Canonical outward normal (positive-X frame): a cylinder wall
                # (nx=1, nz=0) gives tilt 0 = radial, exactly like machine #1.
                raw[i] = math.degrees(math.atan2(nz, nx)) + off

        return np.array([kin.clamp_tilt(v) for v in raw])

    def _create_adaptive_pass(self, start_z, end_z, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, pass_name, t_list, p_list, c_list, d_list, params, additional_radial_offset=0.0):
        """
        Generates a dense G-Code path by offsetting the Mandrel Profile at fine intervals.
        Designed for complex geometries with sharp radius changes.
        """
        resolution = float(params.get("finish_trace_resolution", 0.5))
        if resolution < 0.1: resolution = 0.1
        
        # Determine Z range and steps
        z_min = min(start_z, end_z)
        z_max = max(start_z, end_z)
        steps = int((z_max - z_min) / resolution) + 2
        
        # Decide direction
        forward = (start_z < end_z)
        z_vals = np.linspace(start_z, end_z, steps) if forward else np.linspace(start_z, end_z, steps)
        
        path_points = []
        cached_radii = []

        # Safety Offset Calculation
        total_offset = r_tool + blank_thick + additional_radial_offset

        bow_height = float(params.get("adaptive_bow_height", 0.0))

        z_min = np.min(z_vals)
        z_max = np.max(z_vals)
        z_len = z_max - z_min
        if z_len < 0.001: z_len = 1.0

        for z in z_vals:
            m_rad = mandrel_mgr.get_radius_fast(z)
            cached_radii.append(m_rad)
            nx, nz = mandrel_mgr.get_normal_at_z(z)

            t = (z - z_min) / z_len
            parabolic_offset = bow_height * 4 * t * (1.0 - t)

            r_contact = m_rad + shell_offset + parabolic_offset

            p_roller_x = (center_x + r_contact) + (nx * total_offset)
            p_roller_z = z + (nz * total_offset)

            path_points.append([p_roller_x, 0, p_roller_z])

        # Store Result
        pts_arr = np.array(path_points)
        t_list.append(pts_arr)
        
        # Consistent Visualization Data
        # Projections: Trace contacting surface (r_contact)
        proj_pts = []
        for z, m_rad in zip(z_vals, cached_radii):
            px = center_x + m_rad + shell_offset + blank_thick
            proj_pts.append([px, 0, z])
            
        p_list.append(np.array(proj_pts))        
        c_list.append(np.array([])) # Control Pts (None)
        
        # Deviations must match point count for scalars
        if len(pts_arr) > 0:
            # Use surface_z (not roller Z) for mandrel radius lookup.
            # On curved surfaces (sphere, etc.) the roller is pushed in Z by the normal component,
            # so pt[2] (roller Z) differs from the surface contact Z — using it gives wrong clearance.
            devs = []
            for pt, m_r in zip(pts_arr, cached_radii):
                dist = math.sqrt((pt[0]-center_x)**2 + pt[1]**2)
                limit = m_r + blank_thick + shell_offset + r_tool
                devs.append(dist - limit)
            d_list.append(np.array(devs))
        else:
            d_list.append(np.array([]))
            logger.warning(f"Adaptive Pass '{pass_name}' generated 0 points! Range: {start_z:.2f} to {end_z:.2f}")

        logger.info(f"Generated Adaptive Pass '{pass_name}': {len(pts_arr)} points.") 

    def _arc_fillet_at_p2(self, p2_arr, d1, d2, radius, leg1, leg2, check_res):
        """True tangent-circle fillet at vertex p2_arr between two rays d1, d2
        (unit vectors pointing away from the vertex along each leg).

        Returns (T1, T2, arc_pts): T1/T2 are the tangent points on leg1/leg2
        where the arc begins/ends, arc_pts is the polyline from T1 to T2
        (inclusive) approximating the arc. If radius <= 0 or the legs are
        (nearly) collinear (no real corner), T1 == T2 == p2_arr and arc_pts
        is empty — callers should treat that as "no fillet".
        """
        d1 = d1 / max(np.linalg.norm(d1), 1e-9)
        d2 = d2 / max(np.linalg.norm(d2), 1e-9)
        cos_a = float(np.clip(np.dot(d1, d2), -1.0, 1.0))
        angle = math.acos(cos_a)
        if radius <= 0.01 or angle < 1e-3 or angle > math.pi - 1e-3:
            return p2_arr.copy(), p2_arr.copy(), np.empty((0, 3))

        tangent_len = radius / math.tan(angle / 2.0)
        max_len = max(0.0, min(leg1, leg2) * 0.9)
        tangent_len = min(tangent_len, max_len)
        eff_radius = tangent_len * math.tan(angle / 2.0)
        if tangent_len < 1e-6 or eff_radius < 0.01:
            return p2_arr.copy(), p2_arr.copy(), np.empty((0, 3))

        T1 = p2_arr + tangent_len * d1
        T2 = p2_arr + tangent_len * d2
        b = d1 + d2
        b_norm = np.linalg.norm(b)
        if b_norm < 1e-9:
            return p2_arr.copy(), p2_arr.copy(), np.empty((0, 3))
        b = b / b_norm
        center_dist = eff_radius / math.sin(angle / 2.0)
        O = p2_arr + center_dist * b

        u1 = (T1 - O) / eff_radius
        u2 = (T2 - O) / eff_radius
        th1 = math.atan2(u1[2], u1[0])
        th2 = math.atan2(u2[2], u2[0])
        sweep = th2 - th1
        if sweep > math.pi:
            sweep -= 2 * math.pi
        elif sweep < -math.pi:
            sweep += 2 * math.pi

        n_arc = max(4, int(eff_radius * abs(sweep) / check_res))
        t_vals = np.linspace(0.0, 1.0, n_arc)
        thetas = th1 + t_vals * sweep
        arc_pts = np.stack([
            O[0] + eff_radius * np.cos(thetas),
            np.zeros_like(thetas),
            O[2] + eff_radius * np.sin(thetas)
        ], axis=1)
        return T1, T2, arc_pts

    def _enforce_min_clearance(self, points, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, target_clearance):
        """Per-point safety net: pushes any point that violates the minimum
        roller/mandrel clearance outward along the local surface normal, just
        enough to satisfy target_clearance. Points already clear, and points
        outside the mandrel's Z range, are returned unchanged.
        """
        m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
        m_top_z = mandrel_mgr.props.get("top_z", float('inf'))
        corrected = []
        for pt in points:
            sim_x, sim_y, sim_z = pt
            if sim_z < m_min_z or sim_z > m_top_z:
                corrected.append([sim_x, sim_y, sim_z])
                continue
            m_rad = max(0.0, mandrel_mgr.get_radius_fast(sim_z))
            dist = math.sqrt((sim_x - center_x) ** 2 + sim_y ** 2)
            required = m_rad + blank_thick + shell_offset + r_tool + target_clearance
            if dist < required:
                deficit = required - dist
                pnx, pnz = mandrel_mgr.get_normal_at_z(sim_z)
                corrected.append([sim_x + deficit * pnx, sim_y, sim_z + deficit * pnz])
            else:
                corrected.append([sim_x, sim_y, sim_z])
        return np.array(corrected)

    def _correct_clearance_uniform(self, points, mandrel_mgr, center_x, r_tool,
                                   blank_thick, shell_offset, target_clearance,
                                   max_iter=8):
        """Enforces target_clearance over an entire pre-built polyline (e.g. a
        back pass) using the SAME uniform-radial-shift principle that the
        forward spline pass uses in _create_and_store_pass: find the worst
        clearance over the whole stroke, then translate every point rigidly
        outward by that deficit. The bow/shape produced by back_pass_arc_x/z
        is preserved exactly — only its radial position is corrected — just as
        the forward correction preserves the spline shape and only shifts it.

        Two things this fixes versus the old per-point _clamp_radial_clearance:

        1. No Z-range blind spot. The old clamp (and the forward min-clearance
           scan) SKIP every point whose Z is outside [min_z, top_z]. A back
           pass arc routinely extends past the mandrel top (P3 = contact_z +
           p3_z_offset, and on high passes contact_z is already near top_z), so
           those points were never checked — with an inward back_pass_arc_x or
           a flaring/convex profile they dived straight into the mandrel near
           the top edge while the safety net did nothing. Here the radius
           lookup Z is CLAMPED into the mandrel range instead of skipped, so
           the region just past an edge is treated as the edge radius and can
           never be dived into.

        2. Segment-aware. Clearance is sampled along each segment, not just at
           the stored vertices, so a straight G1 chord between two safe points
           can't cut through a convex surface unnoticed.

        Only outward corrections are applied (deficit > 0); an already-clear
        path is never pulled inward, so a deliberate outward bow is kept.
        """
        pts = np.array(points, dtype=float)
        if len(pts) < 2:
            return pts

        m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
        m_top_z = mandrel_mgr.props.get("top_z", float('inf'))

        # Outward direction along X. Canonical generation keeps every path point
        # on one side of the spindle axis, so a single sign is correct.
        side = 1.0 if (float(np.mean(pts[:, 0])) - center_x) >= 0 else -1.0

        check_res = 0.5
        for _ in range(max_iter):
            min_clear = float('inf')
            for a, b in zip(pts[:-1], pts[1:]):
                seg_len = float(np.linalg.norm(b - a))
                n = max(2, int(seg_len / check_res) + 1)
                for t in np.linspace(0.0, 1.0, n):
                    sx, sy, sz = a + t * (b - a)
                    zc = min(max(sz, m_min_z), m_top_z)          # clamp, don't skip
                    m_rad = max(0.0, mandrel_mgr.get_radius_fast(zc))
                    dist = math.sqrt((sx - center_x) ** 2 + sy ** 2)
                    clear = dist - (m_rad + blank_thick + shell_offset + r_tool)
                    if clear < min_clear:
                        min_clear = clear

            if min_clear == float('inf'):
                break                                            # nothing to check
            diff = target_clearance - min_clear
            if diff <= 0.01:
                break                                            # safe (never pull in)
            pts[:, 0] += side * diff
        return pts

    def _tangent_chord_arc(self, A, B, arc_ang_deg, check_res):
        """Dense point run A→B in the XZ plane: straight line when arc_ang_deg≈0,
        else a circular arc with the given tangent-chord angle (°). Positive =
        bow outward (away from the spin axis, larger X), negative = inward.
        The tangent-chord angle of a circular arc is identical at both ends, so
        the same call serves either traversal direction. Shared by the exit leg
        and — for reverse passes (#82) — the outgoing arm leg."""
        A = np.asarray(A, dtype=float)
        B = np.asarray(B, dtype=float)
        seg_len = max(np.linalg.norm(B - A), 0.1)
        try:
            _ang = float(arc_ang_deg)
        except (TypeError, ValueError):
            _ang = 0.0
        ang_rad = math.radians(abs(_ang))
        if ang_rad < 1e-4:
            return np.linspace(A, B, max(10, int(seg_len / check_res)))
        chord_dir = (B - A) / seg_len
        perp_xz = np.array([-chord_dir[2], 0.0, chord_dir[0]])
        if perp_xz[0] < 0:
            perp_xz = -perp_xz
        _sign = 1.0 if _ang > 0 else -1.0
        R = seg_len / (2.0 * math.sin(ang_rad))
        arc_len = R * 2.0 * ang_rad
        center = 0.5 * (A + B) - _sign * R * math.cos(ang_rad) * perp_xz
        u1 = (A - center) / R
        th1 = math.atan2(u1[2], u1[0])
        sweep = _sign * 2.0 * ang_rad
        n = max(10, int(arc_len / check_res))
        t_vals = np.linspace(0.0, 1.0, n)
        thetas = th1 + t_vals * sweep
        return np.stack([center[0] + R * np.cos(thetas),
                         np.zeros(n),
                         center[2] + R * np.sin(thetas)], axis=1)

    def _bezier_bow(self, A, B, bow_mm, check_res, bias=0.5):
        """Dense point run A→B in the XZ plane that bows sideways by `bow_mm`,
        using a quadratic Bézier. Unlike _tangent_chord_arc, this is
        parameterized by BOW HEIGHT (mm), not by a tangent-chord angle, so it is
        stable in exactly the regime that breaks the arc:

          • Endpoints A and B are reproduced EXACTLY (t=0 → A, t=1 → B), so a
            pinned P3 (reach-follow / progressive-angle) never moves.
          • The visible bow height is `bow_mm` and grows monotonically — the
            curve can never sweep past a semicircle and fold back on itself the
            way a tangent-chord arc does once its angle exceeds ~90° (that fold
            is the "funny movement" on steep last passes). Ideal for the (b)
            case where P2 and P3 sit at nearly the same Z and the exit must bow
            out and come back without looping.

        `bias` (0.05–0.95, default 0.5) slides the single control point ALONG
        the chord, which moves where the fullest part of the bow sits: <0.5 pulls
        it toward A (hug then peel), >0.5 toward B (lift late). Because A and B
        carry no perpendicular component, the peak perpendicular deviation stays
        exactly `bow_mm` regardless of bias — only its spatial position shifts.

        Bow SIDE uses a FIXED handedness: perp = (−chord_z, +chord_x), i.e. the
        chord rotated +90° in XZ, with the sign carried by bow_mm. This is the
        key to a consistent bow across a progressive-angle fan: the exit chord
        sweeps through the radial direction as the fan opens (pass_angle < 90°
        → below radial, > 90° → above), and ANY "keep it on the +X / away-from-
        part side" rule flips the perpendicular's Z-sign exactly at that radial
        crossing — which is why the first pass used to bow the opposite way to
        the rest. A fixed handedness rotates smoothly with the chord and never
        flips, so every pass in a fan bows the same way; +bow leans toward the
        mandrel top (+Z), −bow toward the base. Staying clear of the part is
        handled separately (see _make_bow_leg), not by the side choice."""
        A = np.asarray(A, dtype=float)
        B = np.asarray(B, dtype=float)
        seg_len = max(np.linalg.norm(B - A), 0.1)
        try:
            _bow = float(bow_mm)
        except (TypeError, ValueError):
            _bow = 0.0
        if abs(_bow) < 1e-4:
            return np.linspace(A, B, max(10, int(seg_len / check_res)))
        try:
            _bias = min(max(float(bias), 0.05), 0.95)
        except (TypeError, ValueError):
            _bias = 0.5
        chord_dir = (B - A) / seg_len
        perp_xz = np.array([-chord_dir[2], 0.0, chord_dir[0]])   # fixed +90° handedness
        # Quadratic Bézier: the curve reaches half the control-point offset at
        # t=0.5, so lift the control point by 2·bow to make the peak == bow_mm.
        # The along-chord position of the control point (_bias) shifts where that
        # peak lands without changing its height.
        ctrl = A + _bias * (B - A) + (2.0 * _bow) * perp_xz
        n = max(10, int(seg_len / check_res))
        t = np.linspace(0.0, 1.0, n).reshape(-1, 1)
        return (1 - t) ** 2 * A + 2 * (1 - t) * t * ctrl + t ** 2 * B

    def _bow_penetration(self, pts, mandrel_mgr, center_x, r_tool,
                         blank_thick, shell_offset, clearance):
        """Worst interior clearance violation (mm, >=0) of a bow leg against the
        clearance-offset surface at `clearance`. Radial test (all path points
        have y=0, so distance-to-axis = |x - center_x|); the surface radius Z is
        CLAMPED into the mandrel range (not skipped) so a bow poking past the
        top edge is still caught. Endpoints are excluded — they are pinned."""
        pts = np.asarray(pts, dtype=float)
        if len(pts) < 3:
            return 0.0
        m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
        m_top_z = mandrel_mgr.props.get("top_z", float('inf'))
        worst = 0.0
        for i in range(1, len(pts) - 1):
            sx, sz = pts[i, 0], pts[i, 2]
            zc = min(max(sz, m_min_z), m_top_z)
            m_rad = max(0.0, mandrel_mgr.get_radius_fast(zc))
            required = m_rad + blank_thick + shell_offset + r_tool + clearance
            pen = required - abs(sx - center_x)
            if pen > worst:
                worst = pen
        return worst

    def _make_bow_leg(self, A, B, bow_mm, check_res, mandrel_mgr,
                      center_x, r_tool, blank_thick, shell_offset,
                      clearance, do_trim, pass_name="", bias=0.5):
        """Build a bow leg A→B (via _bezier_bow) and keep it clear of the part:

          • do_trim=True  → TRIM: build the FULL requested bow, then push any
            interior point that crosses the `clearance` surface radially back
            out to exactly that surface. The bow keeps its full shape wherever
            it fits and rides the clearance contour only across the infeasible
            stretch. Endpoints stay pinned. (User 2026-07-08: preferred, because
            on a short steep last pass a big bow survives instead of collapsing.)
          • do_trim=False → CLAMP: shrink the bow AMPLITUDE until no interior
            point violates — a smaller but perfectly smooth bow (no kink).

        Either way the leg never comes closer to the part than `clearance`, so
        the shared uniform-shift correction downstream never fires for the bow
        and P3 / the approach arm are left exactly where reach & angle put them."""
        m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
        m_top_z = mandrel_mgr.props.get("top_z", float('inf'))
        if do_trim:
            curve = self._bezier_bow(A, B, bow_mm, check_res, bias=bias)
            side = 1.0 if (float(np.mean(curve[:, 0])) - center_x) >= 0 else -1.0
            moved = 0
            for i in range(1, len(curve) - 1):     # keep endpoints pinned
                sx, sz = curve[i, 0], curve[i, 2]
                zc = min(max(sz, m_min_z), m_top_z)
                m_rad = max(0.0, mandrel_mgr.get_radius_fast(zc))
                required = m_rad + blank_thick + shell_offset + r_tool + clearance
                if abs(sx - center_x) < required - 1e-6:
                    curve[i, 0] = center_x + side * required   # ride the contour
                    moved += 1
            if moved:
                logger.info(
                    f"[PARAM_DEBUG] '{pass_name}' exit_bow TRIMMED: {moved} pt(s) "
                    f"rode the clearance contour ({clearance:.2f}mm)")
            return curve
        # CLAMP: geometric shrink of the amplitude until it fits.
        amp = float(bow_mm)
        curve = self._bezier_bow(A, B, amp, check_res, bias=bias)
        for _ in range(14):
            pen = self._bow_penetration(curve, mandrel_mgr, center_x, r_tool,
                                        blank_thick, shell_offset, clearance)
            if pen <= 0.05 or abs(amp) < 0.05:
                break
            amp *= 0.85
            curve = self._bezier_bow(A, B, amp, check_res, bias=bias)
        if abs(amp - float(bow_mm)) > 0.05:
            logger.info(
                f"[PARAM_DEBUG] '{pass_name}' exit_bow CLAMPED "
                f"{float(bow_mm):+.1f} → {amp:+.1f}mm (clearance {clearance:.2f}mm)")
        return curve

    # Fold guard for the exit curl: the tangent arc may never sweep past this.
    # Same failure mode exit_arc_angle has above ~90° (it folds back on itself);
    # here the LENGTH is the invariant (see _make_curl_leg), so the cap grows the
    # radius instead of shortening the pass.
    CURL_SWEEP_CAP_DEG = 90.0

    def _curl_penetration(self, pts, mandrel_mgr, center_x, r_tool,
                          blank_thick, shell_offset, clearance, skip_first=True):
        """Worst clearance violation (mm, >=0) of a curl leg against the
        clearance-offset surface. Same radial test as `_bow_penetration`, but the
        LAST point is included: unlike a bow, the curl's end is a free output
        (the pass no longer has to land on the planned P3), so it must be checked
        too. `skip_first` keeps M — the junction with the straight leg — pinned."""
        pts = np.asarray(pts, dtype=float)
        if len(pts) < 2:
            return 0.0
        m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
        m_top_z = mandrel_mgr.props.get("top_z", float('inf'))
        worst = 0.0
        for i in range(1 if skip_first else 0, len(pts)):
            sx, sz = pts[i, 0], pts[i, 2]
            zc = min(max(sz, m_min_z), m_top_z)
            m_rad = max(0.0, mandrel_mgr.get_radius_fast(zc))
            required = m_rad + blank_thick + shell_offset + r_tool + clearance
            pen = required - abs(sx - center_x)
            if pen > worst:
                worst = pen
        return worst

    def _tangent_arc(self, M, tan_dir, radius_mm, arc_len, check_res):
        """Dense point run starting at M, leaving along `tan_dir`, curving at
        EXACTLY radius |radius_mm| for up to `arc_len` mm of arc. The start point
        and start TANGENT are exact, so a straight leg feeding into this has no
        corner at the junction.

        Returns (points, sweep_rad, leftover_len, end_dir). The turn is capped at
        CURL_SWEEP_CAP_DEG; when the cap bites, the arc simply stops there and
        `leftover_len` is the length that did not fit — the caller runs it on as a
        straight tangent (see `_curl_tail`). The RADIUS IS NEVER ALTERED to make
        the length fit: doing that made every radius below arc_len·2/π collapse to
        one identical shape, so only the sign of the field had any effect
        (user-reported 2026-07-26).

        SIGN / HANDEDNESS — deliberately identical to `_bezier_bow`: the normal is
        the chord rotated a fixed +90° in XZ, `perp = (−dir_z, 0, +dir_x)`, with the
        side carried by the sign of `radius_mm`. It is tempting to instead pick
        "whichever perpendicular points away from the axis (+X)", but that rule
        flips its Z-sign exactly where the exit direction sweeps through radial —
        which is the bug that made the first pass of a progressive-angle fan bow
        opposite to the rest (see `_bezier_bow`). A fixed handedness rotates
        smoothly with the direction and never flips, so every pass in a fan curls
        the same way: **+R curls toward the mandrel top (+Z), −R toward the base.**

        Total tail length is still preserved — see `_curl_tail`."""
        M = np.asarray(M, dtype=float)
        d = np.asarray(tan_dir, dtype=float)
        d_norm = np.linalg.norm(d)
        R = abs(float(radius_mm))
        if d_norm < 1e-9 or arc_len <= 1e-6 or R < 1e-6:
            return np.array([M]), 0.0, max(arc_len, 0.0), (d / d_norm if d_norm > 1e-9
                                                           else np.array([0.0, 0.0, 1.0]))
        d   = d / d_norm
        sgn = 1.0 if float(radius_mm) >= 0 else -1.0
        cap = math.radians(self.CURL_SWEEP_CAP_DEG)
        sweep = min(arc_len / R, cap)                  # radius exact; turn capped
        used  = R * sweep
        perp   = np.array([-d[2], 0.0, d[0]])          # fixed +90° handedness
        center = M + sgn * R * perp
        u0     = M - center
        n      = max(10, int(used / max(check_res, 1e-3)))
        phi    = np.linspace(0.0, sgn * sweep, n)
        cos_p, sin_p = np.cos(phi), np.sin(phi)
        pts = np.stack([
            center[0] + u0[0] * cos_p - u0[2] * sin_p,
            np.zeros(n),
            center[2] + u0[0] * sin_p + u0[2] * cos_p,
        ], axis=1)
        # Unit tangent where the arc ends = the start direction turned by the sweep.
        c_e, s_e = math.cos(sgn * sweep), math.sin(sgn * sweep)
        end_dir = np.array([d[0] * c_e - d[2] * s_e, 0.0, d[0] * s_e + d[2] * c_e])
        return pts, sweep, max(arc_len - used, 0.0), end_dir

    def _spiral_tail(self, M, tan_dir, k0, k1, sgn, total_len, check_res):
        """Variable-curvature tail: curvature runs LINEARLY in arc length from k0
        at M to k1 at the end (a clothoid — the transition curve used for road and
        rail easements). Turn is capped at CURL_SWEEP_CAP_DEG exactly as the plain
        arc is; leftover length runs on straight and tangent.

        Why this exists (#92 mid phase): a constant-radius arc has a CURVATURE
        JUMP where it meets the straight leg — heading is continuous (no corner)
        but curvature snaps from 0 to 1/R. The tool slams into the bend and the
        material takes it at one spot. Starting near-straight and tightening
        toward the blank edge spreads that bend into the wall.

        Returns (points, turn_rad, leftover_len, end_dir)."""
        M = np.asarray(M, dtype=float)
        d = np.asarray(tan_dir, dtype=float)
        d = d / max(np.linalg.norm(d), 1e-12)
        cap = math.radians(self.CURL_SWEEP_CAP_DEG)

        n  = max(40, int(total_len / max(check_res, 1e-3)))
        s  = np.linspace(0.0, total_len, n)
        ds = float(s[1] - s[0])
        kap = k0 + (k1 - k0) * (s / total_len)
        # Heading = running integral of curvature (trapezoid).
        turn = np.concatenate([[0.0], np.cumsum(0.5 * (kap[:-1] + kap[1:])) * ds])

        # Fold guard: stop where the accumulated turn reaches the cap.
        over = np.nonzero(turn > cap)[0]
        if len(over):
            cut  = max(int(over[0]), 1)
            s, turn = s[:cut + 1], turn[:cut + 1]
        leftover = total_len - float(s[-1])

        phi = sgn * turn
        dx  = d[0] * np.cos(phi) - d[2] * np.sin(phi)
        dz  = d[0] * np.sin(phi) + d[2] * np.cos(phi)
        px  = M[0] + np.concatenate([[0.0], np.cumsum(0.5 * (dx[:-1] + dx[1:])) * ds])
        pz  = M[2] + np.concatenate([[0.0], np.cumsum(0.5 * (dz[:-1] + dz[1:])) * ds])
        pts = np.stack([px, np.zeros(len(px)), pz], axis=1)
        end_dir = np.array([float(dx[-1]), 0.0, float(dz[-1])])
        return pts, float(turn[-1]), max(leftover, 0.0), end_dir

    def _curl_tail(self, M, tan_dir, radius_mm, total_len, check_res,
                   radius_end_mm=None):
        """The whole post-M tail: a constant-radius arc of EXACTLY |radius_mm|,
        turning at most CURL_SWEEP_CAP_DEG, followed by a straight tangent run
        spending whatever length is left.

        This keeps BOTH promises at once — the radius the operator typed is the
        radius they get (a tight R makes a tight hook), and the tail still runs
        the full leftover |M→P3| length, so reach keeps deciding how far the pass
        goes. Large radii never reach the cap, so their shape is a pure arc,
        exactly as before.

        `radius_end_mm` (optional) makes the curvature VARY along the tail — see
        `_spiral_tail`. Empty/None/equal ⇒ the analytic constant-radius arc above
        is used unchanged, so leaving the field alone is byte-identical.

        DIRECTION comes from whichever radius is set first (start, else end); the
        end radius contributes its MAGNITUDE only, so mixed signs can never fold
        the tail into an S mid-curve. If only the end radius is given, the tail
        leaves M perfectly straight (curvature 0) and eases into that radius.

        Returns (points, sweep_rad, straight_len)."""
        _r0 = abs(float(radius_mm)) if radius_mm not in (None, "") else 0.0
        try:
            _r1 = abs(float(radius_end_mm)) if radius_end_mm not in (None, "") else None
        except (TypeError, ValueError):
            _r1 = None
        k0 = 1.0 / _r0 if _r0 > 1e-6 else 0.0
        k1 = k0 if (_r1 is None) else (1.0 / _r1 if _r1 > 1e-6 else 0.0)

        if abs(k1 - k0) > 1e-9:
            sgn = 1.0 if (float(radius_mm or 0) or float(radius_end_mm or 0)) >= 0 else -1.0
            arc, sweep, leftover, end_dir = self._spiral_tail(
                M, tan_dir, k0, k1, sgn, total_len, check_res)
            if leftover <= 1e-6 or len(arc) < 2:
                return arc, sweep, 0.0
            tail_end = arc[-1] + leftover * (end_dir / max(np.linalg.norm(end_dir), 1e-12))
            n_run    = max(2, int(leftover / max(check_res, 1e-3)))
            run      = np.linspace(arc[-1], tail_end, n_run)
            return np.vstack([arc, run[1:]]), sweep, leftover

        arc, sweep, leftover, end_dir = self._tangent_arc(
            M, tan_dir, radius_mm, total_len, check_res)
        if leftover <= 1e-6 or len(arc) < 2:
            return arc, sweep, 0.0
        tail_end = arc[-1] + leftover * end_dir
        n_run    = max(2, int(leftover / max(check_res, 1e-3)))
        run      = np.linspace(arc[-1], tail_end, n_run)
        return np.vstack([arc, run[1:]]), sweep, leftover

    def _make_curl_leg(self, A, B, t_frac, radius_mm, check_res, mandrel_mgr,
                       center_x, r_tool, blank_thick, shell_offset,
                       clearance, do_trim, pass_name="", radius_end_mm=None):
        """Exit leg A→(curl): DEAD STRAIGHT from A to M, then a constant-radius arc
        tangent at M. `t_frac` places M along the straight A→B CHORD (not along the
        point array — see PROPOSAL_exit_mid_spline.md Q3), and the arc runs the
        length that is left over, |M→B|, so reach still decides how far the pass
        goes while the radius decides only how hard it curls.

        The end point is a free output: once the tail curls away from the blank
        edge there is nothing left for follow-blank to follow, so B is a length
        budget rather than a target.

        Clearance is handled exactly like `exit_bow_trim`:
          • do_trim=True  → TRIM: full arc, then any point crossing the `clearance`
            surface is pushed radially back out to it and rides the contour.
          • do_trim=False → FLATTEN: an arc has no amplitude to shrink, so its
            equivalent is curvature — the radius is GROWN until nothing violates,
            giving a gentler but perfectly smooth curl.
        M stays pinned in both modes, so the straight leg never moves."""
        A = np.asarray(A, dtype=float)
        B = np.asarray(B, dtype=float)
        chord = B - A
        L = float(np.linalg.norm(chord))
        try:
            _t = min(max(float(t_frac), 0.05), 0.95)
        except (TypeError, ValueError):
            _t = 0.5
        if L < 1e-6:
            return np.linspace(A, B, 2)
        d       = chord / L
        M       = A + _t * chord
        arc_len = (1.0 - _t) * L

        n_str    = max(2, int((_t * L) / max(check_res, 1e-3)))
        straight = np.linspace(A, M, n_str)

        R_eff = abs(float(radius_mm or 0.0))
        arc, sweep, run_len = self._curl_tail(M, d, radius_mm, arc_len, check_res,
                                              radius_end_mm=radius_end_mm)
        if run_len > 0.05:
            logger.info(
                f"[PARAM_DEBUG] '{pass_name}' exit curl turn-capped at "
                f"{self.CURL_SWEEP_CAP_DEG:.0f}°: R{R_eff:.1f}mm arc "
                f"{arc_len - run_len:.1f}mm + straight run-out {run_len:.1f}mm "
                f"(radius kept exact, total length {arc_len:.1f}mm kept)")

        if do_trim:
            m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
            m_top_z = mandrel_mgr.props.get("top_z", float('inf'))
            side  = 1.0 if (float(np.mean(arc[:, 0])) - center_x) >= 0 else -1.0
            moved = 0
            for i in range(1, len(arc)):          # M pinned; the free end IS checked
                sx, sz = arc[i, 0], arc[i, 2]
                zc = min(max(sz, m_min_z), m_top_z)
                m_rad = max(0.0, mandrel_mgr.get_radius_fast(zc))
                required = m_rad + blank_thick + shell_offset + r_tool + clearance
                if abs(sx - center_x) < required - 1e-6:
                    arc[i, 0] = center_x + side * required     # ride the contour
                    moved += 1
            if moved:
                logger.info(
                    f"[PARAM_DEBUG] '{pass_name}' exit curl TRIMMED: {moved} pt(s) "
                    f"rode the clearance contour ({clearance:.2f}mm)")
        else:
            # FLATTEN: grow the radius (the curl's analogue of the bow's ×0.85
            # amplitude shrink) until nothing violates. Length is preserved, so
            # this degenerates toward a straight leg in the worst case.
            R_try = R_eff
            for _ in range(24):
                pen = self._curl_penetration(arc, mandrel_mgr, center_x, r_tool,
                                             blank_thick, shell_offset, clearance)
                if pen <= 0.05 or sweep < math.radians(0.5):
                    break
                R_try *= 1.5
                # Scale BOTH radii together so the spiral keeps its shape while
                # every part of it gets gentler.
                _re_try = (None if radius_end_mm in (None, "")
                           else math.copysign(abs(float(radius_end_mm)) * (R_try / max(R_eff, 1e-9)),
                                              float(radius_end_mm)))
                arc, sweep, run_len = self._curl_tail(
                    M, d, math.copysign(R_try, float(radius_mm or 1.0)), arc_len,
                    check_res, radius_end_mm=_re_try)
            if R_try - R_eff > 0.05:
                logger.info(
                    f"[PARAM_DEBUG] '{pass_name}' exit curl FLATTENED: R "
                    f"{R_eff:.1f} → {R_try:.1f}mm (clearance {clearance:.2f}mm)")
            R_eff = R_try
            # BACKSTOP (deliberately stronger than exit_bow's CLAMP): flattening can
            # only undo the violation the CURL causes. If the leg's own direction
            # already runs inside the clearance surface, a perfectly straight curl
            # still violates — and `exit_bow_trim=False` would hand that gouge
            # downstream. Push whatever is left out to the contour so the clearance
            # contract holds in BOTH modes; only these leftover points get a kink.
            pen = self._curl_penetration(arc, mandrel_mgr, center_x, r_tool,
                                         blank_thick, shell_offset, clearance)
            if pen > 0.05:
                m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
                m_top_z = mandrel_mgr.props.get("top_z", float('inf'))
                side  = 1.0 if (float(np.mean(arc[:, 0])) - center_x) >= 0 else -1.0
                moved = 0
                for i in range(1, len(arc)):
                    sx, sz = arc[i, 0], arc[i, 2]
                    zc = min(max(sz, m_min_z), m_top_z)
                    m_rad = max(0.0, mandrel_mgr.get_radius_fast(zc))
                    required = m_rad + blank_thick + shell_offset + r_tool + clearance
                    if abs(sx - center_x) < required - 1e-6:
                        arc[i, 0] = center_x + side * required
                        moved += 1
                logger.info(
                    f"[PARAM_DEBUG] '{pass_name}' exit curl FLATTEN backstop: "
                    f"{moved} pt(s) trimmed to the contour — the leg direction "
                    f"itself runs inside the {clearance:.2f}mm clearance surface")

        _r_txt = (f"R{math.copysign(R_eff, float(radius_mm or 1.0)):+.1f}mm"
                  if radius_end_mm in (None, "") else
                  f"R{R_eff:.1f}→{abs(float(radius_end_mm)):.1f}mm (spiral)")
        logger.info(
            f"[PARAM_DEBUG] '{pass_name}' exit curl: straight {(_t * L):.1f}mm "
            f"(t={_t:.2f}) + tail {arc_len:.1f}mm @ {_r_txt} "
            f"turn={math.degrees(sweep):.1f}°"
            + (f" + run-out {run_len:.1f}mm" if run_len > 0.05 else "")
            + f" | end=({arc[-1][0]:.2f}, Z={arc[-1][2]:.2f})")
        return np.vstack([straight[:-1], arc])

    def _create_and_store_pass(self, p1_x_offset, p1_z_offset, p3_z_offset, p3_x_offset, initial_p2, base_rot, auto_align, t_list, p_list, c_list, d_list, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, pass_name, params, debug_lines=None, op=None, op_clearance=0.0, exit_points=None, exit_shape=None, breaks=None):
            # --- Smart Spline Optimization V6 (Morphing) ---
            # Instead of rigid shifting, independently adjust control points based on where collision occurs.

            # Start edge-fillet straightening (opt-in): use the extrapolated straight-wall
            # normal for PLACEMENT (approach direction + rotation alignment) so the pass
            # follows the wall angle through the start radius instead of the fillet.
            # The clearance / gouge check below deliberately keeps sampling the REAL
            # mandrel (get_radius_fast), so this never weakens collision safety — the
            # tool is placed on the intended line but still pushed out if it would hit
            # a convex lip. No-op above the transition / on curved mandrels / flag off.
            _straighten = params.get("straighten_start_fillet", False)
            def _place_normal(z):
                return (mandrel_mgr.get_straightened_normal(z) if _straighten
                        else mandrel_mgr.get_normal_at_z(z))
            
            # 1. Initialize Absolute Control Points
            p2 = initial_p2
            # P1/P3 start based on P2, preserving offset relationship initially
            calc_p1_z = p2.Z() - abs(p1_z_offset)
            p1 = gp_Pnt(p2.X() + abs(p1_x_offset), 0, calc_p1_z)
            
            calc_p3_z = p2.Z() + p3_z_offset
            p3 = gp_Pnt(p2.X() + p3_x_offset, 0, calc_p3_z)
            _dbg_init_p2x = p2.X()
            logger.info(
                f"[PARAM_DEBUG] '{pass_name}' control pts: "
                f"P1=({p1.X():.2f}, Z={p1.Z():.2f})  "
                f"P2=({p2.X():.2f}, Z={p2.Z():.2f})  "
                f"P3=({p3.X():.2f}, Z={p3.Z():.2f})"
            )

            final_points = []
            _ap_split    = None  # index where exit portion starts in pts_raw (linear_approach/linear_full only)
            _fillet_len  = 0     # number of P2 arc-fillet points in pts_raw (0 = sharp corner)
            # #100: "straight" (default) means the waypoints ARE the emitted
            # points, so they must survive every downsampler below verbatim.
            _wp_shape = exit_waypoints.normalize_shape(exit_shape)
            _wp_verbatim = bool(exit_points) and _wp_shape != exit_waypoints.SHAPE_SPLINE
            _exit_len = 0        # vertices in exit_portion (incl. its leading T2)

            # Gouge Check Parameters
            max_iterations = 20

            # Resolution for Checking
            check_res = max(0.05, float(params.get("collision_resolution", 0.5)))
            
            for attempt in range(max_iterations):
                # 2. Generate Spline (High Rez based on Check Res)
                # Estimate length for step count
                approx_len = p1.Distance(p2) + p2.Distance(p3)
                num_points = int(max(10, approx_len / check_res))
                
                pass_shape = (op or {}).get("pass_shape", "spline")

                if pass_shape in ("linear_approach", "linear_full"):
                    # Approach: straight line of length p1_z from P2 back toward the start.
                    # P1X is ignored entirely — only P1Z controls approach length.
                    p1_z_off  = max(abs(p1_z_offset), 0.1)
                    p2_arr    = np.array([p2.X(), 0.0, p2.Z()])

                    # Approach direction (from P2 toward the approach start).
                    #   • default: pure -Z (vertical, parallel to the spindle axis).
                    #   • approach_follow_surface: along the mandrel surface tangent at P2,
                    #     so the arm runs parallel to an angled surface — constant clearance
                    #     along the whole arm instead of only at P2 (no over-clearing of P2
                    #     on tapered walls). Reduces exactly to -Z on a vertical surface.
                    if (op or {}).get("approach_follow_surface", False):
                        _anx, _anz = _place_normal(p2.Z())
                        _appr = np.array([_anz, 0.0, -_anx])      # tangent ⟂ surface normal
                        _aln  = np.linalg.norm(_appr)
                        _appr = _appr / _aln if _aln > 1e-9 else np.array([0.0, 0.0, -1.0])
                        if _appr[2] > 0.0:                        # head toward lower Z (base side)
                            _appr = -_appr
                    else:
                        _appr = np.array([0.0, 0.0, -1.0])

                    ap_start  = p2_arr + p1_z_off * _appr
                    p3_arr    = np.array([p3.X(), 0.0, p3.Z()])

                    # #100: operator-authored exit tail. When this pass carries
                    # waypoints there is NO P3 — the last waypoint ends the pass —
                    # so the fillet's second leg aims at the FIRST waypoint instead,
                    # and p3_arr is redirected to the last one so everything
                    # downstream (control points, extents) sees the real end.
                    # Empty list = every line below behaves exactly as before.
                    _wp_abs = []
                    if exit_points:
                        _wp_abs = exit_waypoints.resolve(p2_arr[0], p2_arr[2], exit_points)
                        p3_arr = np.array([_wp_abs[-1][0], 0.0, _wp_abs[-1][1]])
                        _aim = np.array([_wp_abs[0][0], 0.0, _wp_abs[0][1]])
                    else:
                        _aim = p3_arr
                    p2p3_len  = max(np.linalg.norm(_aim - p2_arr), 0.1)

                    # True tangent-circle fillet at P2 (radius in mm). d1 points back
                    # along the approach (so the fillet stays tangent to the arm even when
                    # it is tilted to the surface), d2 points toward P3 (or, with #100
                    # waypoints, toward the first waypoint).
                    d1 = _appr
                    d2 = (_aim - p2_arr) / p2p3_len
                    p2_radius = float((op or {}).get("p2_radius", 0.0))
                    T1, T2, arc_pts = self._arc_fillet_at_p2(p2_arr, d1, d2, p2_radius, p1_z_off, p2p3_len, check_res)
                    _fillet_len = len(arc_pts)

                    # Per-op exit_arc_angle (#81): the op's own value wins; the
                    # Process-tab global is the default/fallback, so programs that
                    # never set the op key are byte-identical.
                    _arc_src = (op or {}).get("exit_arc_angle", None)
                    if _arc_src in (None, ""):
                        _arc_src = params.get("exit_arc_angle", 0.0)
                    try:
                        _exit_arc_deg = float(_arc_src)
                    except (TypeError, ValueError):
                        _exit_arc_deg = 0.0

                    # Exit bow (mm) — stable alternative to exit_arc_angle for the
                    # P2→P3 curve. Set (non-zero) → the exit/arm is a bow-height
                    # Bézier that keeps P3 pinned and never folds, so it survives
                    # steep near-vertical last passes (reach-follow + progressive
                    # angle) that make exit_arc_angle loop. 0/empty → arc behavior
                    # (byte-identical default).
                    _bow_src = (op or {}).get("exit_bow", None)
                    try:
                        _exit_bow = float(_bow_src) if _bow_src not in (None, "") else 0.0
                    except (TypeError, ValueError):
                        _exit_bow = 0.0
                    # Bow side uses a fixed handedness (see _bezier_bow — no
                    # first-pass flip across the fan), and the leg is kept clear
                    # of the part at the op's own clearance — never below the
                    # hard safety floor. exit_bow_trim (default ON) rides the
                    # clearance contour where a big bow won't fit; OFF clamps the
                    # amplitude smaller instead.
                    _bow_floor = float(params.get("min_safety_gap",
                                                  params.get("target_clearance", 0.0)))
                    _bow_clear = max(float(op_clearance), _bow_floor)
                    _bow_trim  = bool((op or {}).get("exit_bow_trim", True))
                    # exit_bow_bias (0.05–0.95, default 0.5): slides the fullest
                    # part of the bow toward P2 (<0.5) or P3 (>0.5).
                    try:
                        _bow_bias = float((op or {}).get("exit_bow_bias", 0.5))
                    except (TypeError, ValueError):
                        _bow_bias = 0.5

                    # THE #82 LEG SWAP IS GONE (2026-08-30). A reverse pass is now
                    # simply the forward pass driven backwards — one rule, no mode,
                    # no flag, and every exit shape (bow, arc, curl, break points)
                    # behaves the same in both directions.
                    #
                    # What #82 did: on a reverse linear pass it forced the leg over
                    # the free blank straight and moved the curve onto the outgoing
                    # arm, so the roller entered the mandrel clean. The first half
                    # worked. The SECOND HALF NEVER DID — `:2514` collapses the arm
                    # to its two end points, so the curve was built and then deleted
                    # (measured: arm bow 0.000 mm with exit_arc_angle at 0° AND at
                    # 25°). Reverse passes have therefore always run straight in and
                    # straight out, and every exit-shape field silently did nothing
                    # on them. That is the bug this deletes, not a behaviour anyone
                    # chose.
                    #
                    # Why deleting rather than repairing the arm: bow, arc and break
                    # points are alternative ways to shape the SAME leg — the free
                    # blank. Repairing #82 would land the bow on the positioning arm
                    # while breaks stayed on the blank, which is not explicable to
                    # anyone. And #82's protection only ever bit when the operator
                    # had explicitly typed a shape: with no shape set, the forward
                    # geometry reversed already enters the mandrel dead straight,
                    # which is the default and is unchanged here.
                    #
                    # ⚠ A saved reverse op that carries exit_bow / exit_arc_angle /
                    # exit_mid_rotation now CUTS IT. It was ignored before. See
                    # TODO #82 and the `rx_f_rev_shape` audit finding, which lists
                    # exactly those operations so they can be re-checked.

                    if exit_points:
                        # #100 highest priority: the operator drew this tail by
                        # hand, so no parametric shape gets a say. Starts at T2
                        # (where the fillet ends) and runs through every waypoint
                        # to the last, which IS the end of the pass.
                        # In "straight" mode (the default) exit_portion is
                        # exactly [T2, wp1 … wpN] — no interpolation at all.
                        exit_portion = exit_waypoints.build_curve(
                            p2_arr[0], p2_arr[2], exit_points,
                            start_xz=(T2[0], T2[2]), shape=_wp_shape)
                        if len(exit_portion) < 2:
                            exit_portion = np.vstack([T2, p3_arr])
                        _ignored = [k for k in ("exit_bow", "exit_arc_angle",
                                                "exit_mid_radius")
                                    if (op or {}).get(k) not in (None, "", 0)]
                        # Breaks are reported from the resolved list rather than from
                        # op keys: it covers both a per-pass list (invisible on the op)
                        # and the legacy exit_mid_rotation it falls back to, and it
                        # cannot claim a break that is not actually there.
                        if breaks:
                            _ignored.append(f"exit_breaks({len(breaks)})")
                        if _ignored:
                            logger.info(
                                f"[#100] '{pass_name}' exit waypoints active "
                                f"({len(exit_points)} pts) → {', '.join(_ignored)} "
                                f"IGNORED on the exit leg")
                    elif pass_shape == "linear_full":
                        if abs(_exit_bow) > 1e-4:
                            exit_portion = self._make_bow_leg(
                                T2, p3_arr, _exit_bow, check_res, mandrel_mgr,
                                center_x, r_tool, blank_thick, shell_offset,
                                _bow_clear, _bow_trim, pass_name, bias=_bow_bias)
                        else:
                            n_ex         = max(2, int(np.linalg.norm(p3_arr - T2) / check_res))
                            exit_portion = np.linspace(T2, p3_arr, n_ex)
                    else:
                        # #92 EXIT CURL (exit_mid_radius, mm, signed) — highest
                        # priority exit shape. Straight T2→M (M at exit_mid_t along
                        # the CHORD), then a constant-radius arc tangent at M running
                        # the leftover |M→P3| length. The straight part is what makes
                        # the machine smooth and collapses to 2 lines under PLC RDP;
                        # the curl is the forming work near the blank edge.
                        # The end point is a free output (follow-blank has nothing
                        # left to follow once the tail leaves the edge).
                        # Empty/0 → every branch below behaves exactly as before.
                        _curl_src = (op or {}).get("exit_mid_radius", None)
                        try:
                            _curl_r = float(_curl_src) if _curl_src not in (None, "") else 0.0
                        except (TypeError, ValueError):
                            _curl_r = 0.0
                        # Mid phase: optional END radius makes the curvature vary along
                        # the tail (clothoid). Setting ONLY the end radius is valid and
                        # means "leave M straight, ease into this radius" — so either
                        # field alone switches the curl on.
                        _curl_end_src = (op or {}).get("exit_mid_radius_end", None)
                        try:
                            _curl_re = (float(_curl_end_src)
                                        if _curl_end_src not in (None, "") else 0.0)
                        except (TypeError, ValueError):
                            _curl_re = 0.0
                        _curl_end_arg = None if abs(_curl_re) <= 1e-4 else _curl_re

                        if abs(_curl_r) > 1e-4 or abs(_curl_re) > 1e-4:
                            # Curl supersedes exit_bow / exit_arc_angle on this leg —
                            # they curve the whole leg, which is exactly what the curl
                            # exists to avoid. Logged, never silent.
                            if ((op or {}).get("exit_bow") not in (None, "", 0) or
                                    (op or {}).get("exit_arc_angle") not in (None, "", 0)):
                                logger.info(
                                    f"[PARAM_DEBUG] '{pass_name}' exit curl active "
                                    f"(R={_curl_r:+.1f}mm) → exit_bow / exit_arc_angle "
                                    f"IGNORED on the exit leg")
                            exit_portion = self._make_curl_leg(
                                T2, p3_arr, (op or {}).get("exit_mid_t", 0.5),
                                _curl_r, check_res, mandrel_mgr,
                                center_x, r_tool, blank_thick, shell_offset,
                                _bow_clear, bool((op or {}).get("exit_mid_trim", True)),
                                pass_name, radius_end_mm=_curl_end_arg)
                        # Exit curve T2 → P3. exit_bow (mm) wins when set: a
                        # bow-height Bézier that keeps P3 fixed and never folds.
                        # Otherwise the tangent-chord arc — exit_arc_angle (°):
                        # positive = bow outward (larger X), negative = inward,
                        # 0 = straight line (default).
                        elif abs(_exit_bow) > 1e-4:
                            exit_portion = self._make_bow_leg(
                                T2, p3_arr, _exit_bow, check_res, mandrel_mgr,
                                center_x, r_tool, blank_thick, shell_offset,
                                _bow_clear, _bow_trim, pass_name, bias=_bow_bias)
                        else:
                            exit_portion = self._tangent_chord_arc(T2, p3_arr, _exit_arc_deg, check_res)

                        # #102 BREAK POINTS: each one picks M at its own fraction along
                        # the exit and swings everything after it about M by its angle
                        # (Y-axis, XZ plane). Whatever the exit shape currently is, this
                        # just re-orients the tail around M — the leg up to M is
                        # untouched, the end point moves with the tail, and the
                        # clearance correction (below) still applies.
                        # `breaks` is already the pass's own list OR the op's legacy
                        # single exit_mid break, so one break here is bit-identical to
                        # what the old code produced.
                        # #92: mutually exclusive with the curl — radius wins, and the
                        # editor greys the button out so this is visible, not silent.
                        if not (abs(_curl_r) > 1e-4 or abs(_curl_re) > 1e-4):
                            exit_portion = exit_breaks.apply(exit_portion, breaks or [])

                    # The arm is ALWAYS the straight positioning leg now, in both
                    # directions (#82's "put the bow here on a reverse pass" is
                    # deleted — see above; it never survived the collapse below).
                    n_ap     = max(2, int(np.linalg.norm(T1 - ap_start) / check_res))
                    approach = np.linspace(ap_start, T1, n_ap)
                    _ap_split = len(approach) - 1   # straight arm reduces to 2 pts; fillet+exit stays dense
                    _exit_len = len(exit_portion)
                    if _fillet_len > 0:
                        pts_raw = np.vstack([approach[:-1], arc_pts, exit_portion[1:]])
                    else:
                        pts_raw = np.vstack([approach[:-1], exit_portion])

                    if len(pts_raw) == 0: break

                else:  # "spline" — original behaviour
                    pts_raw = self._generate_spline(p1, p2, p3, num_points)
                    if len(pts_raw) == 0: break

                # 3. Apply Rotation (Aligned to P2 surface normal)
                nx, nz = _place_normal(p2.Z())
                if pass_shape in ("linear_approach", "linear_full"):
                    # Rotation about P2 would tilt the pure-Z approach arm and shift P3
                    # off its computed position — both guarantees this shape exists for.
                    # Direction is already controlled explicitly via pass_angle/progressive.
                    final_rot = 0.0
                else:
                    final_rot = base_rot
                if auto_align and pass_shape not in ("linear_approach", "linear_full"):
                    surface_angle = math.degrees(math.atan2(nz, nx))
                    raw_rot = -surface_angle + base_rot
                    # Clamp 2: geometric constraint — P3 must stay above P2 in Z after rotation.
                    # After Y-axis rotation θ: P3.z_rel = -p1_x*sin(θ) + p3_z*cos(θ).
                    # P3 stays above P2 only when θ < atan2(p3_z, p1_x).
                    # Without this, large positive rotation flips P3 below P2 → arc inverts → straight-line appearance.
                    _px = abs(p1_x_offset); _p3z = abs(p3_z_offset); _p1z = abs(p1_z_offset)
                    _geo_max =  float('inf')
                    _geo_min = float('-inf')
                    if _px > 0.001 and _p3z > 0.001:
                        geo_max_rot = math.degrees(math.atan2(_p3z, _px)) * 0.9
                        raw_rot = min(raw_rot, geo_max_rot)
                        _geo_max = geo_max_rot
                    if _px > 0.001 and _p1z > 0.001:
                        geo_max_neg_rot = math.degrees(math.atan2(_p1z, _px)) * 0.9
                        raw_rot = max(raw_rot, -geo_max_neg_rot)
                        _geo_min = -geo_max_neg_rot
                    final_rot = raw_rot
                    if attempt == 0:
                        _clamp_note = ""
                        if abs(final_rot - (-surface_angle + base_rot)) > 0.1:
                            _clamp_note = f" ← CLAMPED (geo window [{_geo_min:.1f}°, {_geo_max:.1f}°])"
                        logger.info(
                            f"[PARAM_DEBUG] '{pass_name}' rotation: auto_align ON | "
                            f"surface_angle={surface_angle:.1f}° base_rot={base_rot:.1f}° | "
                            f"raw={-surface_angle + base_rot:.1f}° → final={final_rot:.1f}°{_clamp_note}"
                        )
                elif attempt == 0:
                    if pass_shape in ("linear_approach", "linear_full"):
                        logger.info(f"[PARAM_DEBUG] '{pass_name}' rotation: locked to 0° (linear shape — use pass_angle to control direction)")
                    else:
                        logger.info(f"[PARAM_DEBUG] '{pass_name}' rotation: auto_align OFF, using base_rot={final_rot:.1f}° | TIP: enable Auto-Calc Angle to align pass to mandrel surface")

                check_pts = pts_raw
                if abs(final_rot) > 0.01:
                    check_pts = self._apply_rotation(pts_raw, final_rot, p2)
                
                # 4. Clearance check & correction
                # Safety FLOOR (renamed from the old two-way `target_clearance` setter):
                # the minimum allowed roller-to-blank gap. Applied ONE-WAY below — it can
                # only push a pass OUT, never pull it in (pulling in is what overrode the
                # op's clearance and made roughing sit closer than finishing).
                target_clearance = float(params.get("min_safety_gap", params.get("target_clearance", 0.0)))

                # Mandrel Z sınırları — sınır dışındaki noktalarda clearance hesabı yapma
                _m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
                _m_top_z = mandrel_mgr.props.get("top_z", float('inf'))

                if params.get("clearance_correction_per_point", False):
                    # PER-POINT NORMAL CORRECTION
                    # Each point is independently pushed out along its local surface normal
                    # if it violates the minimum clearance. Spline shape is preserved everywhere else.
                    check_pts = self._enforce_min_clearance(
                        check_pts, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, target_clearance)
                    # No further iterations needed — fall through to debug_lines + break

                else:
                    # UNIFORM SHIFT: find minimum clearance, shift all control points in X, iterate
                    min_clearance = float('inf')
                    for pt in check_pts:
                        sim_x, sim_y, sim_z = pt
                        if sim_z < _m_min_z or sim_z > _m_top_z:  # mandrel dışı: atla
                            continue
                        m_rad = max(0.0, mandrel_mgr.get_radius_fast(sim_z))
                        dist_to_axis = math.sqrt((sim_x - center_x)**2 + sim_y**2)
                        clearance = dist_to_axis - (m_rad + blank_thick + shell_offset + r_tool)
                        if clearance < min_clearance:
                            min_clearance = clearance

                    if min_clearance == float('inf'):
                        break  # tüm noktalar mandrel dışında, çarpışma yok

                    # ONE-WAY floor: only act when the closest point is nearer than the
                    # floor; push it back out. Never pull a too-far pass in (that would
                    # override the op's `clearance`).
                    if min_clearance < target_clearance - 0.01:
                        diff = target_clearance - min_clearance   # > 0 → outward only
                        _p2x_before = p2.X()
                        p1 = gp_Pnt(p1.X() + diff, 0, p1.Z())
                        p2 = gp_Pnt(p2.X() + diff, 0, p2.Z())
                        p3 = gp_Pnt(p3.X() + diff, 0, p3.Z())
                        logger.info(
                            f"[PARAM_DEBUG] '{pass_name}' safety-floor iter {attempt+1}: "
                            f"min_clearance={min_clearance:.3f}mm (floor={target_clearance:.3f}mm) → "
                            f"pushing out +{diff:.3f}mm in X | P2: {_p2x_before:.2f} → {p2.X():.2f}"
                        )
                        continue
                
                # If we reach here, check passed or max iterations reached.
                # Generate Final Analysis Line - ONLY the MINIMUM clearance point
                if debug_lines is not None and len(check_pts) > 0:
                    min_cl = float('inf')
                    min_line = None
                    min_status = 0
                    
                    for pt in check_pts:
                         sim_x, sim_y, sim_z = pt

                         m_rad = max(0.0, mandrel_mgr.get_radius_fast(sim_z))
                         required_dist = m_rad + blank_thick + shell_offset + r_tool
                         dist = math.sqrt((sim_x - center_x)**2 + sim_y**2)
                         clearance = dist - required_dist
                         
                         if clearance < min_cl:
                             min_cl = clearance
                             p_pass = [sim_x, sim_y, sim_z]
                             p_mandrel = [center_x + m_rad, 0, sim_z]
                             min_line = [p_pass, p_mandrel]
                             
                             # Color based on clearance
                             if clearance < 0:
                                 min_status = 2 # Collision (Red)
                             elif clearance < target_clearance:
                                 min_status = 1 # Warning (Yellow)
                             else:
                                 min_status = 0 # Safe (Green)
                    
                    if min_line:
                        # Store: [p_pass, p_mandrel, status, clearance_value]
                        debug_lines.append([min_line[0], min_line[1], min_status, min_cl])
                
                # Use the ROTATED points for final output
                final_points = check_pts
                _total_shift = p2.X() - _dbg_init_p2x
                logger.info(
                    f"[PARAM_DEBUG] '{pass_name}' RESULT: {len(final_points)} pts | "
                    f"P2 X: {_dbg_init_p2x:.2f} → {p2.X():.2f} (clearance shift {_total_shift:+.2f}mm) | "
                    f"path start=({final_points[0][0]:.2f}, Z={final_points[0][2]:.2f}) "
                    f"end=({final_points[-1][0]:.2f}, Z={final_points[-1][2]:.2f}) | "
                    f"rotation applied={final_rot:.2f}°"
                )
                break

             
            if len(final_points) == 0:
                final_points = check_pts # Fallback

            # For linear_approach: straight approach arm needs only 2 points (start + P2).
            # Render-split bookkeeping: index of T1 (end of the straight approach
            # line) and T2 (end of the P2 fillet arc) within final_points, tracked
            # through the transforms below so the renderer never has to re-guess
            # the straight/arc/curve boundaries via heuristics.
            _line_end = _ap_split
            _arc_end  = (_ap_split + _fillet_len - 1) if (_ap_split is not None and _fillet_len > 0) else _ap_split

            # #100 D11: report a hand-drawn tail that sits closer to the part than
            # the op's clearance. Checked against the FINAL P2 — the safety floor
            # above may have pushed the whole pass outward, and the tail travels
            # with it (the operator's offsets are P2-relative), so checking earlier
            # would flag a tail that has since been moved clear.
            #
            # This REPORTS, it does not correct: the safety floor stays the last
            # line of defence exactly as before, untouched. The point of the
            # warning is that a shifted pass is a silently different pass, and on
            # a tail the operator drew by hand that is worth saying out loud.
            if exit_points:
                try:
                    _m_min = mandrel_mgr.props.get("min_z", float('-inf'))
                    _m_top = mandrel_mgr.props.get("top_z", float('inf'))

                    def _rad_at(_z, _mm=_m_min, _mt=_m_top):
                        if _z < _mm or _z > _mt:
                            return None
                        return mandrel_mgr.get_radius_fast(_z)

                    _bad = exit_waypoints.check_clearance(
                        exit_waypoints.build_curve(p2.X(), p2.Z(), exit_points),
                        _rad_at, center_x, blank_thick + shell_offset + r_tool,
                        float(op_clearance))
                    if _bad:
                        self.last_waypoint_warnings.append({
                            "pass_name": pass_name,
                            "op_name": (op or {}).get("name")
                                       or (op or {}).get("type", "?"),
                            "n_points": len(exit_points),
                            "n_violating": len(_bad),
                            "worst": _bad[0],
                            "clearance": float(op_clearance),
                        })
                        logger.info(
                            f"[#100] '{pass_name}' exit tail is closer than the op "
                            f"clearance ({op_clearance:.2f}mm) at {len(_bad)} sampled "
                            f"point(s); worst {_bad[0]['clearance']:.3f}mm at "
                            f"X{_bad[0]['x']:.2f} Z{_bad[0]['z']:.2f}")
                except Exception:
                    pass        # a reporting failure must never break a calculation

                # #100 (research 2026-08-27): the safety floor pushes P2 outward
                # until the WHOLE pass clears — and the tail is part of the pass.
                # A tail drawn at one Z and later run at another can therefore
                # shove the entire pass off the work: measured 68→85 mm on a
                # shouldered mandrel, where the same pass without a tail needed
                # only 68→71. Nothing collides, but the roller stops touching the
                # part and the pass silently does no work. Report the shift and
                # let the operator judge it.
                try:
                    _shift = abs(p2.X() - _dbg_init_p2x)
                    if _shift > TAIL_SHIFT_REPORT_MM:
                        self.last_waypoint_shifted.append({
                            "pass_name": pass_name,
                            "op_name": (op or {}).get("name")
                                       or (op or {}).get("type", "?"),
                            "shift": float(_shift),
                            "n_points": len(exit_points),
                        })
                        logger.info(
                            f"[#100] '{pass_name}' carries a hand-drawn tail and the "
                            f"safety floor moved the pass {_shift:.2f}mm outward — the "
                            f"tail moved with it; contact may no longer be where it was drawn")
                except Exception:
                    pass

            # Reduce before gcode_resolution so the downsampler doesn't add redundant collinear pts.
            if _ap_split is not None and _ap_split > 1 and len(final_points) > _ap_split + 1:
                final_points = np.vstack([
                    final_points[[0, _ap_split]],
                    final_points[_ap_split + 1:]
                ])
                _arc_end  = max(1, _arc_end - _ap_split + 1)
                _line_end = 1

            # Downsample for G-code output (separate from collision_resolution).
            # T1/T2 are force-kept so the (line_end, arc_end) indices stay valid
            # in the final, possibly-downsampled array.
            gcode_res = float(params.get("gcode_resolution", 2.0))
            _force_idx = {i for i in (_line_end, _arc_end) if i is not None}
            # #100 straight mode: the exit vertices are the operator's points.
            # They sit contiguously after T2 (exit_portion[1:] was stacked there),
            # and gcode_resolution would silently drop any pair closer than ~2 mm —
            # dropping a point he can see in the table, along with its feed.
            if _wp_verbatim and _arc_end is not None and _exit_len > 1:
                _force_idx |= set(range(_arc_end + 1, _arc_end + _exit_len))
            _render_pos = {}
            if gcode_res > 0.01 and len(final_points) > 2:
                downsampled = [final_points[0]]
                for rel_idx, pt in enumerate(final_points[1:-1], start=1):
                    forced = rel_idx in _force_idx
                    if forced or np.linalg.norm(np.array(pt) - np.array(downsampled[-1])) >= gcode_res:
                        downsampled.append(pt)
                    if forced:
                        _render_pos[rel_idx] = len(downsampled) - 1
                downsampled.append(final_points[-1])
                final_points = downsampled
            else:
                for i in _force_idx:
                    if i < len(final_points):
                        _render_pos[i] = i

            _path_idx = len(t_list)
            t_list.append(np.array(final_points))

            # #100: remember where this pass's waypoints ended up, so G-code
            # emission can apply their per-point feeds without re-deriving P2
            # (which the safety floor may have moved after the tail was built).
            if exit_points:
                _res = exit_waypoints.resolve(p2.X(), p2.Z(), exit_points)
                self.last_waypoint_abs[_path_idx] = [
                    {"x": _x, "z": _z, "feed": _w.get("feed")}
                    for (_x, _z), _w in zip(_res, exit_points)]
                if _wp_verbatim:
                    # Tell the PLC decimator to leave this tail alone: RDP would
                    # happily drop a collinear waypoint, which changes no shape
                    # but DOES lose the feed step the operator put on it.
                    self.last_exit_verbatim.add(_path_idx)

            # #102: how many breaks shaped this path's exit leg. Recorded here
            # because the decimator works on path indices and cannot see which
            # pass a path came from — and without it, a point cap that flattens
            # a break cannot tell that anything was lost (the clearance gate it
            # already has only notices when the tail moves TOWARD the part; a
            # flattened break moves it away and passes silently).
            if breaks:
                self.last_exit_break_counts[_path_idx] = len(breaks)

            if _line_end is not None and _line_end in _render_pos:
                self.last_render_split_idx[_path_idx] = (
                    _render_pos[_line_end],
                    _render_pos.get(_arc_end, _render_pos[_line_end]),
                )
            
            # Control Pts
            c_pts = np.array([ [p1.X(), 0, p1.Z()], [p2.X(), 0, p2.Z()], [p3.X(), 0, p3.Z()] ])
            c_list.append(c_pts)
            
            # Deviation / Heatmap Data
            devs = []
            for pt in final_points:
                m_r = mandrel_mgr.get_radius_fast(pt[2])
                dist = math.sqrt((pt[0]-center_x)**2 + pt[1]**2)
                limit = m_r + blank_thick + shell_offset + r_tool
                if m_r is not None: devs.append(dist - limit)
                else: devs.append(0.0)
            d_list.append(np.array(devs))
            
            # Projections (Visual Helper)
            proj_line = []
            step_size = 5 if len(final_points) > 50 else 1
            for pt in final_points[::step_size]:
                z_cur = pt[2]
                r_surf = mandrel_mgr.get_radius_fast(z_cur)
                if r_surf is None: continue 
                px = center_x + r_surf + shell_offset + blank_thick
                proj_line.append([px, 0, z_cur])
            
            # Projeksiyon çizgisi Z aralığı:
            # op içindeki proj_extend_bottom / proj_extend_top ile kullanıcı
            # mandrel sınırları dışına ne kadar uzatılacağını belirler (mm, default 0).
            _op = op or {}
            _min_z = mandrel_mgr.props.get("min_z", 0.0) - float(_op.get("proj_extend_bottom", 0.0))
            _max_z = mandrel_mgr.props.get("top_z", 100.0) + float(_op.get("proj_extend_top", 0.0))
            proj_line = [p for p in proj_line if _min_z <= p[2] <= _max_z]
            if proj_line: p_list.append(np.array(proj_line))

    def _compute_proj_and_devs(self, path, mandrel_mgr, center_x, shell_offset, blank_thick, r_tool, op=None):
        """Compute projection line and deviation array from the actual path points.
        Used for back passes so their visual data reflects their own geometry rather
        than a reversed copy of the forward pass arrays."""
        devs = []
        for pt in path:
            m_r = mandrel_mgr.get_radius_fast(pt[2])
            dist = math.sqrt((pt[0] - center_x) ** 2 + pt[1] ** 2)
            limit = m_r + blank_thick + shell_offset + r_tool
            devs.append(dist - limit if m_r is not None else 0.0)

        proj_line = []
        step_size = 5 if len(path) > 50 else 1
        for pt in path[::step_size]:
            r_surf = mandrel_mgr.get_radius_fast(pt[2])
            if r_surf is None:
                continue
            proj_line.append([center_x + r_surf + shell_offset + blank_thick, 0, pt[2]])

        _op = op or {}
        _min_z = mandrel_mgr.props.get("min_z", 0.0) - float(_op.get("proj_extend_bottom", 0.0))
        _max_z = mandrel_mgr.props.get("top_z", 100.0) + float(_op.get("proj_extend_top", 0.0))
        proj_line = [p for p in proj_line if _min_z <= p[2] <= _max_z]

        proj_arr = np.array(proj_line) if proj_line else np.array([])
        devs_arr = np.array(devs)
        return proj_arr, devs_arr

    def _waypoint_feed_map(self, path_arr, wp_abs):
        """#100: per-point feed for a pass whose exit tail was drawn by hand.

        STEP semantics (user, 2026-08-27): a waypoint's feed governs the span
        ARRIVING at it — set the slow number on the point near the sheet edge and
        the roller is already slow when it gets there. A blank feed inherits
        whatever the previous span was running, so the operator only fills in the
        points he actually cares about.

        Works off geometry rather than array indices, so it survives the PLC
        decimation and the G-code downsampler resampling the tail: each waypoint
        is located by its nearest emitted point.

        Returns a list the same length as path_arr, holding a float or None,
        or None when there is nothing to apply.
        """
        if not wp_abs or path_arr is None or len(path_arr) < 2:
            return None
        if all(w.get("feed") is None for w in wp_abs):
            return None

        pts = np.asarray(path_arr, dtype=float)
        bounds = []
        for w in wp_abs:
            d = np.hypot(pts[:, 0] - float(w["x"]), pts[:, 2] - float(w["z"]))
            bounds.append((int(np.argmin(d)), w.get("feed")))
        bounds.sort(key=lambda b: b[0])

        out = [None] * len(pts)
        prev_idx = 0
        carried = None
        for idx, feed in bounds:
            eff = feed if feed is not None else carried
            if eff is not None:
                for k in range(prev_idx, min(idx + 1, len(out))):
                    out[k] = eff
            prev_idx = max(prev_idx, idx + 1)
            carried = eff
        if carried is not None:                 # anything past the last waypoint
            for k in range(prev_idx, len(out)):
                out[k] = carried
        return out

    def _contact_zone_mask(self, path_arr, center_x, contact_zone_mm,
                           r_tool, blank_thick, shell_offset):
        """
        Per-point boolean mask marking where the roller is near the mandrel.

        Uses the SAME true roller-to-blank-surface clearance the path generator
        relies on for collision safety (see _correct_clearance_uniform):
            dist  = sqrt((x - center_x)^2 + y^2)          # radial dist from axis
            clear = dist - (surface_radius(z) + blank_thick + shell_offset + r_tool)
        `clear` is 0 when the roller touches the blank and grows as it pulls away.
        Because `dist` is a magnitude it is orientation-independent — it works no
        matter which radial side of the axis the roller sits on — and it follows a
        curved profile via get_radius_fast(z). A point is "in the contact zone" when
        it is within `contact_zone_mm` of the surface:
            clear <= contact_zone_mm
        Applied identically to forward and back passes.

        Returns a numpy bool array (len == len(path_arr)) or None when disabled /
        unavailable (contact_zone_mm <= 0, no mandrel, or fewer than 2 points).
        """
        mgr = self.last_mandrel_mgr
        if contact_zone_mm <= 0 or mgr is None or path_arr is None or len(path_arr) < 2:
            return None
        m_min_z = mgr.props.get("min_z", float('-inf'))
        m_top_z = mgr.props.get("top_z", float('inf'))
        clears = np.empty(len(path_arr))
        for i, (x, y, z) in enumerate(path_arr[:, :3]):
            zc = min(max(z, m_min_z), m_top_z)                 # clamp, don't skip
            m_rad = max(0.0, mgr.get_radius_fast(zc))
            dist = math.sqrt((x - center_x) ** 2 + y ** 2)
            clears[i] = dist - (m_rad + blank_thick + shell_offset + r_tool)
        return clears <= contact_zone_mm

    def generate_gcode(self, feed: int = 1000, speed: int = 200, max_rpm: int = 2000, params: dict = None,
                       for_recipe: bool = False) -> str:
        """
        Generates CNC G-Code for the calculated toolpaths.

        ``for_recipe`` marks output that is about to be converted into a PLC
        recipe (SCL). It describes the OUTPUT PATH, not a machine setting, and
        is deliberately NOT derived from params["plc_mode"]: plc_mode only asks
        for decimation, and a PLC machine may legitimately run with it off
        (ID112-1 does, at plc_tolerance 0.01), so keying off it would leave that
        machine with the very lines this flag exists to drop. Every SCL caller
        must pass it; .nc output leaves it False and stays byte-identical.

        When params["plc_mode"] is True, each toolpath is decimated using
        the Ramer-Douglas-Peucker algorithm before G-code emission.  The
        closest-to-mandrel point on every pass is always preserved so that
        the critical contact geometry is never lost.  The tolerance is
        controlled by params["plc_tolerance"] (mm, default 0.5).
        The CNC path (gcode_resolution) is NOT affected.
        """
        if params is None: return ""
        # "Nothing calculated" USED to mean "no toolpaths". Point ops broke that
        # equivalence: they emit real machine moves but append no toolpath, so a
        # program made only of Point ops (a jog or setup routine) would have
        # silently produced an empty file. Emit when there is anything to say.
        if not self.last_calculated_paths and not any(
                o.get("type") == "point" and o.get("enabled", True)
                for o in (params.get("operations") or [])):
            return ""

        # --- PLC Mode: decimated path list ---
        plc_mode = bool(params.get("plc_mode", False))
        plc_tolerance = float(params.get("plc_tolerance", 0.5))
        center_x = float(params.get("mandrel_pos_x_offset", 0.0))
        # Roller side, for the pass retract: it must pull AWAY from the part, which
        # is -X on a negative-side machine. See retract_x_offset_real.
        ret_side = 1.0 if params.get("roller_positive_x_side", True) else -1.0

        if plc_mode:
            _exit_tol = float(params.get("plc_exit_tolerance", plc_tolerance))
            paths_to_use = self.decimate_all_paths(plc_tolerance, _exit_tol, center_x,
                                                   params=params)
            logger.info(
                f"[PLC Mode] Decimated {len(self.last_calculated_paths)} paths. "
                f"Points: {sum(len(p) for p in self.last_calculated_paths)} → "
                f"{sum(len(p) for p in paths_to_use)} (tol={plc_tolerance} mm)"
            )
        else:
            paths_to_use = self.last_calculated_paths
        # Remember what PLC mode emitted so the auto-tune / clearance guard can
        # measure the exact chords the machine will run.
        self.last_plc_paths = paths_to_use

        # ── Tilt-arm machines (ID112): per-point B words + reachability check.
        # Tilt is recomputed from the emitted point list itself (decimated or
        # not) via _compute_tilt_for_path, so words always match the points.
        _tilt_kin = get_kinematics(params)
        _tilt_mgr = getattr(self, "last_mandrel_mgr", None)
        self.last_kinematic_warnings = []

        invert_x = params.get("machine_invert_x", False)
        invert_z = params.get("machine_invert_z", False)  # [NEW] Z axis inversion
        dia_mode = params.get("machine_output_diameter_mode", False)
        
        # [NEW] Machine Origin in Global Coords (Post-Processor)
        origin_x = params.get("machine_origin_x", 0.0)
        origin_z = params.get("machine_origin_z", 0.0)
        # Override: origin = safe home position
        if params.get("origin_use_home", False):
            origin_x = params.get("home_x", 0.0)
            origin_z = params.get("home_z", 0.0)
        
        # Additional Work Offsets (G54 style, applied AFTER origin transformation)
        off_x = params.get("machine_gcode_offset_x", 0.0)
        off_z = params.get("machine_gcode_offset_z", 0.0)
        
        # Axis direction multipliers
        dir_x = -1.0 if invert_x else 1.0
        dir_z = -1.0 if invert_z else 1.0
        
        # Get Template Strings
        header_tmpl = params.get("gcode_header", "G21 G90 G18\nG54")
        
        # Tool & Operation Setup
        operations = self._ensure_ops_dict(params)

        # Custom Commands
        raw_cmds = params.get("custom_commands", [])
        pass_cmds = [(int(float(c["value"])), c["cmd"]) for c in raw_cmds if c.get("trigger") == "pass"]
        z_cmds    = [(float(c["value"]), c["cmd"])      for c in raw_cmds if c.get("trigger") == "z"]
        # program_start ignores "value" entirely — the trigger IS the moment.
        start_cmds = [c["cmd"] for c in raw_cmds if c.get("trigger") == "program_start"]

        mcode_descriptions = params.get("mcode_descriptions", {})

        def _annotate_mcode(cmd_str):
            """Append M-code description as a G-code comment if one is defined."""
            if '(' in cmd_str:
                return cmd_str
            m = re.search(r'M(\d+)', cmd_str, re.IGNORECASE)
            if m:
                desc = mcode_descriptions.get(m.group(1), "")
                if desc:
                    return f"{cmd_str} ({desc})"
            return cmd_str

        def _emit_custom(cmd_str):
            """Emit a user-defined M-code, and forget the tracked spindle state
            if it touches the spindle.

            Custom commands are free text: nothing stops an operator typing
            "M5" or "M3 S900" as a program-start / pass / Z-triggered command.
            Either one changes the spindle behind the emitter's back, and a
            stale ``_last_spindle`` would then make the next operation SKIP a
            command it genuinely needs — a spindle left off, or left at the
            wrong speed. Forgetting is always safe; the next op re-commands.

            M30 / M35 / M53 must NOT match, hence the word boundary.
            """
            nonlocal _last_spindle
            gcode.append(_annotate_mcode(cmd_str))
            if re.search(r'\bM0*[35]\b', cmd_str, re.IGNORECASE):
                _last_spindle = None

        # Split line by line
        plc_label = " [PLC MODE]" if plc_mode else ""
        gcode = ["%", f"O1001 (METAL SIVAMA - {len(paths_to_use)} PASO{plc_label})"]
        gcode.extend(header_tmpl.splitlines())
        
        # Configurable Machine Home / Safe Pts
        home_x = params.get("home_x", 300.0)
        home_z = params.get("home_z", 150.0)
        
        # [NEW] Transform Home Position through post-processor
        def _xf_pt(gx, gz):
            """Post-processor transform for a single (global X, global Z) — same math
            as the per-point transform_pt below, reused for the tool-change target."""
            xo = ((gx - origin_x) * dir_x) + off_x
            zo = ((gz - origin_z) * dir_z) + off_z
            if dia_mode: xo *= 2.0
            return xo, zo
        home_x_machine, home_z_machine = _xf_pt(home_x, home_z)

        # Machine Settings Comment Block
        gen_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        gcode.append(f"(Generated: {gen_time})")

        # --- CONTACT POINT (calibration touch) — highlighted, critical info ---
        calib = params.get("calibration_last_session", {}) or {}
        c_x = str(calib.get("entry_x", "")).strip()
        c_z = str(calib.get("entry_z", "")).strip()
        if c_x or c_z:
            c_surf = str(calib.get("surface", "")).strip()
            c_tool = str(calib.get("tool_var", "")).strip()
            c_rt   = str(calib.get("entry_rt", "")).strip()
            c_bt   = str(calib.get("entry_blank_t", "")).strip()
            gcode.extend([
                "(========================================)",
                "(===       CONTACT / TEMAS NOKTASI    ===)",
                f"(===   X = {c_x or '?':<6}   Z = {c_z or '?':<6}       ===)",
                "(========================================)",
            ])
            detail = []
            if c_surf: detail.append(f"Surface={c_surf}")
            if c_tool: detail.append(f"Tool={c_tool}")
            if c_rt:   detail.append(f"Rr={c_rt}mm")
            if c_bt:   detail.append(f"Blank={c_bt}mm")
            if detail:
                gcode.append(f"(Contact ref: {', '.join(detail)})")

        gcode.extend([
            "(--- MAKINE AYARLARI / POST-PROCESSOR ---)",
            f"(Machine Origin: X={origin_x}, Z={origin_z})",
            f"(Axis Direction: X={'INVERTED' if invert_x else 'NORMAL'}, Z={'INVERTED' if invert_z else 'NORMAL'})",
            f"(Output Mode: {'DIAMETER' if dia_mode else 'RADIUS'})",
            f"(G54 Offset: X={off_x}, Z={off_z})",
            f"(Program Start: X={params.get('home_x', 300.0)}, Z={params.get('home_z', 150.0)}) (PLC handles actual homing)",
            "(Program End: X={:g}, Z={:g}){}".format(
                *resolve_program_end(params),
                "" if params.get("end_use_home", True) else " (park position)"),
            "(Retract: per operation)",
            "(--- PARCA / BLANK ---)",
            f"(Blank Radius: {params.get('blank_radius', 0.0)} mm)",
            f"(Blank Z Shift: {params.get('blank_z_shift', 0.0)} mm)",
            f"(Final Thickness: {params.get('final_part_thickness_on_mandrel', 2.0)} mm)",
            f"(Safety Clearance: {params.get('safety_clearance_roller_to_part', 0.5)} mm)",
            "(--- MANDREL POZISYON ---)",
            f"(Mandrel Offset: X={params.get('mandrel_pos_x_offset', 0.0)}, Z={params.get('mandrel_pos_z_offset', 0.0)})",
            f"(Mandrel Rotation: Rx={params.get('mandrel_rot_x', 0.0)}, Ry={params.get('mandrel_rot_y', 0.0)}, Rz={params.get('mandrel_rot_z', 0.0)})",
            "(--- OPERASYONLAR ---)",
        ])
        for i, op in enumerate(operations):
            op_type = op.get("type", "Process").upper()
            op_count = op.get("count", 1)
            op_tool = op.get("tool_id", "T0101")
            op_speed = op.get("speed", 0)
            op_s_mode = resolve_speed_mode(op)
            op_feed = op.get("feed", 0)
            op_f_mode = op.get("feed_mode", "mm_min")
            op_r = op.get("r_tool", 0)
            gcode.append(
                f"(Op{i+1}: {op_type}, {op_count} paso, {op_tool}, "
                f"R={op_r}mm, {op_s_mode}={op_speed}, {op_f_mode}={op_feed})"
            )
        gcode.extend(["", f"G50 S{max_rpm} (Devir Siniri)"])
        # The staged Z-then-X move to Program Start is a G-code homing
        # convention: it gives the first pass a known start point, because the
        # move into a pass (see "Op{n} P{n}" below) is a coordinated diagonal
        # that would otherwise sweep from wherever the roller happens to sit.
        #
        # A PLC recipe does not need it. Every recipe line carries absolute X
        # AND Z, the PLC homes before every run (so the known start point is
        # already guaranteed), and with origin_use_home the pair transforms to
        # X0 Z0 — two identical CMD=0 rows. At best they are a no-op; when the
        # operator has jogged in or the start cylinder has moved the roller,
        # they drag it BACK to zero before work starts. Note the program_start
        # custom commands (M40 etc.) are emitted AFTER this block, so on the
        # recipe path the cylinder sequence is now the first thing that runs.
        if not for_recipe:
            gcode.append(f"G0 Z{home_z_machine:.3f} (Program Start Z)")
            gcode.append(f"G0 X{home_x_machine:.3f} (Program Start X)")
        gcode.append("")

        # NOTE: the dedicated "Cylinder GOTO" block that used to sit here was
        # removed 2026-07-30. M40 is now an ordinary program_start custom
        # command, so the cylinder's extend/relax/retract sequence lives in ONE
        # list instead of being split between a checkbox and a command table —
        # which is how a disabled M40 went unnoticed while its valve commands
        # kept firing. Existing setups are converted by
        # config_schema.migrate_cylinder_mcode, so nobody loses their extend.

        # The spindle command actually WRITTEN last, as (speed code, integer rpm),
        # or None when unknown. Declared HERE, above the first _emit_custom call
        # below — that helper writes it, and a future edit that also READS it
        # would raise UnboundLocalError if this line sat further down.
        #
        # An operation re-commanding a speed the spindle already holds is a no-op
        # on the PLC (CMD=20 writes the target and does not block — confirmed by
        # the PLC side 2026-08-31) but still costs one of the 1000 recipe lines.
        # DB_RecipeProgram1.scl spent 25 of its 205 lines that way; recipe3 spent
        # 15 while sitting at 999 against the cap.
        #
        # The pair, not the number: G96 S200 and G97 S200 are different commands
        # if CSS is ever re-enabled. The INTEGER, not the float: 800.0 and 800.4
        # both write "S800", and comparing floats would emit twice for no change.
        _last_spindle = None

        # Program-start custom commands — here, and NOT in the pass loop,
        # because this is the only point that is still before the tool change
        # and before the spindle starts. An actuator that has to be set while
        # the part is stationary (a back support clamping the blank) cannot use
        # a "pass 1" trigger: that fires after S.. M3 is already running.
        if start_cmds:
            gcode.append("(--- PROGRAM START ---)")
            for scmd in start_cmds:
                _emit_custom(scmd)
            gcode.append("")

        safe_x_machine = home_x_machine  # Use transformed safe X
        current_tool = None
        global_path_idx = 0
        total_paths = len(paths_to_use)
        
        # --- OPERATION BASED LOOP ---
        for op_idx, op in enumerate(operations):
            if not op.get("enabled", True): continue
            
            count = int(op.get("count", 1))
            op_tool = op.get("tool_id", "T0101")
            op_type = op.get("type", "Process").upper()
            
            # Velocity Params
            s_mode = resolve_speed_mode(op)  # CSS or RPM (CSS currently disabled)
            f_mode = op.get("feed_mode", "mm_min") # mm_min or mm_rev
            
            def_speed = params.get("surface_speed_m_min", 200)
            def_feed = params.get("feed_rate_mm_min", 300)
            
            val_speed = float(op.get("speed", def_speed))
            val_feed = float(op.get("feed", def_feed))
            
            code_speed = "G96" if s_mode == "CSS" else "G97"
            code_feed = "G98" if f_mode == "mm_min" else "G99"
            
            # Tool Change / Init Logic
            tool_differs = (op_tool != current_tool)
            
            if tool_differs and current_tool is not None:
                 # Resolve the retract target (global home / absolute / relative to
                 # the previous pass end) — same helper the 3D sim uses so they agree.
                 _prev_end = (np.asarray(paths_to_use[global_path_idx - 1][-1], dtype=float)
                              if global_path_idx > 0 else np.array([home_x, 0.0, home_z]))
                 _tc = resolve_tool_change_point(
                     op, _prev_end, np.array([home_x, 0.0, home_z]))
                 _tc_x_m, _tc_z_m = _xf_pt(float(_tc[0]), float(_tc[2]))
                 _tc_mode = str(op.get("tool_change_mode", "global") or "global").lower()
                 _tc_sim = bool(op.get("tool_change_simultaneous", False))
                 gcode.extend(["", "(--- TOOL CHANGE SAFETY ---)"])
                 if _tc_mode == "global":
                     gcode.append(f"G0 Z{_tc_z_m:.3f} (Home Z)")
                     gcode.append(f"G0 X{_tc_x_m:.3f} (Retract X)")
                 elif _tc_sim:
                     # Coordinated diagonal — both axes move together in one G0.
                     gcode.append(f"G0 X{_tc_x_m:.3f} Z{_tc_z_m:.3f} (Tool Change XZ, {_tc_mode})")
                 else:
                     gcode.append(f"G0 Z{_tc_z_m:.3f} (Tool Change Z, {_tc_mode})")
                     gcode.append(f"G0 X{_tc_x_m:.3f} (Tool Change X, {_tc_mode})")
                 # No M5/M1: the spindle runs through the turret index (user
                 # decision 2026-08-31 — the turret is automatic, and the G0
                 # above is the clearance that matters).
                 # M1 also had to go: the recipe has no such command, so it came
                 # out as CMD=1 (LINEAR) with F=0 — see LAST_CHANGES 2026-08-31d.
                 # Revert for a hand-changed turret: gcode.extend(["M5"]).
                 #
                 # The INCOMING op's speed is commanded HERE, before M6, not
                 # after it. What follows the tool change is a rapid into the
                 # work and then the first cut, so a speed set after M6 can
                 # still be ramping when the cut starts — recipe1's Op17 drops
                 # 800 → 500 for a cutting pass at 5 mm/min. Setting it first
                 # gives the spindle the whole turret index plus the approach to
                 # settle, and the turret indexes at the speed the new tool
                 # wants rather than the speed the old one was using.
                 #
                 # A tool change ALWAYS re-commands the speed, even when the
                 # number is unchanged (so this one is exempt from the
                 # redundancy skip below). Whether CMD=10 disturbs spindle state
                 # on the PLC is not documented — unlike CMD=20, which the PLC
                 # side confirmed is a plain setpoint write. The insurance costs
                 # one line per change: two in all of DB_RecipeProgram1.scl.
                 gcode.append(f"{code_speed} S{int(val_speed)} M3")
                 _last_spindle = (code_speed, int(val_speed))
                 _speed_already_set = True
            else:
                 _speed_already_set = False

            if tool_differs or current_tool is None:
                 gcode.append(f"M6 {op_tool} ({op_type})")
                 if not _speed_already_set:
                     # First op of the program: no tool-change block ran, so the
                     # spindle has not been started yet.
                     gcode.append(f"{code_speed} S{int(val_speed)} M3")
                     _last_spindle = (code_speed, int(val_speed))
                 gcode.append(f"{code_feed} (Feed: {f_mode})")
                 gcode.append("")
                 current_tool = op_tool
            elif current_tool == op_tool:
                 gcode.append(f"(Update Params: {val_speed} {s_mode}, {val_feed} {f_mode})")
                 # Same tool, so the spindle has not been touched since the last
                 # op: command it only if the number actually moved. The comment
                 # in the else branch is deliberate — it costs nothing in the
                 # recipe (comments are skipped by the parser) and stops the
                 # missing M3 from reading as an omission to whoever opens
                 # the .nc next.
                 _spindle_cmd = (code_speed, int(val_speed))
                 if _spindle_cmd != _last_spindle:
                     gcode.append(f"{code_speed} S{int(val_speed)} M3")
                     _last_spindle = _spindle_cmd
                 else:
                     gcode.append(f"(Spindle already at {code_speed} S{int(val_speed)})")
                 gcode.append(f"{code_feed}")

            # --- Point: go to ONE typed position and stop ---------------------
            # calculate_paths contributes NO toolpath for a Point, so this MUST
            # NOT touch global_path_idx — advancing it here would hand this op
            # the next op's pass. The tool-change and spindle block above has
            # already run, which is what makes "change the tool at this exact
            # place" work: put a Point op carrying the new tool_id where you want
            # the change to happen.
            #
            # Single-axis G0 lines are safe in the recipe: parse_gcode carries X
            # and Z modally (recipe_to_scl.py:472), so the omitted word keeps its
            # previous value — the same mechanism the tool-change retract has
            # always relied on.
            if op.get("type", "roughing") == "point":
                # center_x=None: the emitter is already in the real frame, so no
                # mirror conversion. `side` is still required — "surface" mode
                # adds a radial distance and must add it on the roller's side.
                # Anchors are supplied in this frame, mirroring the sim's use of
                # the previous pass's FORMING end (paths_to_use[idx-1][-1]) —
                # the same array both sites read, so they cannot disagree.
                _pt_prev = (np.asarray(paths_to_use[global_path_idx - 1][-1], dtype=float)
                            if global_path_idx > 0 else None)
                _pt = resolve_point_target(
                    op, center_x=None, side=ret_side, params=params,
                    mandrel_mgr=getattr(self, "last_mandrel_mgr", None),
                    prev_end=_pt_prev,
                    home_pt=np.array([home_x, 0.0, home_z]))
                _pt_x_m, _pt_z_m = _xf_pt(float(_pt[0]), float(_pt[2]))
                _pt_motion = resolve_point_motion(op)
                _pt_rapid, _pt_feed = resolve_point_feed(op, params)
                _g = "G0" if _pt_rapid else "G1"
                # F only on a LINEAR move — the recipe format requires F=0 on
                # every other command (CAM_INTERFACE_SPEC section 5), and the
                # PLC clamps it to 1..3000.
                _f = "" if _pt_rapid else f" F{max(1.0, min(3000.0, _pt_feed)):.3f}"
                _tag = f"(Point Op{op_idx+1})"
                gcode.append(f"(--- OP {op_idx+1}: {op_type} ---)")
                if _pt_motion == "x_first":
                    gcode.append(f"{_g} X{_pt_x_m:.3f}{_f} {_tag}")
                    gcode.append(f"{_g} Z{_pt_z_m:.3f}{_f} {_tag}")
                elif _pt_motion == "z_first":
                    gcode.append(f"{_g} Z{_pt_z_m:.3f}{_f} {_tag}")
                    gcode.append(f"{_g} X{_pt_x_m:.3f}{_f} {_tag}")
                else:
                    gcode.append(f"{_g} X{_pt_x_m:.3f} Z{_pt_z_m:.3f}{_f} {_tag}")
                gcode.append("")
                continue

            # calculate_paths emits exactly ONE path for a cutting/bending op and
            # ignores its `count` — so the emitter must too, or a stray count>1
            # (hand-edited .ssp, imported preset) makes this op swallow the NEXT
            # op's path and run it with the wrong tool and feed.
            emit_count = 1 if op.get("type", "roughing") in ("cutting", "bending") else count
            for i in range(emit_count):
                if global_path_idx >= total_paths: break

                path = paths_to_use[global_path_idx]
                gcode.append(f"(--- OP {op_idx+1}: {op_type} - PASO {i+1} ---)")

                # Per-pass feed
                t_pass = (i / (count - 1)) if count > 1 else 0.0
                pass_feed         = val_feed
                feed_contact_sv   = float(op.get("feed_contact",     pass_feed))
                feed_contact_ev   = float(op.get("feed_contact_end", feed_contact_sv))
                pass_feed_contact = feed_contact_sv + t_pass * (feed_contact_ev - feed_contact_sv)
                contact_zone_mm   = float(op.get("contact_zone_mm",  0.0))
                # Per-point mask: True where the roller is within contact_zone_mm of
                # the blank surface (same clearance measure the path generator uses).
                cz_r_tool      = float(op.get("r_tool", 25.0))
                cz_blank_thick = float(params.get("final_part_thickness_on_mandrel", 2.0))
                cz_shell_off   = float(params.get("shell_thickness", 0.0))
                contact_mask = self._contact_zone_mask(np.array(path), center_x, contact_zone_mm,
                                                       cz_r_tool, cz_blank_thick, cz_shell_off)
                # #100: per-point feeds from a hand-drawn exit tail, if this pass has one.
                wp_feeds = self._waypoint_feed_map(
                    np.array(path),
                    getattr(self, "last_waypoint_abs", {}).get(global_path_idx))

                # Per-point tilt for this (possibly decimated) point list.
                pass_tilts = None
                if _tilt_kin is not None and _tilt_mgr is not None:
                    pass_tilts = self._compute_tilt_for_path(np.array(path), op, _tilt_mgr, _tilt_kin)
                    _issues = _tilt_kin.check_reachable(np.array(path), pass_tilts)
                    if _issues:
                        self.last_kinematic_warnings.extend(
                            f"Op{op_idx+1} P{i+1}: {s}" for s in _issues[:5])

                # Pass-triggered custom commands (1-indexed)
                pass_num = global_path_idx + 1
                for (pn, pcmd) in pass_cmds:
                    if pn == pass_num:
                        _emit_custom(pcmd)

                def transform_pt(p_arr):
                    """
                    Post-Processor Coordinate Transformation:
                    X_machine = ((X_global - origin_x) * direction_x) + offset_x
                    Z_machine = ((Z_global - origin_z) * direction_z) + offset_z
                    """
                    x, y, z = p_arr[0], p_arr[1], p_arr[2]
                    # Apply post-processor transformation
                    x_out = ((x - origin_x) * dir_x) + off_x
                    z_out = ((z - origin_z) * dir_z) + off_z
                    # Apply diameter mode if enabled
                    if dia_mode: x_out *= 2.0
                    return x_out, z_out

                def _b_word(tilts, idx):
                    """' B<deg>' G-code word, or '' on plain-XZ machines (111 output unchanged)."""
                    if tilts is None:
                        return ""
                    return f" B{_tilt_kin.tilt_to_b(float(tilts[idx])):.3f}"

                s_x, s_z = transform_pt(path[0])
                gcode.append(f"G0 X{s_x:.3f} Z{s_z:.3f}{_b_word(pass_tilts, 0)} (Op{op_idx+1} P{i+1})")
                
                zones = op.get("zones", [])
                current_s_val = val_speed
                current_f_val = -1.0
                fired_z_indices = set()
                prev_raw_z = path[0][2] if len(path) > 0 else None

                for _pi, p in enumerate(path[1:], start=1):
                    tx, tz = transform_pt(p)
                    raw_z = p[2]

                    # Z-triggered custom commands (fire once per threshold per pass)
                    if prev_raw_z is not None:
                        for zi, (z_thresh, z_cmd) in enumerate(z_cmds):
                            if zi not in fired_z_indices:
                                if (prev_raw_z <= z_thresh < raw_z) or (prev_raw_z >= z_thresh > raw_z):
                                    _emit_custom(z_cmd)
                                    fired_z_indices.add(zi)
                    prev_raw_z = raw_z

                    # Check Zones
                    target_s = val_speed
                    target_f = pass_feed

                    for zdata in zones:
                         try:
                             zstart = float(zdata.get("start_z", 0))
                             zend = float(zdata.get("end_z", 0))
                             if min(zstart, zend) <= raw_z <= max(zstart, zend):
                                  target_s = float(zdata.get("speed", val_speed))
                                  target_f = float(zdata.get("feed", pass_feed))
                                  break
                         except (TypeError, ValueError, KeyError): pass

                    # Contact zone overrides everything — slow feed near the mandrel
                    if contact_mask is not None and contact_mask[_pi]:
                        target_f = pass_feed_contact

                    # #100: an explicit per-waypoint feed wins over the automatic
                    # contact-zone slow-down. The operator typed a number on that
                    # exact point of a tail he drew by hand; a rule inferred from
                    # proximity should not quietly overrule it. (They rarely meet
                    # anyway — the contact zone hugs the surface, the tail leaves it.)
                    if wp_feeds is not None and wp_feeds[_pi] is not None:
                        target_f = float(wp_feeds[_pi])


                    s_suffix = ""
                    if target_s != current_s_val:
                         s_suffix = f" {code_speed} S{int(target_s)}"
                         current_s_val = target_s
                    
                    f_suffix = ""
                    if abs(target_f - current_f_val) > 0.001:
                        f_suffix = f" F{target_f:.3f}"
                        current_f_val = target_f

                    gcode.append(f"G1 X{tx:.3f} Z{tz:.3f}{_b_word(pass_tilts, _pi)}{f_suffix}{s_suffix} (Op{op_idx+1} P{i+1})")
                
                # Skip the forward retract when a back pass follows — the back pass
                # starts where the forward ended (P3), so the roller flows straight in.
                _bp_meta = getattr(self, 'last_back_pass_meta', {})
                _back_follows = (global_path_idx + 1) in _bp_meta
                if len(path) > 0 and not _back_follows:
                    last_pt = path[-1]
                    ret_x_off, ret_z_off = resolve_pass_retract(op, params)  # #90 per-op
                    _ret_motion = resolve_retract_motion(op)

                    # Same helper the 3D sim uses, so the picture and the machine
                    # agree on the SHAPE. "synchronized" yields exactly one
                    # segment, i.e. the single diagonal G0 this has always been —
                    # that is what keeps existing recipes byte-identical.
                    #
                    # BOTH axis words on every leg, including the one that does
                    # not move. A recipe line carries absolute X and Z regardless
                    # (CAM_INTERFACE_SPEC section 4), so naming both costs
                    # nothing and the .nc stops depending on modal state to be
                    # read correctly.
                    for _rs in retract_segments(
                            last_pt, retract_x_offset_real(ret_x_off, ret_side),
                            ret_z_off, _ret_motion):
                        rx, rz = transform_pt([_rs[-1][0], 0, _rs[-1][2]])
                        gcode.append(f"G0 X{rx:.3f} Z{rz:.3f} "
                                     f"(Retract Op{op_idx+1} P{i+1})")

                gcode.append("")
                _fwd_last_pt = path[-1] if len(path) > 0 else None
                global_path_idx += 1

                # Back pass G-code (consumed here, not by the outer for i loop)
                if global_path_idx < total_paths and global_path_idx in _bp_meta:
                    bp_info     = _bp_meta[global_path_idx]
                    bp_path     = paths_to_use[global_path_idx]
                    bp_feed_val = float(bp_info.get("feed", val_feed))
                    gcode.append(f"(--- OP {op_idx+1}: {op_type} - BACK PASS {i+1} ---)")
                    # Same per-point contact zone as the forward pass (shared op settings):
                    # slow to the contact feed where the back pass nears the mandrel — the
                    # back pass runs outer→inner, so this catches its inner end.
                    bp_mask = self._contact_zone_mask(np.array(bp_path), center_x, contact_zone_mm,
                                                      cz_r_tool, cz_blank_thick, cz_shell_off)
                    # Tilt derives from each point's Z, so a back pass needs no
                    # special handling — the same Z always yields the same angle.
                    bp_tilts = None
                    if _tilt_kin is not None and _tilt_mgr is not None:
                        bp_tilts = self._compute_tilt_for_path(np.array(bp_path), op, _tilt_mgr,
                                                               _tilt_kin)
                        _issues = _tilt_kin.check_reachable(np.array(bp_path), bp_tilts)
                        if _issues:
                            self.last_kinematic_warnings.extend(
                                f"Op{op_idx+1} BP{i+1}: {s}" for s in _issues[:5])
                    # Only approach if the back pass start isn't already the forward end
                    # (bp_arc bow / clearance shift can move it); otherwise flow straight in.
                    if _fwd_last_pt is None or np.linalg.norm(np.array(_fwd_last_pt) - np.array(bp_path[0])) > 1e-3:
                        bs_x, bs_z = transform_pt(bp_path[0])
                        gcode.append(f"G0 X{bs_x:.3f} Z{bs_z:.3f}{_b_word(bp_tilts, 0)} (Op{op_idx+1} BP{i+1})")
                    # Base feed line (unchanged when no contact zone -> identical output).
                    gcode.append(f"G1 F{bp_feed_val:.3f}")
                    current_bp_f = bp_feed_val
                    for _bpi, bp_pt in enumerate(bp_path[1:], start=1):
                        tx, tz = transform_pt(bp_pt)
                        target_bp_f = pass_feed_contact if (bp_mask is not None and bp_mask[_bpi]) else bp_feed_val
                        f_suffix = ""
                        if abs(target_bp_f - current_bp_f) > 0.001:
                            f_suffix = f" F{target_bp_f:.3f}"
                            current_bp_f = target_bp_f
                        gcode.append(f"G1 X{tx:.3f} Z{tz:.3f}{_b_word(bp_tilts, _bpi)}{f_suffix} (Op{op_idx+1} BP{i+1})")
                    if len(bp_path) > 0:
                        bl = bp_path[-1]
                        _bp_rx_off, _bp_rz_off = resolve_pass_retract(op, params)  # #90 per-op
                        for _rs in retract_segments(
                                bl, retract_x_offset_real(_bp_rx_off, ret_side),
                                _bp_rz_off, resolve_retract_motion(op)):
                            rx, rz = transform_pt([_rs[-1][0], 0, _rs[-1][2]])
                            gcode.append(f"G0 X{rx:.3f} Z{rz:.3f} "
                                         f"(Retract Op{op_idx+1} BP{i+1})")
                    gcode.append("")
                    global_path_idx += 1

        if self.last_kinematic_warnings:
            logger.warning(f"[TILT] {len(self.last_kinematic_warnings)} kinematic reachability "
                           f"issue(s) in generated G-code; first: {self.last_kinematic_warnings[0]}")

        # Final Safety Return (Use transformed coordinates).
        # Program End defaults to Program Start, so this stays byte-identical for
        # every existing recipe. Note it goes through _xf_pt like every other
        # coordinate — unlike the footer template below, which is emitted raw.
        _end_x_cam, _end_z_cam = resolve_program_end(params)
        end_x_machine, end_z_machine = _xf_pt(_end_x_cam, _end_z_cam)
        gcode.append("(--- PROGRAM SONU GUVENLI DONUS ---)")
        gcode.append(f"G0 Z{end_z_machine:.3f}")
        gcode.append(f"G0 X{end_x_machine:.3f}")

        footer_tmpl = params.get("gcode_footer", "M5\nM30")
        gcode.extend(footer_tmpl.splitlines())
        gcode.append("%")
        return "\n".join(gcode)

    def _safe_rapid_segments(self, p_from, p_to, safe_x):
        """
        Mandrelın içinden geçmemek için rapid'i 3 adıma böler:
        1. X'i safe_x'e çek  (her iki noktanın da max X'i + margin)
        2. Z'de hareket et   (güvenli X'te)
        3. Hedef X'e yaklaş
        Eğer Z değişimi yoksa (sadece X hareketi) direkt gider.
        """
        segs = []
        threshold = 1.0  # mm

        # Safe X: her iki noktanın dışında olmalı. home_x değil, dinamik hesap.
        clearance_x = max(p_from[0], p_to[0], safe_x)

        mid1 = np.array([clearance_x, 0.0, p_from[2]])
        mid2 = np.array([clearance_x, 0.0, p_to[2]])

        # Z farkı küçükse (aynı seviyede) direkt git, 3-adıma gerek yok
        if abs(p_from[2] - p_to[2]) < threshold:
            if np.linalg.norm(p_from - p_to) > threshold:
                segs.append(np.array([p_from, p_to]))
            return segs

        if np.linalg.norm(p_from - mid1) > threshold:
            segs.append(np.array([p_from, mid1]))
        if np.linalg.norm(mid1 - mid2) > threshold:
            segs.append(np.array([mid1, mid2]))
        if np.linalg.norm(mid2 - p_to) > threshold:
            segs.append(np.array([mid2, p_to]))

        if not segs and np.linalg.norm(p_from - p_to) > threshold:
            segs.append(np.array([p_from, p_to]))

        return segs

    def _generate_spline(self, p1, p2, p3, num_points=100):
        try:
            arr = TColgp_Array1OfPnt(1,3)
            arr.SetValue(1, p1); arr.SetValue(2, p2); arr.SetValue(3, p3)
            bs = GeomAPI_PointsToBSpline(arr)
            if not bs.IsDone(): return np.array([])
            
            curve = bs.Curve()
            pts = []
            
            # Use dynamic resolution
            if num_points < 10: num_points = 10
            
            for t in np.linspace(curve.FirstParameter(), curve.LastParameter(), num_points):
                p = curve.Value(t)
                pts.append([p.X(), p.Y(), p.Z()])
            return np.array(pts)
        except Exception as e:
            logger.error(f"Spline generation failed: {e}")
            return np.array([])

    def _apply_rotation(self, points, deg, pivot_point):
        rad = math.radians(deg)
        trsf = gp_Trsf()
        axis = gp_Ax1(pivot_point, gp_Dir(0, 1, 0))
        trsf.SetRotation(axis, rad)
        new_pts = []
        for p in points:
            gp = gp_Pnt(p[0], p[1], p[2]).Transformed(trsf)
            new_pts.append([gp.X(), gp.Y(), gp.Z()])
        return np.array(new_pts)

    # -----------------------------------------------------------------------
    # PLC MODE HELPERS
    # -----------------------------------------------------------------------

    def _rdp_decimate(self, points, tolerance):
        """
        Ramer-Douglas-Peucker (RDP) path decimation.
        Returns the indices of the points to keep from `points` (numpy Nx3 array).
        `tolerance` is the maximum allowed perpendicular deviation in mm.

        The distances for one segment are ONE numpy expression rather than a
        Python loop over its points, and `np.argmax` picks the first maximum
        exactly as `d > max_dist` did.

        NOT BIT-IDENTICAL TO THE SCALAR VERSION, and the difference is worth
        knowing before you chase it. A row-wise `@` and `norm(..., axis=1)`
        accumulate in a different order from per-point `np.dot` / `norm`, so the
        distances differ in the last bit or two (~1e-14 mm). That only ever shows
        when two candidate points are EXACTLY tied for furthest — which happens
        on the densely sampled, near-straight approach arm, where consecutive
        samples sit symmetrically about the chord — and then the two versions
        keep different members of the tie.

        Measured over 294 real path/tolerance combinations (2026-08-30):

            index lists differ  :  9  (3.1%)
            POINT COUNT differs :  0     <- the PLC line budget is unaffected
            max-deviation gap   :  0.000e+00 mm

        So the simplified path is equally accurate to the bit, and the auto-tune
        (which steers on line count) cannot see the change at all. Only the
        identity of one interchangeable point moves. `_test_decimation.py` pins
        exactly that against `_rdp_decimate_scalar` below.

        WHY: this is the hottest function in the program. It ran ~409k scalar
        `np.linalg.norm` calls per PLC auto-tune fit, which was 87% of a 4.9 s
        freeze on the Tk main thread (measured 2026-08-30, 15-pass recipe).
        """
        pts = np.asarray(points, dtype=float)
        n = len(pts)
        if n <= 2:
            return list(range(n))

        kept = {0, n - 1}
        stack = [(0, n - 1)]
        while stack:
            start, end = stack.pop()
            if end - start <= 1:
                continue
            seg_vec = pts[end] - pts[start]
            seg_len = np.linalg.norm(seg_vec)
            inner = pts[start + 1:end]
            if seg_len < 1e-9:
                # Degenerate segment — distance from the start point, as before.
                d = np.linalg.norm(inner - pts[start], axis=1)
            else:
                t = (inner - pts[start]) @ seg_vec / (seg_len * seg_len)
                proj = pts[start] + t[:, None] * seg_vec
                d = np.linalg.norm(inner - proj, axis=1)
            k = int(np.argmax(d))          # first maximum, like `d > max_dist`
            if d[k] > tolerance:
                max_idx = start + 1 + k
                kept.add(max_idx)
                stack.append((start, max_idx))
                stack.append((max_idx, end))
        return sorted(kept)

    def _rdp_decimate_scalar(self, points, tolerance):
        """The pre-2026-08-30 point-at-a-time RDP, kept ONLY as the reference the
        vectorised one is tested against. Not called in normal operation — if you
        are optimising `_rdp_decimate`, `_test_decimation.py` compares the two on
        real paths, which is cheaper than arguing about floating point."""
        if len(points) <= 2:
            return list(range(len(points)))

        kept = {0, len(points) - 1}
        stack = [(0, len(points) - 1)]
        while stack:
            start, end = stack.pop()
            if end - start <= 1:
                continue
            seg_vec = points[end] - points[start]
            seg_len = np.linalg.norm(seg_vec)
            max_dist = 0.0
            max_idx = start + 1
            for i in range(start + 1, end):
                if seg_len < 1e-9:
                    d = np.linalg.norm(points[i] - points[start])
                else:
                    t = np.dot(points[i] - points[start], seg_vec) / (seg_len * seg_len)
                    proj = points[start] + t * seg_vec
                    d = np.linalg.norm(points[i] - proj)
                if d > max_dist:
                    max_dist = d
                    max_idx = i
            if max_dist > tolerance:
                kept.add(max_idx)
                stack.append((start, max_idx))
                stack.append((max_idx, end))
        return sorted(kept)

    def _thin_evenly(self, pts, n_max):
        """Reduce a point run to at most n_max points, spaced evenly by ARC LENGTH
        (not by index), always keeping the first and last.

        Even-by-index would bunch the survivors wherever RDP happened to keep a
        cluster; even-by-arc-length keeps the chord errors uniform around the
        fillet, which is the whole point of capping it.

        n_max < 2 is treated as 2 (a section cannot be shorter than its endpoints).
        Returns the input unchanged when it is already short enough.
        """
        pts = np.asarray(pts, dtype=float)
        n_max = max(2, int(n_max))
        if len(pts) <= n_max:
            return pts

        seg = np.linalg.norm(np.diff(pts[:, [0, 2]], axis=0), axis=1)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        total = cum[-1]
        if total <= 1e-9:                      # degenerate run — fall back to index
            idx = np.unique(np.linspace(0, len(pts) - 1, n_max).astype(int))
            return pts[idx]

        targets = np.linspace(0.0, total, n_max)
        idx = np.unique(np.abs(cum[None, :] - targets[:, None]).argmin(axis=1))
        idx[0] = 0
        idx[-1] = len(pts) - 1
        return pts[np.unique(idx)]

    @staticmethod
    def _total_turn_deg(pts):
        """Sum of the direction changes along a polyline, in degrees.

        A shape fingerprint that is blind to point COUNT: decimating a straight
        run leaves it at 0, while dropping a corner removes that corner's angle
        outright. That is what makes it the right measure for "did the cap eat a
        break" — #102.
        """
        d = np.diff(np.asarray(pts, dtype=float), axis=0)
        n = np.linalg.norm(d, axis=1)
        d = d[n > 1e-9] / n[n > 1e-9][:, None]
        if len(d) < 2:
            return 0.0
        dots = np.clip(np.einsum("ij,ij->i", d[:-1], d[1:]), -1.0, 1.0)
        return float(np.degrees(np.arccos(dots)).sum())

    def _decimate_path_for_plc(self, path, tolerance, center_x,
                               approach_end_idx=None,
                               arc_end_idx=None,
                               exit_tolerance=None,
                               max_fillet_points=None,
                               max_exit_points=None,
                               exit_verbatim=False):
        """
        Decimates a toolpath for PLC point-to-point output.

        The point closest to the mandrel (minimum X distance from center_x)
        is always kept as a critical contact point — this is where the roller
        presses hardest and the geometry is most sensitive.

        Structural split parameters (all optional, for linear_approach passes):

          approach_end_idx : index of T1 (end of straight approach arm).
            The approach arm [0..T1] is kept verbatim as 2 pts — it is a
            straight line and needs no RDP. Without this, the long ap_start→P2
            chord dilutes fillet deviations and over-decimates the forward pass.

          arc_end_idx : index of T2 (end of P2 fillet arc, start of exit curve).
            When provided together with approach_end_idx, the path is split into
            three independent RDP regions:
              1. approach  [ap_start..T1]  → kept verbatim (2 pts)
              2. fillet    [T1..T2]        → RDP with `tolerance`
              3. exit      [T2..P3]        → RDP with `exit_tolerance`
            This gives the exit curve its own short T2→P3 chord so its
            curvature is evaluated correctly — without this, the exit sits in
            the same RDP half as the fillet and the long chord from the contact
            point to P3 can make a real Bézier exit curve look nearly straight.

          exit_tolerance : RDP tolerance used only for the exit section [T2..P3].
            Falls back to `tolerance` when None. Setting it higher than
            `tolerance` produces fewer exit points while keeping the fillet
            at full accuracy; setting it lower forces more exit detail.

          max_fillet_points : hard cap on how many points the P2 fillet section
            [T1..T2] may keep (TODO #99). Applied AFTER its RDP pass, thinned
            evenly by arc length with T1/T2 always retained. None/0 = no cap.
            Only meaningful when the three-section split is active (there is no
            isolated fillet otherwise). The machine decelerates to a stop at
            every point, so a dense fillet runs slow and rough; this trades
            corner accuracy for motion smoothness. The clearance check that
            decides whether a given cap is allowed lives in `decimate_all_paths`
            — this function only applies what it is told.

          max_exit_points : #101 (user 2026-08-27), the exit-leg twin of
            max_fillet_points. Caps how many points the P2→P3 leg may spend in
            the recipe, whichever shape produced it — exit_bow, exit_arc_angle
            or the exit_mid curl all land in this section, and a bowed exit was
            measured at 8 recipe points against 1 for a straight one. Same
            safety rule: `decimate_all_paths` decides whether the cap is allowed,
            this function only applies what it is told. Never applied to a
            hand-drawn tail (D22) — see exit_verbatim.

          exit_verbatim : #100. The exit section is a hand-drawn straight-line
            tail, so it is kept EXACTLY as-is. RDP would drop a collinear
            waypoint — no change in shape, but the per-point feed step riding on
            that waypoint would go with it, and the operator would find fewer
            points running than the table shows him.

        Returns a numpy array of the retained points.
        """
        pts = np.array(path)
        if len(pts) <= 2:
            return pts

        _exit_tol = exit_tolerance if exit_tolerance is not None else tolerance

        _has_app = approach_end_idx is not None and 0 < approach_end_idx < len(pts) - 1
        _has_arc = (arc_end_idx is not None and _has_app
                    and arc_end_idx > approach_end_idx
                    and arc_end_idx < len(pts) - 1)

        if _has_app and _has_arc:
            # Three-section split: approach verbatim, fillet and exit each get
            # their own RDP call with the correct short chord.
            approach_part = pts[:approach_end_idx + 1]              # [ap_start, T1]
            fillet_part   = pts[approach_end_idx : arc_end_idx + 1] # [T1..T2]
            exit_part     = pts[arc_end_idx:]                        # [T2..P3]
            dec_fillet = self._decimate_path_for_plc(fillet_part, tolerance, center_x)
            if max_fillet_points:
                # #99: cap the fillet AFTER RDP — RDP decides which points matter,
                # the cap decides how many the machine is willing to stop at.
                dec_fillet = self._thin_evenly(dec_fillet, max_fillet_points)
            # #100 straight mode: the exit section IS the operator's point list.
            # Decimating it would drop points he can see in the table (and the
            # per-point feeds riding on them), which is the whole feature.
            dec_exit = (exit_part if exit_verbatim
                        else self._decimate_path_for_plc(exit_part, _exit_tol, center_x))
            if max_exit_points and not exit_verbatim:
                # #101, same reasoning as the fillet cap above: RDP decides which
                # points carry the shape, the cap decides how many stops the
                # machine is willing to make for it. D22 — never a hand-drawn tail.
                dec_exit = self._thin_evenly(dec_exit, max_exit_points)
            # Stitch: approach_part ends with T1, dec_fillet starts with T1 → drop one.
            # dec_fillet ends with T2, dec_exit starts with T2 → drop one.
            result = np.vstack([approach_part[:-1], dec_fillet])
            if len(dec_exit) > 1:
                result = np.vstack([result, dec_exit[1:]])
            return result

        if _has_app:
            # Two-section split: approach verbatim, rest with RDP.
            approach_part = pts[:approach_end_idx + 1]
            curve_part    = pts[approach_end_idx:]
            if exit_verbatim:
                # There is no isolated fillet section here (T1 == T2, i.e.
                # p2_radius = 0), so the whole curve part IS the hand-drawn
                # tail. Keep it exactly — same reason as the three-section case.
                return np.vstack([approach_part[:-1], curve_part])
            dec_curve = self._decimate_path_for_plc(curve_part, tolerance, center_x)
            if max_exit_points:
                # No isolated fillet here either, so this curve IS the exit leg.
                dec_curve = self._thin_evenly(dec_curve, max_exit_points)
            return np.vstack([approach_part[:-1], dec_curve])

        # --- 1. Find critical (closest-to-mandrel) point ---
        x_distances = np.abs(pts[:, 0] - center_x)
        critical_idx = int(np.argmin(x_distances))

        # --- 2. Split path at critical point and decimate each half ---
        half1 = pts[:critical_idx + 1]
        half2 = pts[critical_idx:]

        keep1 = self._rdp_decimate(half1, tolerance)
        keep2 = self._rdp_decimate(half2, tolerance)

        # Map local half-indices back to global indices, avoiding duplicate at split
        result_pts = list(half1[keep1])
        for local_idx in keep2:
            if local_idx == 0:
                continue  # already included as last of half1
            result_pts.append(half2[local_idx])

        return np.array(result_pts)

    def decimate_all_paths(self, tolerance, exit_tolerance, center_x, params=None):
        """Return decimated copies of last_calculated_paths using the same
        per-path structural split (approach / fillet / exit) generate_gcode uses.
        Read-only — does not mutate the stored paths.

        When `params` is supplied, the two per-op point caps are applied on top —
        `p2_radius_max_points` on the P2 corner (#99) and `exit_max_points` on the
        P2→P3 leg (#101) — but only where they cost no clearance. Omitting
        `params` disables both, so every existing caller keeps its exact previous
        behaviour.

        The caps are gated INDEPENDENTLY: a fillet cap that has to be refused must
        not take a perfectly safe exit cap down with it. Each is measured against
        the same baseline (below), and an accepted cap stays applied while the
        next one is tested.

        SAFETY (the reason the cap lives here and not in `_decimate_path_for_plc`):
        fewer points means longer chords, and a chord across a convex fillet cuts
        the corner even when both of its endpoints are clear. So each capped path
        is measured — with the same metric the auto-tune guard uses — against the
        UNCAPPED decimation of the same pass: the program that would ship if the
        cap were not set. If the cap makes clearance worse than that, it is
        DROPPED and the uncapped decimation is kept; the operator is told which
        passes could not honour their cap via `last_point_cap_warnings`.
        """
        self.last_point_cap_warnings = []
        self.last_break_flatten_warnings = []      # #102
        out = []
        for _pi, _p in enumerate(self.last_calculated_paths):
            _split   = self.last_render_split_idx.get(_pi)
            # A reverse pass is stored back-to-front and its split index is
            # dropped, so it used to arrive here with no structure at all: one
            # RDP region over the whole path, and BOTH point caps dead
            # (`_cap_of` returns 0 on a missing split). exit_max_points simply
            # did nothing on a reverse pass — user, 2026-08-30: it should behave
            # like a forward one.
            #
            # Decimated REVERSED with the forward indices, then flipped back.
            # Feeding the mirrored pair to the splitter would swap the roles of
            # the arm and the exit leg — it slices `pts[:approach_end+1]` as the
            # arm and `pts[arc_end:]` as the exit, which on a back-to-front array
            # is exactly the wrong way round. RDP and `_thin_evenly` are both
            # symmetric (endpoints pinned, selection by deviation / arc length),
            # so reversing input reverses output and nothing else.
            _rev_flip = False
            if _split is None:
                _rv = getattr(self, "last_reverse_split_idx", {}).get(_pi)
                if _rv is not None:
                    _p = np.asarray(_p, dtype=float)[::-1]
                    _n = len(_p)
                    _split = (_n - 1 - _rv[1], _n - 1 - _rv[0])
                    _rev_flip = True
            _app_end = _split[0] if _split is not None else None
            _arc_end = _split[1] if _split is not None else None
            _verb = _pi in getattr(self, "last_exit_verbatim", set())
            _plain = self._decimate_path_for_plc(_p, tolerance, center_x,
                                                 approach_end_idx=_app_end,
                                                 arc_end_idx=_arc_end,
                                                 exit_tolerance=exit_tolerance,
                                                 exit_verbatim=_verb)

            _op = self._path_op_map[_pi] if _pi < len(self._path_op_map) else None

            def _cap_of(key, _o=_op, _s=_split):
                if params is None or _o is None or _s is None:
                    return 0
                try:
                    _raw = _o.get(key, None)
                    return 0 if _raw in (None, "") else int(float(_raw))
                except (TypeError, ValueError):
                    return 0

            _fill_cap = _cap_of("p2_radius_max_points")     # #99, the P2 corner
            _exit_cap = _cap_of("exit_max_points")          # #101, the P2→P3 leg
            if _fill_cap <= 0 and _exit_cap <= 0:
                out.append(_plain[::-1] if _rev_flip else _plain)
                continue

            # The two caps are judged INDEPENDENTLY. Testing them only together
            # would let a refused fillet cap throw away a perfectly safe exit cap
            # (and vice versa), which is exactly the silent "I set it and nothing
            # happened" the warning exists to prevent. Applied fillet-first so the
            # accepted result is what the exit cap is then measured against.
            _best = _plain
            _accepted = {}          # caps that already passed the clearance gate
            # BASELINE = the decimation that would ship if no cap were set, NOT the
            # full-resolution path. Measuring against full resolution charges the cap
            # for clearance RDP gave up on its own — and because the metric spans the
            # WHOLE path, a fillet that RDP chorded would veto a cap on the exit leg
            # that costs nothing at all (measured: capped 1.9955 vs plain 1.9955,
            # refused only because full resolution was 2.0000). The invariant that
            # matters is "the cap never makes the exported program worse than not
            # using it", which is what this docstring always claimed.
            _floor = self._path_min_clearance(_plain, _op, params)
            for _kind, _cap, _kw in (("fillet", _fill_cap, "max_fillet_points"),
                                     ("exit", _exit_cap, "max_exit_points")):
                if _cap <= 0:
                    continue
                _try = self._decimate_path_for_plc(
                    _p, tolerance, center_x,
                    approach_end_idx=_app_end, arc_end_idx=_arc_end,
                    exit_tolerance=exit_tolerance, exit_verbatim=_verb,
                    **{**_accepted, _kw: _cap})
                if len(_try) >= len(_best):
                    continue                    # this cap changed nothing
                _got = self._path_min_clearance(_try, _op, params)
                if _got >= _floor - 1e-6:
                    # #102: the gate above only refuses a cap that costs
                    # CLEARANCE. Blunting a break rotates the tail AWAY from the
                    # part, so it passes the gate while quietly deleting the
                    # shape the operator typed. Measured: 3 breaks of 10° under
                    # a cap of 3 lost 5°, under a cap of 2 lost 15°, in silence.
                    # The cap still wins (user 2026-08-28: "leave it, just
                    # warn") — but it says so now.
                    _n_brk = getattr(self, "last_exit_break_counts", {}).get(_pi, 0)
                    if _kind == "exit" and _n_brk:
                        _lost = self._total_turn_deg(_best) - self._total_turn_deg(_try)
                        if _lost > 0.5:
                            self.last_break_flatten_warnings.append({
                                "path_index": _pi,
                                "op_name": (_op.get("name") or _op.get("type", "?")) if _op else "?",
                                "cap": _cap,
                                "n_breaks": int(_n_brk),
                                "lost_deg": float(_lost),
                            })
                            logger.info(
                                f"[#102] Exit cap {_cap} on path {_pi} "
                                f"({self.last_break_flatten_warnings[-1]['op_name']}) "
                                f"blunted {_n_brk} break(s): {_lost:.1f}° of bend lost. "
                                f"Cap kept (clearance is unaffected).")
                    _best = _try
                    _accepted[_kw] = _cap
                else:
                    self.last_point_cap_warnings.append({
                        "path_index": _pi,
                        "section": _kind,
                        "op_name": (_op.get("name") or _op.get("type", "?")) if _op else "?",
                        "requested": _cap,
                        "kept": int(len(_best)),
                        "clearance": float(_got),
                        "floor": float(_floor),
                    })
                    logger.info(
                        f"[#{'99' if _kind == 'fillet' else '101'}] {_kind.capitalize()} "
                        f"cap {_cap} REFUSED on path {_pi} "
                        f"({self.last_point_cap_warnings[-1]['op_name']}): clearance would "
                        f"drop {_floor:.3f} → {_got:.3f} mm. Uncapped decimation kept.")
            # Back to the order the rest of the program expects (see _rev_flip).
            out.append(_best[::-1] if _rev_flip else _best)
        return out

    def _straight_line_flatness_dev(self, mandrel_mgr, start_z, end_z, shell_offset=0.0):
        """Max signed radial deviation (mm) of the mandrel profile between start_z and
        end_z from the straight chord joining the two endpoints — how far a
        straight-line finishing pass's 2-point line drifts off the real surface.

        Sign: + = surface bulges TOWARD the tool (mid-line clearance shrinks → gouge
        risk); - = surface dips AWAY (clearance grows → band under-finished). Returns
        0.0 for a perfectly conical/cylindrical span (the mode's valid precondition),
        and None when unmeasurable (zero span, or radii unavailable). Pure/read-only:
        no toolpath or state is touched, so it is safe to unit-test directly.
        """
        s = float(start_z); e = float(end_z)
        if abs(e - s) < 1e-3:
            return None
        r_s = mandrel_mgr.get_radius_fast(s)
        r_e = mandrel_mgr.get_radius_fast(e)
        if r_s is None or r_e is None:
            return None
        r_s += shell_offset; r_e += shell_offset
        n = max(8, min(65, int(abs(e - s)) + 1))
        dev_ext = 0.0
        for k in range(1, n):  # interior samples; the two endpoints are 0 by construction
            t = k / n
            z = s + t * (e - s)
            r = mandrel_mgr.get_radius_fast(z)
            if r is None:
                continue
            r += shell_offset
            r_chord = r_s + (r_e - r_s) * t
            dev = r - r_chord
            if abs(dev) > abs(dev_ext):
                dev_ext = dev
        return dev_ext

    def measure_min_clearance(self, paths, params, sample_step=0.5):
        """Minimum roller-to-part clearance (mm) along the STRAIGHT segments of the
        given tool paths — the actual point-to-point motion, not just the retained
        vertices. This is what catches a decimated chord 'cutting the corner'
        toward the mandrel between two kept points.

        Mirrors the metric used during path creation:
            clearance = radial_dist_from_center - (mandrel_R + blank + shell + r_tool)

        Returns +inf when it cannot be measured (no mandrel loaded / empty paths).
        """
        mgr = getattr(self, "last_mandrel_mgr", None)
        if mgr is None or not paths:
            return float('inf')
        min_cl = float('inf')
        for pi, path in enumerate(paths):
            op = self._path_op_map[pi] if pi < len(self._path_op_map) else None
            c = self._path_min_clearance(path, op, params, sample_step)
            if c < min_cl:
                min_cl = c
        return min_cl

    def _path_min_clearance(self, path, op, params, sample_step=0.5):
        """Minimum roller-to-part clearance along ONE path, sampled along its
        straight segments. The single implementation of the metric — both
        `measure_min_clearance` (whole-program, auto-tune guard) and the #99
        per-pass fillet-cap check go through here, so the two can never drift.

        Returns +inf when it cannot be measured (no mandrel / empty path).
        """
        mgr = getattr(self, "last_mandrel_mgr", None)
        pts = np.asarray(path, dtype=float)
        if mgr is None or len(pts) == 0:
            return float('inf')

        center_x = float(params.get("mandrel_pos_x_offset", 0.0))
        blank = float(params.get("final_part_thickness_on_mandrel", 2.0))
        shell = float(params.get("shell_thickness", 0.0))
        step = max(0.1, float(sample_step))
        r_tool = float(op.get("r_tool", 25.0)) if op else 25.0
        base = blank + shell + r_tool

        def _cl_at(x, z):
            m_r = mgr.get_radius_fast(z)
            if m_r is None:
                return None
            return abs(x - center_x) - (m_r + base)

        min_cl = float('inf')
        if len(pts) == 1:
            c = _cl_at(pts[0][0], pts[0][2])
            return c if c is not None else float('inf')

        for k in range(len(pts) - 1):
            a = pts[k]; b = pts[k + 1]
            seg = math.hypot(b[0] - a[0], b[2] - a[2])
            n = max(1, int(seg / step))
            for s in range(n + 1):
                t = s / n
                c = _cl_at(a[0] + t * (b[0] - a[0]), a[2] + t * (b[2] - a[2]))
                if c is not None and c < min_cl:
                    min_cl = c
        return min_cl

    def calculate_estimated_time(self, params):
        ops = self._ensure_ops_dict(params)
        total_time = 0.0
        global_path_idx = 0
        paths = self.last_calculated_paths
        
        for op in ops:
            if not op.get("enabled", True): continue
            count = int(op.get("count", 1))
            
            s_mode = resolve_speed_mode(op)
            f_mode = op.get("feed_mode", "mm_min")
            def_speed = params.get("surface_speed_m_min", 200)
            def_feed = params.get("feed_rate_mm_min", 300)
            val_speed = float(op.get("speed", def_speed))
            val_feed = float(op.get("feed", def_feed))
            
            zones = op.get("zones", [])
            
            for _ in range(count):
                if global_path_idx >= len(paths): break
                path = paths[global_path_idx]
                
                if len(path) > 1:
                    for j in range(len(path) - 1):
                        p1 = path[j]
                        p2 = path[j+1]
                        
                        dx = p2[0]-p1[0]; dy = p2[1]-p1[1]; dz = p2[2]-p1[2]
                        dist = math.sqrt(dx*dx + dy*dy + dz*dz)
                        if dist <= 0.0001: continue
                        
                        cur_s = val_speed
                        cur_f = val_feed
                        raw_z = p1[2]
                        
                        for zdata in zones:
                             try:
                                 zs = float(zdata.get("start_z", 0)); ze = float(zdata.get("end_z", 0))
                                 if min(zs, ze) <= raw_z <= max(zs, ze):
                                      cur_s = float(zdata.get("speed", val_speed))
                                      cur_f = float(zdata.get("feed", val_feed))
                                      break
                             except (TypeError, ValueError, KeyError): pass
                        
                        seg_time_min = 0.0
                        
                        if f_mode == "mm_min":
                            if cur_f > 0: seg_time_min = dist / cur_f
                        else:
                            rpm = cur_s
                            if s_mode == "CSS":
                                avg_x = abs((p1[0]+p2[0])/2.0)
                                if avg_x < 1.0: avg_x = 1.0
                                dia = 2.0 * avg_x
                                rpm = (cur_s * 1000.0) / (math.pi * dia)
                                max_rpm = float(params.get("spindle_speed_limit_rpm", 3000))
                                rpm = min(rpm, max_rpm)
                            
                            if rpm > 0 and cur_f > 0:
                                f_min = cur_f * rpm
                                seg_time_min = dist / f_min
                        
                        total_time += (seg_time_min * 60.0) 

                global_path_idx += 1
                
        return total_time

    def _create_sweeping_pass(self, start_z, end_z, mandrel_mgr, center_x, r_tool, blank_thick, finish_allowance, shell_offset, pass_name, t_list, p_list, c_list, d_list, safety_clearance=0.0):
        # Sweeping / Ironing Pass: Traces the Mandrel Surface directly
        path_pts = []
        projs = []
        devs = []

        dist = abs(end_z - start_z)
        if dist < 1.0: return

        step_size = 1.0 # 1mm resolution
        num_steps = int(dist / step_size)
        step_dir = -1.0 if start_z > end_z else 1.0

        current_z = start_z

        for _ in range(num_steps + 1):
            if (step_dir > 0 and current_z > end_z) or (step_dir < 0 and current_z < end_z):
                current_z = end_z

            m_rad = mandrel_mgr.get_radius_fast(current_z) + shell_offset
            nx, nz = mandrel_mgr.get_normal_at_z(current_z)

            total_off = r_tool + blank_thick + safety_clearance + finish_allowance

            rx = center_x + m_rad + (nx * total_off)
            rz = current_z + (nz * total_off)
            
            path_pts.append([rx, 0.0, rz])
            projs.append([center_x + m_rad, 0.0, current_z])
            devs.append(0.0) 
            
            current_z += (step_size * step_dir)
            if abs(current_z - end_z) < 0.1: break
            
        t_list.append(np.array(path_pts, dtype=float))
        p_list.append(np.array(projs,    dtype=float))
        c_list.append(np.array([],       dtype=float))
        d_list.append(np.array(devs,     dtype=float))