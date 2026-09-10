# -*- coding: utf-8 -*-
"""Headless test: every UI string exists, in every language.

WHY

`t("key")` returns the KEY ITSELF when it is missing (i18n.py `t`), and falls
back to English when only some languages have it. Both failures are silent at
the desk of whoever wrote the feature — they work in EN, and the shop floor in
Mexico is where `rep_item_program` shows up as a label. The rule in
CODE_NAVIGATION §17 is that every new string lands in all three languages at
once, and until now nothing enforced it.

Three separate claims, because they fail for different reasons:

1. Every literal `t("...")` in the source has an entry.  → typo, or forgot i18n
2. Every entry covers EN, TR and ES, non-empty.          → added EN only
3. Every entry is a dict of language→string.             → malformed entry

WHAT THIS CANNOT SEE

Keys built at run time (`t("rep_item_" + key)`, `t(lk)`). They are counted and
reported so the number is visible, but a dynamic family has to be covered by the
test that owns the feature — `_test_report_bundle.py` does exactly that for the
report rows.
"""
import os
import re
import sys

from i18n import LANGUAGES, STRINGS

HERE = os.path.dirname(os.path.abspath(__file__))

# A literal key inside a t(...) call.
LITERAL = re.compile(r"\bt\(\s*([\"'])([A-Za-z0-9_]+)\1\s*\)")
# A t(...) call whose argument is not a plain literal.
DYNAMIC = re.compile(r"\bt\(\s*(?![\"'][A-Za-z0-9_]+[\"']\s*\))[^)\n]")

# Not shipped: tests, one-off diagnostics, research scratch.
SKIP_PREFIXES = ("_test_", "test_", "_diag_", "_research_", "_proof_")
SKIP_FILES = {"i18n.py"}                      # defines t(), does not consume it
SKIP_DIRS = {"__pycache__", "backup", "machines", "tool_geometry", ".git"}


def source_files():
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in sorted(files):
            if not fn.endswith(".py") or fn in SKIP_FILES:
                continue
            if any(fn.startswith(p) for p in SKIP_PREFIXES):
                continue
            yield os.path.join(root, fn)


def scan():
    """(used_keys, dynamic_call_count) across the shipped source."""
    used, dynamic = {}, 0
    for path in source_files():
        rel = os.path.relpath(path, HERE)
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if line.lstrip().startswith("#"):
                    continue
                for m in LITERAL.finditer(line):
                    used.setdefault(m.group(2), []).append(f"{rel}:{n}")
                if DYNAMIC.search(line):
                    dynamic += 1
    return used, dynamic


def test_every_used_key_exists():
    used, dynamic = scan()
    missing = {k: v for k, v in used.items() if k not in STRINGS}
    if missing:
        lines = ["%d key(s) used in the UI but absent from i18n.STRINGS:" % len(missing)]
        for k in sorted(missing):
            lines.append("  %-32s %s" % (k, ", ".join(missing[k][:3])))
        raise AssertionError("\n".join(lines))
    print("1 every literal t() key exists: OK (%d keys, %d dynamic calls skipped)"
          % (len(used), dynamic))


def test_every_entry_covers_every_language():
    """Blank in SOME languages is the bug. Blank in ALL of them is a decision.

    A handful of entries are deliberately empty everywhere — `rx_col_sev` is the
    header of a 34 px icon column that shows a ◆ and must have no caption. What
    is never right is text in one language and nothing in another, because that
    is what a half-finished translation looks like and it renders as an empty
    label on exactly one shop floor.
    """
    bad, blank = {}, []
    for key, entry in STRINGS.items():
        if not isinstance(entry, dict):
            continue                       # reported by the shape test below
        gaps = [lang for lang in LANGUAGES
                if not str(entry.get(lang, "") or "").strip()]
        if not gaps:
            continue
        if len(gaps) == len(LANGUAGES):
            blank.append(key)              # deliberately captionless
        else:
            bad[key] = gaps
    if bad:
        lines = ["%d entry/entries translated in some languages but not others:"
                 % len(bad)]
        for k in sorted(bad):
            lines.append("  %-32s missing %s" % (k, "+".join(bad[k])))
        raise AssertionError("\n".join(lines))
    print("2 every entry covers %s: OK (%d entries, %d deliberately blank: %s)"
          % ("/".join(LANGUAGES), len(STRINGS), len(blank), ", ".join(sorted(blank)) or "-"))


def test_every_entry_is_well_formed():
    bad = [k for k, v in STRINGS.items() if not isinstance(v, dict)]
    assert not bad, "not a language dict: %s" % sorted(bad)
    nonstr = [(k, lang) for k, v in STRINGS.items() if isinstance(v, dict)
              for lang, val in v.items() if not isinstance(val, str)]
    assert not nonstr, "non-string translations: %s" % nonstr
    print("3 every entry is language->string: OK")


def test_format_placeholders_match_across_languages():
    """A translation that drops a {placeholder} raises KeyError at the moment it
    is shown — in the one language the developer does not run. Compares the
    named fields of each translation against the English one."""
    field = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
    bad = {}
    for key, entry in STRINGS.items():
        if not isinstance(entry, dict) or "EN" not in entry:
            continue
        want = set(field.findall(entry["EN"]))
        for lang in LANGUAGES:
            if lang == "EN" or lang not in entry:
                continue
            got = set(field.findall(entry[lang]))
            if got != want:
                bad.setdefault(key, []).append(
                    "%s has %s, EN has %s" % (lang, sorted(got) or "none",
                                              sorted(want) or "none"))
    if bad:
        lines = ["%d entry/entries with mismatched placeholders:" % len(bad)]
        for k in sorted(bad):
            lines.append("  %-28s %s" % (k, "; ".join(bad[k])))
        raise AssertionError("\n".join(lines))
    print("4 placeholders match across languages: OK")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print("FAIL - %s\n%s" % (fn.__name__, e))
    print()
    print("ALL i18n CHECKS PASSED" if not failed else "%d i18n CHECK(S) FAILED" % failed)
    sys.exit(1 if failed else 0)
