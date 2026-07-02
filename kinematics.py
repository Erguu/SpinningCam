"""
Machine kinematics models.

ID112 hot spinning machine: the Z carriage carries a rotary (B) pivot, and the
X slide rides on the rotating arm. Tool tip position in the CAM XZ plane is a
function of (B, X-on-arm, Z-carriage), and the roller orientation follows B.

Tilt convention
---------------
tilt = 0 deg  -> slide is purely radial (identical to the ID111 machine).
Positive tilt rotates the tool tip direction toward +Z.
Physical B axis value = tilt * tilt_b_sign + tilt_b_home.

Assumption (Phase 1): the tool tip lies on the slide axis and the tool rotates
about its own tip. The tip therefore keeps following the same offset surface a
non-tilting machine would; tilt only adds orientation. Contact-point migration
on the curved roller profile at large tilt is a later refinement (TODO #50).

"Both-ready core": the CAM's canonical output is tool tip XZ + tilt per point.
This module converts tip+tilt <-> machine axes (B, X_arm, Z_carriage) in both
directions, so the Phase 3 decision (does the CODESYS controller receive
machine axes, or Cartesian + angle?) needs no rework on the CAM side.
"""
import math

# Geometry keys read from the machine profile (placeholders until the machine
# builder provides real dimensions — all editable in the Machine tab).
# NOTE: pivot coordinates are expressed in the CAM global frame (the same frame
# as calculated path points), so reachability checks run directly on paths.
# Mapping to physical machine-frame values happens with calibration (Phase 3).
TILT_PROFILE_DEFAULTS = {
    "tilt_pivot_x": 0.0,    # pivot X in CAM global coords
    "tilt_pivot_z": 0.0,    # pivot Z in CAM global coords (rides with Z carriage)
    "tilt_b_min": -60.0,    # deg, physical B axis travel
    "tilt_b_max": 60.0,     # deg
    "tilt_b_home": 0.0,     # deg, B axis reading when tilt = 0
    "tilt_b_sign": 1.0,     # +1 / -1, positive-tilt direction of the B axis
}


class TiltArmKinematics:
    """Tip+tilt <-> (B, X_arm, Z_carriage) for the ID112 tilt-arm machine."""

    def __init__(self, params: dict):
        g = lambda k: float(params.get(k, TILT_PROFILE_DEFAULTS[k]))
        self.pivot_x = g("tilt_pivot_x")
        self.pivot_z = g("tilt_pivot_z")
        self.b_min   = g("tilt_b_min")
        self.b_max   = g("tilt_b_max")
        self.b_home  = g("tilt_b_home")
        self.b_sign  = g("tilt_b_sign") or 1.0
        # Roller approach side: the arm extends from the pivot TOWARD the
        # mandrel, i.e. in +X for positive-side machines, -X for negative-side.
        self.side = 1.0 if params.get("roller_positive_x_side", True) else -1.0

    # ── Angle helpers ────────────────────────────────────────────────────────

    def clamp_tilt(self, tilt_deg: float) -> float:
        """Clamp a desired tilt to the physically reachable range (in tilt
        convention; the B travel limits are expressed as tilt via sign/home)."""
        lo, hi = sorted(((self.b_min - self.b_home) / self.b_sign,
                         (self.b_max - self.b_home) / self.b_sign))
        return max(lo, min(hi, tilt_deg))

    def tilt_to_b(self, tilt_deg: float) -> float:
        return tilt_deg * self.b_sign + self.b_home

    # ── Forward / inverse ────────────────────────────────────────────────────

    def forward(self, b_axis: float, x_arm: float, z_car: float):
        """Machine axes -> (tip_x, tip_z, tilt_deg) in CAM global coords."""
        tilt = (b_axis - self.b_home) / self.b_sign
        th = math.radians(tilt)
        tip_x = self.pivot_x + self.side * x_arm * math.cos(th)
        tip_z = z_car + self.pivot_z + x_arm * math.sin(th)
        return tip_x, tip_z, tilt

    def inverse(self, tip_x: float, tip_z: float, tilt_deg: float):
        """(tip_x, tip_z, tilt) -> (b_axis, x_arm, z_car).

        Raises ValueError near the cos(tilt)=0 singularity (arm parallel to Z);
        the B travel limits normally prevent ever getting close.
        """
        th = math.radians(tilt_deg)
        c = math.cos(th)
        if abs(c) < 1e-6:
            raise ValueError(f"tilt {tilt_deg:.1f} deg is at the +/-90 deg singularity")
        x_arm = self.side * (tip_x - self.pivot_x) / c
        z_car = tip_z - self.pivot_z - x_arm * math.sin(th)
        return self.tilt_to_b(tilt_deg), x_arm, z_car

    # ── Validation ───────────────────────────────────────────────────────────

    def check_reachable(self, points, tilts) -> list:
        """Validate a path (Nx3 CAM points) + per-point tilt array.

        Returns a list of human-readable violation strings (empty = all good):
        B out of travel, singularity, or negative arm extension (tip on the
        wrong side of the pivot).
        """
        issues = []
        for i, (pt, tilt) in enumerate(zip(points, tilts)):
            b = self.tilt_to_b(tilt)
            if not (self.b_min - 1e-9 <= b <= self.b_max + 1e-9):
                issues.append(f"pt {i}: B={b:.1f} deg outside [{self.b_min:.1f}, {self.b_max:.1f}]")
                continue
            try:
                _, x_arm, _ = self.inverse(pt[0], pt[2], tilt)
            except ValueError as e:
                issues.append(f"pt {i}: {e}")
                continue
            if x_arm < 0.0:
                issues.append(f"pt {i}: arm extension {x_arm:.1f} mm < 0 (tip behind pivot)")
        return issues


def get_kinematics(params: dict):
    """Return the kinematics model for the active machine, or None for plain
    XZ machines (ID111) where no transformation is needed."""
    if params.get("kinematics") == "tilt_arm":
        return TiltArmKinematics(params)
    return None
