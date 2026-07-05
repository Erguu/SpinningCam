"""Verify that the exe builder still matches the app — so drift can't hide.

Two layers, cheapest first:

  python check_packaging.py            → STATIC checks only (no build needed, seconds)
  python check_packaging.py --post-build [dist_dir]
                                       → also verify the built folder + run the exe's
                                         own --selfcheck

STATIC checks:
  * every SHIP_NEXT_TO_EXE entry exists in the source tree (build has something to copy)
  * every CRITICAL_MODULES entry imports in the dev environment
  * SOURCE SCAN: grep the source for runtime data-file reads; WARN about any data
    filename that is neither shipped nor explicitly in NOT_SHIPPED — the safety net
    that stops a new file from being silently forgotten.

POST-BUILD checks (run after build_exe.py):
  * every required SHIP_NEXT_TO_EXE entry sits NEXT TO the exe (not just _internal)
  * SECURITY: no MUST_NOT_SHIP file (private key, admin.lic) leaked into the build
  * the exe's own `--selfcheck` exits 0

Exit code is 0 only when everything passes, so this is CI/pre-ship friendly.
"""

import importlib
import os
import re
import subprocess
import sys

import packaging_manifest as M

ROOT = os.path.dirname(os.path.abspath(__file__))

# Data-file extensions we care about when scanning source for "did you ship it?".
_DATA_RE = re.compile(r"""['"]([A-Za-z0-9_./\\-]+\.(?:json|png|ico|lic|pem))['"]""")
# Directories to skip when scanning/searching (third-party + build artifacts).
_SKIP_DIRS = {"_internal", "dist", "build", "backup", ".git", "__pycache__", ".claude"}


def _iter_source_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for f in filenames:
            if f.endswith(".py") and not f.startswith("_"):  # skip _research_/_test_ scratch
                yield os.path.join(dirpath, f)


def _shipped_names():
    """Basenames covered by the manifest, expanding shipped directories to their
    contents (so machines/ID111-1.json counts as shipped via the machines/ dir)."""
    names = set()
    for name, _ in M.SHIP_NEXT_TO_EXE:
        names.add(os.path.basename(name))
        full = os.path.join(ROOT, name)
        if os.path.isdir(full):
            for f in os.listdir(full):
                names.add(f)
    return names


def check_static():
    problems, warnings = [], []

    # 1. Every non-optional shipped item exists to be copied.
    for name, optional in M.SHIP_NEXT_TO_EXE:
        if not optional and not os.path.exists(os.path.join(ROOT, name)):
            problems.append(f"SHIP source missing: '{name}' is required but not in the project tree")

    # 2. Critical modules import in the dev env.
    for mod in M.CRITICAL_MODULES:
        try:
            importlib.import_module(mod)
        except Exception as e:  # noqa: BLE001
            problems.append(f"IMPORT '{mod}': {type(e).__name__}: {e}")

    # 3. Source scan: any data filename read in code that we neither ship nor exclude?
    known = _shipped_names() | set(M.NOT_SHIPPED) | set(M.MUST_NOT_SHIP)
    # machine profiles are a directory of *.json — treat any machines/*.json as covered
    seen = {}
    for src in _iter_source_files():
        try:
            with open(src, encoding="utf-8") as fh:
                text = fh.read()
        except Exception:  # noqa: BLE001
            continue
        for m in _DATA_RE.finditer(text):
            base = os.path.basename(m.group(1).replace("\\", "/"))
            seen.setdefault(base, src)
    for base, src in sorted(seen.items()):
        if base in known:
            continue
        if base.startswith("license") and base.endswith(".lic"):
            continue  # customer-browsed licenses, various names
        rel = os.path.relpath(src, ROOT)
        warnings.append(f"'{base}' is read in {rel} but is not in SHIP_NEXT_TO_EXE or "
                        f"NOT_SHIPPED — ship it or list it as excluded")

    return problems, warnings


def check_post_build(dist_dir):
    problems = []
    exe = os.path.join(dist_dir, "SpinningCam.exe")
    if not os.path.exists(exe):
        return [f"exe not found at {exe} — did the build run?"]

    # 1. Required data present NEXT TO the exe (get_base_path == this folder).
    for name, optional in M.SHIP_NEXT_TO_EXE:
        if optional:
            continue
        if not os.path.exists(os.path.join(dist_dir, name)):
            problems.append(f"missing next to exe: '{name}' (present only in _internal does NOT count)")

    # 2. SECURITY: nothing that must never ship leaked anywhere into the build.
    for secret in M.MUST_NOT_SHIP:
        for dirpath, dirnames, filenames in os.walk(dist_dir):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            if secret in filenames:
                rel = os.path.relpath(os.path.join(dirpath, secret), dist_dir)
                problems.append(f"SECURITY: '{rel}' must NEVER ship — remove it from the build")

    # 3. The exe proves itself.
    try:
        r = subprocess.run([exe, "--selfcheck"], capture_output=True, text=True, timeout=120)
        out = (r.stdout or "") + (r.stderr or "")
        print("── exe --selfcheck output ──")
        print(out.strip() or "(no output)")
        print("────────────────────────────")
        if r.returncode != 0:
            problems.append("exe --selfcheck returned non-zero (see output above)")
    except Exception as e:  # noqa: BLE001
        problems.append(f"could not run exe --selfcheck: {type(e).__name__}: {e}")

    return problems


def main():
    post = "--post-build" in sys.argv
    dist_dir = None
    if post:
        args = [a for a in sys.argv[1:] if a != "--post-build"]
        dist_dir = args[0] if args else os.path.join(ROOT, "dist", "SpinningCam")

    print("=== SpinningCam packaging check ===\n")
    problems, warnings = check_static()

    if warnings:
        print("WARNINGS (won't fail the check, but look):")
        for w in warnings:
            print("  ! " + w)
        print()

    if post:
        problems += check_post_build(dist_dir)

    if problems:
        print("FAILED:")
        for p in problems:
            print("  ✗ " + p)
        return 1

    scope = "static + post-build" if post else "static"
    print(f"PASSED ({scope}). Builder matches the app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
