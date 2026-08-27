# -*- coding: utf-8 -*-
"""#102 — the shared 2D-preview orientation helper.

The bug this guards: the pass table and the waypoint editor drew the same pass
with the axes SWAPPED, and only one of them applied the machine-side mirror.

Run:  python _test_preview_orient.py
"""
import sys

from ui import preview_orient as po

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


class FakeCam:
    def __init__(self, position, focal_point, up):
        self.position, self.focal_point, self.up = position, focal_point, up


class FakePlotter:
    def __init__(self, cam):
        self.camera = cam


class FakeApp:
    def __init__(self, cam=None, positive_side=True, cx=0.0):
        self.params = {"roller_positive_x_side": positive_side,
                       "mandrel_pos_x_offset": cx}
        if cam is not None:
            self.plotter = FakePlotter(cam)


def test_fallback():
    print("\n[1] no camera → the old pass-table convention")
    o = po.resolve(FakeApp())
    check("Z horizontal, X up", o.z_horizontal and o.h_sign == 1 and o.v_sign == 1)
    h, v = po.to_plane(o, 70.0, 30.0)
    check("to_plane puts Z across and X up", (h, v) == (30.0, 70.0), f"{(h, v)}")
    check("labels read Z→ (X↑)", po.axis_labels(o) == ("Z→", "X↑"))

    # A plotter with an unreadable camera must not raise, and must fall back.
    class Broken:
        @property
        def camera(self):
            raise RuntimeError("no render window")
    app = FakeApp()
    app.plotter = Broken()
    check("a broken camera falls back instead of raising",
          po.resolve(app).z_horizontal)


def test_camera_axes():
    print("\n[2] orientation follows the camera")
    # Looking down world -Y at the XZ plane, screen-up = world +Z.
    # Then world Z is VERTICAL on screen, so X becomes the horizontal axis.
    o = po.resolve(FakeApp(FakeCam((0, -800, 50), (0, 0, 50), (0, 0, 1))))
    check("Z up on screen → X becomes horizontal", not o.z_horizontal)
    h, v = po.to_plane(o, 70.0, 30.0)
    check("X across, Z up", (h, v) == (70.0, 30.0), f"{(h, v)}")

    # Same view, screen-up = world +X → Z is horizontal again (pass-table style).
    o = po.resolve(FakeApp(FakeCam((0, -800, 50), (0, 0, 50), (1, 0, 0))))
    check("X up on screen → Z is horizontal", o.z_horizontal)

    # Orbit 180°: viewing from +Y instead of -Y flips the horizontal direction.
    a = po.resolve(FakeApp(FakeCam((0, -800, 50), (0, 0, 50), (1, 0, 0))))
    b = po.resolve(FakeApp(FakeCam((0, 800, 50), (0, 0, 50), (1, 0, 0))))
    check("viewing from the other side flips the horizontal axis",
          a.h_sign == -b.h_sign, f"{a.h_sign} vs {b.h_sign}")

    # Upside down: up = -X must flip the vertical.
    c = po.resolve(FakeApp(FakeCam((0, -800, 50), (0, 0, 50), (-1, 0, 0))))
    check("an inverted up-vector flips the vertical axis", c.v_sign == -1)


def test_mirror():
    print("\n[3] the machine-side mirror lives here now")
    o = po.resolve(FakeApp(positive_side=True, cx=10.0))
    check("positive side does not mirror", po.to_plane(o, 70.0, 30.0)[1] == 70.0)

    o = po.resolve(FakeApp(positive_side=False, cx=10.0))
    check("negative side mirrors X about the mandrel centre",
          po.to_plane(o, 70.0, 30.0)[1] == 2 * 10.0 - 70.0,
          str(po.to_plane(o, 70.0, 30.0)))
    check("mirroring does not touch Z", po.to_plane(o, 70.0, 30.0)[0] == 30.0)

    # The mirror must be an involution: mirroring the centre leaves it alone.
    check("the mandrel centre is its own mirror",
          po.to_plane(o, 10.0, 0.0)[1] == 10.0)


def test_frames():
    print("\n[3b] canonical vs machine frame (the SCL inspector's trap)")
    app = FakeApp(positive_side=False, cx=10.0)
    canon = po.resolve(app)                                  # default
    mach = po.resolve(app, frame=po.MACHINE)
    check("canonical mirrors", canon.mirror_x)
    check("machine does NOT mirror again", not mach.mirror_x)
    check("but the axis layout is identical in both frames",
          (canon.z_horizontal, canon.h_sign, canon.v_sign)
          == (mach.z_horizontal, mach.h_sign, mach.v_sign))

    # The engine's own mirror, then the machine-frame draw, must land where the
    # canonical draw lands. This is the round trip that double-mirroring breaks.
    x_canon, z = 70.0, 30.0
    x_machine = 2 * 10.0 - x_canon                  # what calculate_paths stores
    check("a machine-frame point draws where its canonical twin does",
          po.to_plane(mach, x_machine, z) == po.to_plane(canon, x_canon, z),
          f"{po.to_plane(mach, x_machine, z)} vs {po.to_plane(canon, x_canon, z)}")

    # On a positive-side machine the two frames are the same thing — which is
    # exactly why getting this wrong stays invisible there.
    pos = FakeApp(positive_side=True, cx=10.0)
    check("on a positive-side machine both frames agree",
          po.to_plane(po.resolve(pos), 70.0, 30.0)
          == po.to_plane(po.resolve(pos, frame=po.MACHINE), 70.0, 30.0))


def test_agreement():
    print("\n[4] both previews now agree (the actual bug)")
    # Same app, same camera → both windows resolve the SAME orientation, so a
    # point drawn in one lands in the same place in the other.
    app = FakeApp(FakeCam((0, -800, 50), (0, 0, 50), (1, 0, 0)),
                  positive_side=False, cx=10.0)
    a = po.resolve(app)
    b = po.resolve(app)
    check("two windows resolve identically", a == b)
    pts = [(70.0, 30.0), (55.0, -12.0), (90.0, 44.0)]
    check("and map every point identically",
          [po.to_plane(a, x, z) for x, z in pts]
          == [po.to_plane(b, x, z) for x, z in pts])

    # Order must be preserved: a point further out in X stays further out.
    o = po.resolve(FakeApp())
    check("larger X stays higher on a positive-side machine",
          po.to_plane(o, 80.0, 0.0)[1] > po.to_plane(o, 70.0, 0.0)[1])
    o = po.resolve(FakeApp(positive_side=False, cx=0.0))
    check("larger X stays consistent (mirrored) on a negative-side machine",
          po.to_plane(o, 80.0, 0.0)[1] < po.to_plane(o, 70.0, 0.0)[1])


if __name__ == "__main__":
    test_fallback()
    test_camera_axes()
    test_mirror()
    test_frames()
    test_agreement()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    sys.exit(1 if FAIL else 0)
