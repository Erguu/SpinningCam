"""Changelog rendering — headless checks, and an OPT-IN preview of the dialog.

    python _test_changelog_window.py             checks only, exits (default)
    python _test_changelog_window.py --preview   checks + open the window

THE DEFAULT IS HEADLESS ON PURPOSE (2026-08-30). This used to open the real
dialog and sit in `mainloop()` until someone clicked it away — so running the
test suite threw a window onto the developer's screen and blocked there, which
in a batch run reads as a hang and in a timed run as a failure. A test may not
wait on a human. Whether to look at the dialog is a decision for whoever is at
the terminal, so it takes a flag.

Previewing does NOT touch settings.json or changelog_seen_version, so it is safe
to run any time.
"""
import sys
import tkinter as tk

import changelog
from version import APP_VERSION

# --- headless checks -------------------------------------------------------

print("changelog data")

# entries_since only compares versions; it must pass tuple entries through
# untouched now that 1.010 uses them.
secs = changelog.entries_since("1.009", "1.010")
assert [v for v, _ in secs] == ["1.010"], secs
lines = secs[0][1]
assert all(isinstance(x, tuple) for x in lines), "1.010 should be structured entries"
print(f"  OK  1.009 -> 1.010 gives {len(lines)} structured entries")

# Mixed old/new: a user coming from far back sees legacy strings AND tuples.
secs_all = changelog.entries_since("", APP_VERSION)
kinds = {type(x).__name__ for _, ls in secs_all for x in ls}
assert kinds == {"str", "tuple"}, f"expected both entry kinds, got {kinds}"
print(f"  OK  full history spans {len(secs_all)} versions, both entry kinds")

# Every structured entry must be 1..3 fields with a non-empty title, and stay
# on BMP characters (Tk 8.6 mishandles astral-plane chars like emoji).
for ver, ls in secs_all:
    for x in ls:
        parts = [x] if isinstance(x, str) else list(x)
        assert 1 <= len(parts) <= 3, f"v{ver}: entry has {len(parts)} fields"
        assert parts[0].strip(), f"v{ver}: empty title"
        for p in parts:
            bad = [c for c in p if ord(c) > 0xFFFF]
            assert not bad, f"v{ver}: non-BMP char {bad} breaks Tk 8.6"
print("  OK  field counts, non-empty titles, BMP-only text")

# Already-seen current version still yields nothing (dialog must not appear).
assert changelog.entries_since(APP_VERSION, APP_VERSION) == []
print("  OK  seen current version -> no dialog")

# `--check` is still accepted so older notes and habits keep working; it is now
# what happens anyway.
if "--preview" not in sys.argv:
    print("\nCHECKS PASS (window skipped — pass --preview to see the dialog)")
    sys.exit(0)

# --- on-screen preview (opt-in) --------------------------------------------

from ui.dialogs.changelog_window import ChangelogWindow

root = tk.Tk()
root.title("preview host")
root.geometry("900x600")
tk.Label(root, text="Changelog preview — close the dialog to exit.\n"
                    "settings.json is NOT written.",
         font=("Segoe UI", 11)).pack(expand=True)

# Show 1.009 -> 1.010: what a user upgrading from the previous release sees.
ChangelogWindow(root, APP_VERSION, changelog.entries_since("1.009", APP_VERSION),
                lambda dont: root.destroy())
print("\nCHECKS PASS — window open (1.009 -> current)")
root.mainloop()
