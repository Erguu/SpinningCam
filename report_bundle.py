# -*- coding: utf-8 -*-
"""Collect a troubleshooting bundle the operator can hand to the developers.

WHY THIS EXISTS

"The program is behaving strangely" arrives as a sentence, and answering it takes
a round of questions that costs a day each way across a time zone. Everything
needed to reproduce the complaint already sits on the operator's disk — the
program, the machine profile, the tool calibration, the log — but only somebody
who knows the layout can find it. This module gathers it into one .zip.

SIZES ARE SMALL. A typical bundle measured on the development machine:

    program.ssp        17 KB      the program on screen (unsaved edits included)
    spinning_cam.log   70 KB      this session's log
    settings.json      15 KB      app state
    machines/*.json   2.4 KB      the machine profile
    tools.json        2.5 KB      roller calibration
    program.nc        varies      what would go to the machine

That is well under 100 KB, roughly 25 KB zipped — small enough for any chat app
or mail. The mandrel STEP and the tool_geometry folder are the only items that
can be large, and both are off by default.

CONSENT IS THE POINT. Nothing here runs on its own. The dialog lists every item
with its real size, previews any of them on request, and the operator ticks what
leaves their machine. ``settings.json`` does contain their local folder paths;
it is included because a wrong path is a common cause of "it stopped working",
and it is one untick away.

WHAT IS DELIBERATELY NOT COLLECTIBLE

The license file. It is the customer's key and it has no diagnostic value. The
report carries the machine fingerprint instead, which is what identifies them in
the license records and cannot be used to run anything.

EVERY COLLECTOR SWALLOWS ITS OWN ERRORS. A missing STEP file must not stop a
report from being sent — that report is likely being sent *because* something is
broken. A collector that fails returns an item marked with a reason, the dialog
greys the row out, and the rest of the bundle is built.
"""
import io
import os
import platform
import sys
import tempfile
import time
import zipfile

from logger_config import logger
from version import APP_VERSION

# --- item keys -------------------------------------------------------------
PROGRAM = "program"
LOG = "log"
SETTINGS = "settings"
MACHINE = "machine"
TOOLS = "tools"
GCODE = "gcode"
STEP = "step"
TOOL_GEOMETRY = "tool_geometry"

# The order the dialog lists them in: most diagnostically valuable first, so an
# operator who reads only the top of the list still sends the useful things.
ITEM_ORDER = [PROGRAM, LOG, SETTINGS, MACHINE, TOOLS, GCODE, STEP, TOOL_GEOMETRY]

# Ticked when the dialog opens. The two heavy, rarely-needed items are not.
DEFAULT_ON = frozenset({PROGRAM, LOG, SETTINGS, MACHINE, TOOLS, GCODE})

# report.txt is not in ITEM_ORDER and has no checkbox: a bundle with no note and
# no version number is a bundle nobody can act on.
SUMMARY_NAME = "report.txt"

_MAX_MEMBER_BYTES = 64 * 1024 * 1024   # a runaway log must not exhaust memory


class Item(object):
    """One tickable row. ``members`` is [(name_inside_zip, bytes)]."""

    __slots__ = ("key", "members", "error")

    def __init__(self, key, members=None, error=""):
        self.key = key
        self.members = list(members or [])
        self.error = error

    @property
    def size(self):
        return sum(len(d) for _, d in self.members)

    @property
    def available(self):
        return bool(self.members) and not self.error

    def __repr__(self):                                      # pragma: no cover
        return "<Item %s n=%d size=%d err=%r>" % (
            self.key, len(self.members), self.size, self.error)


# --- helpers ---------------------------------------------------------------

def _read(path):
    """Bytes of `path`, or None. Capped so a pathological file cannot blow up
    the process on a machine we are not sitting in front of."""
    try:
        if os.path.getsize(path) > _MAX_MEMBER_BYTES:
            logger.warning("report: %s exceeds %d bytes, skipped",
                           path, _MAX_MEMBER_BYTES)
            return None
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        logger.debug("report: cannot read %s: %s", path, e)
        return None


def _files_item(key, pairs):
    """Item from [(arcname, abspath)], skipping the ones that are not there."""
    members = []
    for arc, path in pairs:
        if path and os.path.isfile(path):
            data = _read(path)
            if data is not None:
                members.append((arc, data))
    if not members:
        return Item(key, error="not_found")
    return Item(key, members)


def human_size(n):
    """'17 KB'. Deliberately coarse — the operator needs a sense of scale, not
    a byte count."""
    if n is None:
        return "?"
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.0f KB" % (n / 1024.0)
    return "%.1f MB" % (n / (1024.0 * 1024.0))


def _base(app):
    try:
        return app.get_base_path()
    except Exception:
        return os.path.dirname(os.path.abspath(__file__))


# --- collectors ------------------------------------------------------------
# Each one takes the app and returns an Item. None of them raise.

def collect_program(app):
    """The program as it is on screen right now.

    Saved through ``app.save_project`` rather than re-serialised here, so the
    bundle always contains exactly what File ▸ Save Project would have written.
    Unsaved edits are included on purpose: the operator's complaint is about the
    state in front of them, not the state they last saved.
    """
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".ssp")
        os.close(fd)
        if not app.save_project(tmp):
            return Item(PROGRAM, error="save_failed")
        data = _read(tmp)
        if data is None:
            return Item(PROGRAM, error="save_failed")
        return Item(PROGRAM, [("program.ssp", data)])
    except Exception as e:
        logger.debug("report: program collect failed: %s", e)
        return Item(PROGRAM, error="save_failed")
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass


def collect_log(app):
    """This session's log, plus the previous session's if it was kept.

    The previous one matters more often than the current one: an operator who
    hits a fault, closes the program and reopens it to send a report has already
    replaced the log that held the fault. See ``logger_config.setup_logger``.
    """
    b = _base(app)
    return _files_item(LOG, [
        ("spinning_cam.log", os.path.join(b, "spinning_cam.log")),
        ("spinning_cam.prev.log", os.path.join(b, "spinning_cam.prev.log")),
    ])


def collect_settings(app):
    return _files_item(SETTINGS, [
        ("settings.json", os.path.join(_base(app), "settings.json"))])


def collect_machine(app):
    """The active machine profile, and the factory template beside it.

    Both, because the interesting question is usually what was *changed* from
    the template — an offset or a workspace limit edited months ago and
    forgotten is a recurring cause of "it used to work".
    """
    mid = ""
    try:
        mid = str(app.params.get("machine_id", "") or "").strip()
    except Exception:
        pass
    if not mid:
        return Item(MACHINE, error="no_machine_id")
    mdir = os.path.join(_base(app), "machines")
    return _files_item(MACHINE, [
        ("machines/%s.json" % mid, os.path.join(mdir, "%s.json" % mid)),
        ("machines/%s.default.json" % mid,
         os.path.join(mdir, "%s.default.json" % mid)),
    ])


def collect_tools(app):
    return _files_item(TOOLS, [
        ("tools.json", os.path.join(_base(app), "tools.json"))])


def collect_gcode(app):
    """The .nc the current program would export.

    Generated here rather than read from disk: the last exported file may be
    from a different program, and a stale .nc is worse than none. Full
    resolution, matching ``SpinningApp.save_gcode`` — PLC decimation belongs to
    the recipe path, not to this file.
    """
    try:
        if not getattr(app.path_gen, "last_calculated_paths", None):
            return Item(GCODE, error="no_paths")
        p = dict(app.params)
        p["plc_mode"] = False
        code = app.path_gen.generate_gcode(params=p)
        if not code:
            return Item(GCODE, error="empty")
        return Item(GCODE, [("program.nc", code.encode("utf-8", "replace"))])
    except Exception as e:
        logger.debug("report: gcode collect failed: %s", e)
        return Item(GCODE, error="generate_failed")


def collect_step(app):
    """The mandrel model. Off by default — it is the one item that can be a few
    megabytes, and it is also the item most likely to be a customer's own part
    geometry that they would rather not hand over without thinking about it."""
    path = getattr(app, "step_file_path_global", "") or ""
    if not path:
        return Item(STEP, error="not_loaded")
    return _files_item(STEP, [("mandrel/" + os.path.basename(path), path)])


def collect_tool_geometry(app):
    """The roller STEP files. Off by default: needed only when the complaint is
    about roller reach or the 3D view of the tool."""
    gdir = os.path.join(_base(app), "tool_geometry")
    if not os.path.isdir(gdir):
        return Item(TOOL_GEOMETRY, error="not_found")
    pairs = []
    try:
        for name in sorted(os.listdir(gdir)):
            full = os.path.join(gdir, name)
            if os.path.isfile(full):
                pairs.append(("tool_geometry/" + name, full))
    except OSError as e:
        logger.debug("report: tool_geometry listing failed: %s", e)
        return Item(TOOL_GEOMETRY, error="not_found")
    return _files_item(TOOL_GEOMETRY, pairs)


_COLLECTORS = {
    PROGRAM: collect_program,
    LOG: collect_log,
    SETTINGS: collect_settings,
    MACHINE: collect_machine,
    TOOLS: collect_tools,
    GCODE: collect_gcode,
    STEP: collect_step,
    TOOL_GEOMETRY: collect_tool_geometry,
}


def collect_items(app, keys=None):
    """Every item in ``ITEM_ORDER``, collected. Never raises.

    Collected eagerly, all of it, when the dialog opens — that is what lets the
    dialog show a real size per row instead of a promise. The expensive one is
    the G-code, and it is the same work the Export button already does on a
    click, so the cost is understood.
    """
    out = []
    for key in (keys or ITEM_ORDER):
        fn = _COLLECTORS.get(key)
        if fn is None:
            continue
        try:
            out.append(fn(app))
        except Exception as e:                               # pragma: no cover
            logger.warning("report: collector %s raised: %s", key, e)
            out.append(Item(key, error="failed"))
    return out


# --- the summary -----------------------------------------------------------

def machine_fingerprint():
    """The licensing fingerprint, so a report can be matched to a customer
    without the license file travelling with it. Never raises — an unlicensed or
    non-Windows machine still gets to send a report."""
    try:
        from license_manager import get_machine_fingerprint
        return str(get_machine_fingerprint() or "unavailable")
    except Exception as e:
        logger.debug("report: fingerprint unavailable: %s", e)
        return "unavailable"


def summary_text(app, note="", items=None, when=None):
    """``report.txt`` — what a human reads first.

    Kept as plain text with the note at the top, because the note is the only
    part no tool can reconstruct.
    """
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(when))
    lines = []
    lines.append("SoftSpinner troubleshooting report")
    lines.append("=" * 60)
    lines.append("")
    lines.append("WHAT THE OPERATOR REPORTED")
    lines.append("-" * 60)
    lines.append((note or "").strip() or "(no description given)")
    lines.append("")
    lines.append("SYSTEM")
    lines.append("-" * 60)
    lines.append("Created        : %s" % stamp)
    lines.append("App version    : %s" % APP_VERSION)
    lines.append("Fingerprint    : %s" % machine_fingerprint())
    try:
        lines.append("Machine        : %s (%s)" % (
            app.params.get("machine_id", "?"),
            app.params.get("machine_name", "?")))
    except Exception:
        lines.append("Machine        : ?")
    try:
        lines.append("Language       : %s" % app.params.get("language", "?"))
    except Exception:
        pass
    lines.append("OS             : %s %s" % (platform.system(), platform.release()))
    lines.append("Python         : %s" % sys.version.split()[0])
    lines.append("Frozen exe     : %s" % bool(getattr(sys, "frozen", False)))

    lines.append("")
    lines.append("PROGRAM")
    lines.append("-" * 60)
    try:
        ops = app.params.get("operations", []) or []
        on = sum(1 for o in ops if o.get("enabled", True))
        lines.append("Operations     : %d (%d enabled)" % (len(ops), on))
        types = {}
        for o in ops:
            k = str(o.get("type", "?"))
            types[k] = types.get(k, 0) + 1
        if types:
            lines.append("By type        : %s" % ", ".join(
                "%s x%d" % (k, v) for k, v in sorted(types.items())))
    except Exception:
        lines.append("Operations     : ?")
    try:
        lines.append("Mandrel STEP   : %s" % (
            os.path.basename(getattr(app, "step_file_path_global", "") or "")
            or "(none loaded)"))
    except Exception:
        pass
    try:
        n = len(getattr(app.path_gen, "last_calculated_paths", None) or [])
        lines.append("Calculated     : %d toolpaths" % n)
    except Exception:
        pass

    lines.append("")
    lines.append("CONTENTS OF THIS BUNDLE")
    lines.append("-" * 60)
    if items:
        for it in items:
            for arc, data in it.members:
                lines.append("  %-34s %s" % (arc, human_size(len(data))))
    lines.append("  %-34s (this file)" % SUMMARY_NAME)
    lines.append("")
    return "\n".join(lines)


# --- writing ---------------------------------------------------------------

def selected_items(items, keys):
    """The available items whose key is ticked. Unavailable rows are dropped
    here rather than at the checkbox, so a stale selection cannot produce a zip
    entry that does not exist."""
    want = set(keys or ())
    return [it for it in items if it.key in want and it.available]


def total_size(items):
    return sum(it.size for it in items)


def write_bundle(zip_path, items, summary):
    """Write the .zip. Returns (n_members, uncompressed_bytes).

    Writes to a temporary file in the same folder and renames on success, so a
    failure halfway through cannot leave a half-written .zip that looks
    complete to whoever picks it up.
    """
    tmp = zip_path + ".part"
    n = 0
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(SUMMARY_NAME, summary.encode("utf-8"))
            n += 1
            for it in items:
                for arc, data in it.members:
                    zf.writestr(arc, data)
                    n += 1
        if os.path.exists(zip_path):
            os.remove(zip_path)
        os.rename(tmp, zip_path)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise
    logger.info("report bundle written: %s (%d files)", zip_path, n)
    return n, total_size(items) + len(summary.encode("utf-8"))


def default_filename(app, when=None):
    """A name that sorts by date and says who it came from, because these land
    in a folder full of other people's reports."""
    stamp = time.strftime("%Y-%m-%d_%H%M", time.localtime(when))
    mid = "unknown"
    try:
        mid = str(app.params.get("machine_id", "") or "unknown").strip() or "unknown"
    except Exception:
        pass
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in mid)
    return "SoftSpinner_report_%s_%s.zip" % (safe, stamp)


def preview_text(item, arcname=None, limit=20000):
    """Readable form of one member, for the dialog's Preview button.

    Binary members are reported as binary rather than dumped as mojibake — the
    point of the preview is for the operator to satisfy themselves about what
    they are sending, and a screen of noise does not do that.
    """
    if not item.members:
        return ""
    for arc, data in item.members:
        if arcname is None or arc == arcname:
            head = data[:limit]
            try:
                txt = head.decode("utf-8")
            except UnicodeDecodeError:
                return "(%s — binary file, %s)" % (arc, human_size(len(data)))
            if len(data) > limit:
                txt += "\n\n… (%s total, showing the first %s)" % (
                    human_size(len(data)), human_size(limit))
            return txt
    return ""
