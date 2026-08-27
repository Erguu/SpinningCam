# -*- coding: utf-8 -*-
"""Open a dialog big enough for its own contents. TODO #103.

THE BUG THIS EXISTS FOR (measured 2026-08-28)

Every dialog asked for a fixed pixel size — `self.geometry("820x600")` — while
the main window sets Tk's scaling from the monitor's DPI
(`main_window.py:55`, `tk scaling = dpi/72`). So on a 125 % display every font,
padding and button grows, and the window does not. Measured on the waypoint
editor:

    96 dpi (100 %)   needs 781x594   opens 820x600   fits, 6 px to spare
    120 dpi (125 %)  needs 786x654   opens 820x600   54 px CLIPPED
    144 dpi (150 %)  needs 785x626   opens 820x600   26 px CLIPPED

54 px is the OK / Cancel row. The operator sees a dialog with no way to accept
it, and the only cure is to drag the window bigger — which is not something to
expect anyone to know, or to remember every time.

WHAT `fit` DOES

Treats the hardcoded number as a MINIMUM WISH, not an answer: the window opens
at whatever Tk says the content needs, or the wish, whichever is larger, clamped
to the screen. It also sets `minsize` to the required size, so the buttons
cannot be dragged out of existence afterwards either.

Measured at idle rather than computed, because only Tk knows what its own fonts
came out as on this machine — which is exactly the thing that varies between the
programmer's desk and the shop floor.

WHY THE BUTTON BAR ALSO HAS TO BE PACKED `side="bottom"` FIRST

If the SCREEN itself cannot fit the content, no amount of resizing helps. Tk's
packer hands out space in packing order, so whatever is packed last is what gets
squeezed off — and in a dialog built top-down that is always the button bar.
Packing the bar bottom-first reserves its space, and the table or canvas above
shrinks instead. `fit` cannot do this for a dialog; it is a property of how the
dialog was built. See `pass_table`, `exit_tail_dialog` and `break_points_dialog`
for the pattern.
"""
from logger_config import logger

# Leave room for the taskbar and a little breathing space. A dialog that fills
# the entire screen edge-to-edge reads as broken even when it is correct.
_MAX_W_FRAC = 0.95
_MAX_H_FRAC = 0.90


def fit(win, want_w, want_h, parent=None):
    """Size `win` to hold its contents, at least `want_w` x `want_h`.

    Call it exactly where the old `geometry("WxH")` call was — it sets that size
    immediately so nothing flickers through an unsized window, then re-measures
    once the widgets exist and grows the window if they need more.

    Never raises: a dialog that opens at the wrong size is a nuisance, one that
    fails to open is a stoppage.
    """
    try:
        win.geometry(f"{int(want_w)}x{int(want_h)}")
    except Exception:
        pass
    try:
        win.after_idle(lambda: _apply(win, want_w, want_h, parent))
    except Exception as e:                                   # pragma: no cover
        logger.debug(f"#103 deferred fit unavailable: {e}")


def measure(win, want_w, want_h):
    """(width, height, min_w, min_h) `fit` would use. Pure — no side effects.

    Split out so the sizing rule can be tested without a display server doing
    real window management.
    """
    req_w = max(int(win.winfo_reqwidth()), 1)
    req_h = max(int(win.winfo_reqheight()), 1)
    max_w = int(win.winfo_screenwidth() * _MAX_W_FRAC)
    max_h = int(win.winfo_screenheight() * _MAX_H_FRAC)
    w = min(max(int(want_w), req_w), max_w)
    h = min(max(int(want_h), req_h), max_h)
    # minsize is the CONTENT requirement, not the wish: shrinking below the wish
    # is fine and sometimes necessary on a small screen, shrinking below what the
    # widgets need is what hides the buttons.
    return w, h, min(req_w, max_w), min(req_h, max_h)


def _apply(win, want_w, want_h, parent):
    try:
        if not win.winfo_exists():
            return
        win.update_idletasks()
        w, h, min_w, min_h = measure(win, want_w, want_h)
        win.minsize(min_w, min_h)

        # Centre on the parent when there is one, then clamp onto the screen so a
        # parent near an edge (or on a second monitor that is gone) cannot push
        # the dialog somewhere the operator has to hunt for it.
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        p = parent if parent is not None else win.master
        try:
            px, py = p.winfo_rootx(), p.winfo_rooty()
            pw, ph = p.winfo_width(), p.winfo_height()
            if pw <= 1 or ph <= 1:
                raise ValueError
            x, y = px + (pw - w) // 2, py + (ph - h) // 2
        except Exception:
            x, y = (sw - w) // 2, (sh - h) // 2
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
        win.geometry(f"{w}x{h}+{x}+{y}")
    except Exception as e:
        logger.debug(f"#103 fit failed, keeping the requested size: {e}")
