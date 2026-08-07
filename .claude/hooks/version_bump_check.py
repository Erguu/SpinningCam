"""Stop hook: has shippable code changed since the last APP_VERSION bump?

Runs when Claude finishes a turn. It compares the working tree + commits against the
last commit that touched ``version.py`` and, if shippable code moved without a version
bump, blocks once so Claude asks the user whether to bump.

Fires at most once per session (marker file in TEMP) and stays silent when there is
nothing to bump for, so read-only or docs-only sessions never see it.

Exit 0 with no output = silent pass. See .claude/settings.json (Stop hook).
"""

import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# Paths that never justify a version bump: docs, scratch diagnostics, tests, backups,
# tool geometry (shared by zip export, not by git), build output, runtime state.
SKIP_DIRS = ("backup/", "tool_geometry/", ".claude/", "dist/", "build/",
             "__pycache__/", "machines/", "Program/")
SKIP_PREFIXES = ("_diag", "_proof", "_test", "_tmp", "test_")
SKIP_NAMES = ("settings.json", "settings.local.json")
SHIP_EXTS = (".py", ".json")


def git(*args):
    """Run git in the project root; return stdout (empty string on failure)."""
    try:
        r = subprocess.run(("git",) + args, cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=20)
    except Exception:
        return ""
    return r.stdout if r.returncode == 0 else ""


def is_shippable(path):
    p = path.replace("\\", "/")
    if p.startswith(SKIP_DIRS):
        return False
    name = p.rsplit("/", 1)[-1]
    if name in SKIP_NAMES or name.startswith(SKIP_PREFIXES):
        return False
    return p.endswith(SHIP_EXTS)


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}

    # Claude is already continuing because of a stop hook -> never re-block (loop guard).
    if payload.get("stop_hook_active"):
        return

    session = str(payload.get("session_id") or "nosession")
    marker = os.path.join(tempfile.gettempdir(),
                          "claude_versioncheck_%s.flag" % re.sub(r"\W", "", session))
    if os.path.exists(marker):
        return

    if not os.path.isfile(os.path.join(ROOT, "version.py")):
        return

    baseline = git("log", "-1", "--format=%H", "--", "version.py").strip()
    if not baseline:
        return

    changed = set()
    for line in git("diff", "--name-only", baseline + "..HEAD").splitlines():
        if line.strip():
            changed.add(line.strip())
    for line in git("status", "--porcelain").splitlines():
        # "XY path" / "XY old -> new" (renames)
        path = line[3:].strip().split(" -> ")[-1].strip().strip('"')
        if path:
            changed.add(path)

    # version.py already touched since the baseline commit -> this session bumped it.
    if any(p.replace("\\", "/") == "version.py" for p in changed):
        return

    shippable = sorted(p for p in changed if is_shippable(p))
    if not shippable:
        return

    version = ""
    try:
        with open(os.path.join(ROOT, "version.py"), encoding="utf-8") as fh:
            m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)', fh.read())
            version = m.group(1) if m else ""
    except OSError:
        pass

    unreleased = git("log", "--oneline", baseline + "..HEAD").strip()
    open(marker, "w").close()

    listing = "\n".join("  - " + p for p in shippable[:20])
    if len(shippable) > 20:
        listing += "\n  - ...and %d more" % (len(shippable) - 20)

    reason = (
        "END-OF-SESSION VERSION CHECK (this fires once per session; it is a prompt, "
        "not an error).\n\n"
        "APP_VERSION is still %s and version.py has not been touched since commit %s, "
        "but shippable code has changed since then:\n%s\n\n"
        "Commits since that bump:\n%s\n\n"
        "Do this now:\n"
        "1. Say in one or two lines what actually changed, user-visible or not.\n"
        "2. Use AskUserQuestion to ask whether to bump APP_VERSION (offer the next "
        "patch number and a 'leave it' option). Do not decide alone.\n"
        "3. If they say yes: bump version.py, add a matching operator-facing entry at "
        "the top of CHANGELOG in changelog.py (see that file's docstring for the "
        "(title, detail, where) tuple format), and note it in LAST_CHANGES.md.\n"
        "4. If they say no, just carry on — this will not ask again this session."
        % (version or "unknown", baseline[:7], listing, unreleased or "  (none — uncommitted work only)")
    )

    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
