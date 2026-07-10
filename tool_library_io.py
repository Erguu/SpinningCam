"""Portable tool-library geometry: ID-named STEP files + zip export/import.

The tool library (tools.json) is shared across machines (git pull, or a shipped
exe). To make each tool's 3D STEP geometry travel with it — instead of pointing
at a machine-specific absolute path that breaks on every other PC — geometry is
stored next to the app in ``tool_geometry/`` and named after the tool ID:

    tool_geometry/T0103.STEP

``tool_step_loader._resolve_step_path`` finds geometry by that convention first,
so a tool "just works" on any machine once its file is in the folder.

This module owns the write side of that convention:
  * ``sync_tool_geometry`` — when a tool is added/edited, copy a browsed STEP
    into ``tool_geometry/<id>`` (and rename it if the tool ID changed), then
    normalise ``step_file`` to the relative convention path.
  * ``export_library`` / ``import_library`` — bundle the whole library + its
    geometry into one ``.zip`` for sharing outside git, and read it back.
"""

import os
import json
import shutil
import zipfile

from logger_config import logger
from tool_step_loader import TOOL_GEOMETRY_DIR, _STEP_EXTS


def geometry_dir(base_dir: str) -> str:
    """Absolute path to the tool_geometry folder, created if missing."""
    d = os.path.join(base_dir, TOOL_GEOMETRY_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def find_geometry_file(base_dir: str, tool_id: str) -> str:
    """Existing tool_geometry/<id>.<ext> for this tool, or "" if none."""
    tid = str(tool_id).strip()
    if not tid or not base_dir:
        return ""
    gdir = os.path.join(base_dir, TOOL_GEOMETRY_DIR)
    for ext in _STEP_EXTS:
        cand = os.path.join(gdir, tid + ext)
        if os.path.isfile(cand):
            return cand
    return ""


def _remove_geometry(base_dir: str, tool_id: str) -> None:
    """Delete any tool_geometry/<id>.<ext> (used before replacing/renaming)."""
    existing = find_geometry_file(base_dir, tool_id)
    if existing:
        try:
            os.remove(existing)
        except OSError as e:
            logger.warning(f"tool geometry remove failed ({existing}): {e}")


def _rel_convention(found_path: str) -> str:
    """Relative, forward-slash convention path stored in tools.json."""
    return f"{TOOL_GEOMETRY_DIR}/{os.path.basename(found_path)}"


def sync_tool_geometry(base_dir: str, tool: dict, old_id: str = None) -> str:
    """Make a tool's STEP geometry portable and ID-named. Mutates ``tool``.

    1. If the tool ID changed (``old_id`` differs), rename its geometry file.
    2. If ``step_file`` points at an EXTERNAL file (absolute, or outside
       tool_geometry/), copy it to tool_geometry/<id>.<ext>.
    3. Normalise ``step_file`` to the relative convention path when a geometry
       file exists, so tools.json stays machine-independent.

    Returns a short human-readable note (for a status line), or "".
    """
    if not base_dir:
        return ""
    tid = str(tool.get("id", "")).strip()
    if not tid:
        return ""
    gdir = geometry_dir(base_dir)
    note = ""

    # 1. Rename geometry on ID change.
    old = str(old_id).strip() if old_id else ""
    if old and old != tid:
        old_path = find_geometry_file(base_dir, old)
        if old_path:
            ext = os.path.splitext(old_path)[1]
            dst = os.path.join(gdir, tid + ext)
            try:
                _remove_geometry(base_dir, tid)  # clear a stale target
                shutil.move(old_path, dst)
                note = f"{os.path.basename(old_path)} → {os.path.basename(dst)}"
            except OSError as e:
                logger.warning(f"tool geometry rename failed: {e}")

    # 2. Ingest an externally-browsed STEP file.
    src = str(tool.get("step_file", "")).strip()
    if src:
        abs_src = src if os.path.isabs(src) else os.path.normpath(os.path.join(base_dir, src))
        inside = os.path.normpath(abs_src).lower().startswith(
            os.path.normpath(gdir).lower())
        if os.path.isfile(abs_src) and not inside:
            ext = os.path.splitext(abs_src)[1] or ".STEP"
            dst = os.path.join(gdir, tid + ext)
            try:
                _remove_geometry(base_dir, tid)  # replace any existing of another ext
                shutil.copyfile(abs_src, dst)
                note = f"→ {os.path.basename(dst)}"
            except OSError as e:
                logger.warning(f"tool geometry copy failed: {e}")

    # 3. Normalise step_file to the relative convention path if a file exists.
    found = find_geometry_file(base_dir, tid)
    if found:
        tool["step_file"] = _rel_convention(found)
    return note


def export_library(base_dir: str, tools: list, zip_path: str) -> tuple:
    """Write a portable .zip = tools.json (paths normalised) + each tool's
    tool_geometry/<id>.<ext>. Returns (n_tools, n_geometry_files)."""
    import copy as _copy
    export_tools = []
    n_geom = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for tool in tools:
            t2 = _copy.deepcopy(tool)
            tid = str(t2.get("id", "")).strip()
            gf = find_geometry_file(base_dir, tid) if tid else ""
            if gf:
                arc = f"{TOOL_GEOMETRY_DIR}/{os.path.basename(gf)}"
                zf.write(gf, arc)
                t2["step_file"] = arc
                n_geom += 1
            else:
                # No geometry on this machine → drop the machine-specific path so
                # the bundle stays portable (the entry still carries r_tool etc.).
                t2["step_file"] = ""
            export_tools.append(t2)
        zf.writestr("tools.json",
                    json.dumps(export_tools, indent=4, ensure_ascii=False))
    return len(export_tools), n_geom


def import_library(base_dir: str, zip_path: str) -> list:
    """Read a .zip made by ``export_library``. Copies its geometry into the local
    tool_geometry/ folder and returns the list of tool dicts with ``step_file``
    normalised to the local convention. Does NOT merge into any library — the
    caller decides how to handle ID conflicts."""
    gdir = geometry_dir(base_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        if "tools.json" not in names:
            raise ValueError("bundle has no tools.json")
        tools = json.loads(zf.read("tools.json").decode("utf-8"))
        if not isinstance(tools, list):
            raise ValueError("bundle tools.json is not a list")
        for tool in tools:
            tid = str(tool.get("id", "")).strip()
            if not tid:
                continue
            member = next(
                (f"{TOOL_GEOMETRY_DIR}/{tid}{ext}" for ext in _STEP_EXTS
                 if f"{TOOL_GEOMETRY_DIR}/{tid}{ext}" in names), None)
            if member:
                ext = os.path.splitext(member)[1]
                dst = os.path.join(gdir, tid + ext)
                _remove_geometry(base_dir, tid)
                with zf.open(member) as sf, open(dst, "wb") as df:
                    shutil.copyfileobj(sf, df)
                tool["step_file"] = f"{TOOL_GEOMETRY_DIR}/{tid}{ext}"
    return tools
