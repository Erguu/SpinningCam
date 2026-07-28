# -*- coding: utf-8 -*-
"""explain.py — why does a pass behave like that? (headless)

Same analysis as Tools ▸ "Why is my pass weird?", from the command line, on a
saved project file. Useful when a customer mails a .ssp and the mandrel STEP
it references is not on this machine.

    python explain.py "13. uzun pasolu.ssp"              # audit the whole file
    python explain.py file.ssp --op 8                    # per-pass provenance
    python explain.py file.ssp --op 8 --pass 1           # one pass, every field
    python explain.py file.ssp --step mandrel.STEP       # unlock per-pass checks
    python explain.py file.ssp --lang TR

Without a mandrel model only the file-level checks run (pins, legacy
overrides, gouge risk, leftovers) — those need no geometry. Pass --step, or put
the STEP where the project references it, for the per-pass checks too.

Read-only: never writes the project.
"""
import argparse
import json
import os
import sys


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "params" not in data:
        raise SystemExit(f"not a SpinningCam project file: {path}")
    return data


def _mandrel(data, step_arg):
    """MandrelManager for the project's STEP, or None if it can't be loaded."""
    step = step_arg or data.get("step") or data["params"].get("last_step_path")
    if not step or not os.path.exists(step):
        return None, step
    try:
        from mandrel_analyzer import MandrelManager
        mgr = MandrelManager()
        mgr.load_step(step)
        p = data["params"]
        # load_step alone leaves the default cone measured — update_geometry is
        # what applies the project's placement (see project_clearance_model).
        mgr.update_geometry(p.get("mandrel_rot_x", 0), p.get("mandrel_rot_y", 0),
                            p.get("mandrel_rot_z", 0),
                            p.get("mandrel_pos_x_offset", 0.0),
                            p.get("mandrel_pos_z_offset", 0.0))
        return mgr, step
    except Exception as e:
        print(f"[warn] could not load mandrel {step}: {e}", file=sys.stderr)
        return None, step


def _tools(params):
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(base, "tools.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", help="path to a .ssp project file")
    ap.add_argument("--op", type=int, help="1-based operation number to detail")
    ap.add_argument("--pass", dest="pas", type=int, help="1-based pass number")
    ap.add_argument("--step", help="mandrel STEP to use (overrides the project's)")
    ap.add_argument("--lang", default="EN", choices=("EN", "TR", "ES"))
    ap.add_argument("--all", action="store_true",
                    help="detail every operation, not just the audit")
    a = ap.parse_args(argv)

    from i18n import set_language
    set_language(a.lang)
    from recipe_explain import (audit_operations, explain_field, format_report,
                                find_overrides, field_label)

    data = _load(a.project)
    params = data["params"]
    ops = params.get("operations") or []
    mgr, step = _mandrel(data, a.step)
    overrides = {int(k): v for k, v in (data.get("overrides") or {}).items()}

    print(f"{os.path.basename(a.project)} — {len(ops)} operation(s), "
          f"{sum(1 for o in ops if o.get('enabled', True))} enabled")
    print(f"mandrel: {step or '(none referenced)'}"
          f"{'' if mgr else '   [NOT LOADED — file-level checks only]'}")
    print()

    targets = []
    if a.op:
        targets = [a.op - 1]
    elif a.all:
        targets = [i for i, o in enumerate(ops) if o.get("enabled", True)]

    if targets:
        if mgr is None:
            print("per-pass detail needs the mandrel model — pass --step\n")
        else:
            from ui.dialogs.pass_table import compute_pass_rows
            for i in targets:
                if not 0 <= i < len(ops):
                    print(f"no operation #{i + 1}")
                    continue
                op = ops[i]
                print(f"── op #{i + 1}  {op.get('name') or op.get('type')}  "
                      f"[{op.get('type')}, {op.get('tool_id')}, "
                      f"{'ON' if op.get('enabled', True) else 'OFF'}]")
                rows = compute_pass_rows(op, params, mgr)
                for r in rows:
                    if a.pas and r["i"] + 1 != a.pas:
                        continue
                    hits = dict(find_overrides(r))
                    print(f"   pass {r['i'] + 1}:")
                    for field in ("anchor", "extend", "clr", "angle", "reach"):
                        txt = explain_field(r, field)
                        if txt:
                            print(f"      {'>>' if field in hits else '  '} {txt}")
                    for w in r["warnings"]:
                        print(f"       ! {w}")
                print()

    print("── recipe check " + "─" * 40)
    findings = audit_operations(params, mgr, gui_overrides=overrides,
                                tools=_tools(params))
    print(format_report(findings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
