"""User-facing changelog, shown once per new version on startup (see
``ui/dialogs/changelog_window.py``).

Keyed by version string. When you bump ``version.APP_VERSION``, add the matching entry
here with short, operator-facing bullet lines (what changed, not how it was coded).
"""

CHANGELOG = {
    "1.004": [
        "Reach authoring reworked: one 'Reach' value per pass, with End Reach / End Angle columns.",
        "Reach⟲ estimates the reach from the remaining blank flange and fills it in.",
        "'Reach follows blank' keeps the reach kissing the blank edge automatically as the end Z changes.",
        "Reach factor (×) biases the auto reach (e.g. 0.90 = stop at 90% of the flange).",
        "Angle⟲ fills the progressive fan-end angle from the mandrel surface (no more assuming 180°).",
        "Continue ⤵ starts a new operation from the previous op's end position / angle / reach.",
        "Split… breaks one multi-pass operation into editable chunk operations.",
        "Clamp-zone warning + 3D band marks the counter-press region that must not be machined.",
        "Pass Info now lists each pass's reach |P2→P3|.",
        "Fixes: the exit no longer folds past 180° or overlaps near the flange; End Angle is shown in your pass-angle frame.",
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
