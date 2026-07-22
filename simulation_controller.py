import time
import threading
import numpy as np
from logger_config import logger

# Simulation pacing. Moves are timed by the machine's REAL rates (mm per
# MINUTE): a cut runs at the operation's feed, a rapid at the machine profile's
# rapid-traverse rate. So at speed 1x the sim plays for the real process time;
# the speed multiplier divides that (2x = half). There is no watchability cap or
# floor any more — the free speed field handles slow/long jobs instead.
DEFAULT_RAPID_RATE_MM_MIN = 5000.0   # used when the machine profile has no rapid rate
DEFAULT_CUT_FEED_MM_MIN = 300.0      # used when a cut item carries no feed
CUT_SIM_STEP_MM = 1.0                # sub-step size (keeps tilt interpolation smooth)


def estimate_process_seconds(sequence, params):
    """Total REAL machining time (seconds) for a sim `sequence`: cutting moves at
    each pass's own feed, rapids at the machine's rapid-traverse rate. The
    tool-change dwell is a sim-only cue and is excluded. This is what the sim
    plays in at speed 1x. Returns 0.0 for an empty / None sequence."""
    if not sequence:
        return 0.0
    rapid_mm_s = max(1.0, float(params.get("rapid_rate_mm_min",
                                           DEFAULT_RAPID_RATE_MM_MIN)) / 60.0)
    total = 0.0
    for item in sequence:
        kind = item[0]
        if kind == "cut":
            path = item[1]
            feed = float(item[4]) if len(item) > 4 else DEFAULT_CUT_FEED_MM_MIN
            mm_s = max(0.001, feed / 60.0)
            for i in range(1, len(path)):
                d = float(np.linalg.norm(np.asarray(path[i], dtype=float)
                                         - np.asarray(path[i - 1], dtype=float)))
                total += d / mm_s
        elif kind == "rapid":
            seg = item[1]
            d = float(np.linalg.norm(np.asarray(seg[1], dtype=float)
                                     - np.asarray(seg[0], dtype=float)))
            total += d / rapid_mm_s
    return total

class SimulationController:
    def __init__(self, plotter, ui_manager, get_actors_callback):
        self.plotter = plotter
        self.ui = ui_manager # Not used in thread
        self.get_actors_callback = get_actors_callback
        
        self.is_running = False
        self.current_pos = None
        self.current_pass_idx = -1   # path index the sim is currently playing (#63 overlay)
        self.current_radius = 25.0
        self.current_tilt = None   # B tilt (deg) at current point — tilt-arm machines only
        self.current_tool_id = ""
        self.thread = None
        self.cleanup_needed = False
        self.speed_multiplier = 1.0  # 1.0 = normal, >1 = faster, <1 = slower

        # Tool-change cue: the worker dwells briefly at each tool change (real time,
        # so it's visible even at high playback speed) and flags it; the main thread
        # (check_sim_loop) draws a banner + pulsing marker while active.
        self.tool_change_active = False
        self.tool_change_pos = None
        self.tool_change_from = ""
        self.tool_change_to = ""
        self.tool_change_dwell = 0.9  # seconds of real-time pause at each tool change

        self.step_mode = False   # when True: pause after every sequence item
        self.is_paused = False   # True while waiting for step_one() / set_step_mode(False)
        self._step_event = threading.Event()

        self._general_pause_event = threading.Event()
        self._general_pause_event.set()  # set = not paused

    def set_widgets(self, start_btn, stop_btn):
        pass # Deprecated widget control from logic

    def step_one(self):
        """Advance exactly one sequence item while paused in step mode."""
        self._step_event.set()

    def set_step_mode(self, enabled: bool):
        self.step_mode = enabled
        if not enabled and self.is_paused:
            self._step_event.set()   # resume immediately when step mode is switched off

    def pause(self):
        """Pause simulation between points (general pause)."""
        if self.is_running:
            self._general_pause_event.clear()

    def resume(self):
        """Resume a general-paused simulation."""
        self._general_pause_event.set()

    def stop(self, v=True):
        if not v: return
        logger.info("Simulation STOP command received.")
        self.is_running = False
        self._step_event.set()          # unblock any waiting step so thread can exit
        self._general_pause_event.set() # unblock any general pause so thread can exit

    def run(self, v, paths, params, sequence=None, tilts=None):
        """tilts: optional per-path tilt arrays (path_gen.last_tilt_angles),
        index-aligned with `paths`; None on plain XZ machines."""
        if not v: return
        if self.is_running:
            logger.warning("Simulation is already running.")
            return

        self.is_running = True
        self.cleanup_needed = True
        self._general_pause_event.set()  # ensure not paused when starting

        # Start Thread
        self.thread = threading.Thread(target=self._worker, args=(paths, params, sequence, tilts))
        self.thread.daemon = True
        self.thread.start()

    def _wait_for_step(self):
        """Block until the user clicks Step (or step mode is disabled / sim stopped)."""
        self.is_paused = True
        self._step_event.clear()
        while not self._step_event.wait(timeout=0.05):
            if not self.is_running:
                break
        self._step_event.clear()   # re-arm for next item
        self.is_paused = False

    def _worker(self, paths, params, sequence, tilts=None):
        try:
            num_passes = len(paths)
            default_rad = params.get("roller_visual_radius", 25.0)
            # Cut items appear in the sequence in the same order paths were
            # appended, so cut #k maps to tilts[k].
            cut_counter = 0

            # Set default radius
            self.current_radius = default_rad

            # Rapid pace = machine profile's rapid-traverse rate (mm/min → mm/s).
            rapid_mm_s = max(1.0, float(params.get("rapid_rate_mm_min",
                                                   DEFAULT_RAPID_RATE_MM_MIN)) / 60.0)

            logger.info(f"Starting Simulation Thread. Sequence Mode: {sequence is not None}")

            if sequence:
                # Sequence Mode (Smooth Rapids)
                for i, item in enumerate(sequence):
                    if not self.is_running: break

                    itype = item[0]
                    data = item[1]

                    if itype == "rapid":
                        # Interpolate segment. Rapids used to jump (5 mm steps, a
                        # fixed tiny sleep) so they were hard to follow between
                        # passes. Now: fine ~1 mm steps paced by the machine's real
                        # rapid-traverse rate (no cap — the speed field handles it).
                        p1, p2 = data[0], data[1]
                        dist = float(np.linalg.norm(p2 - p1))
                        spd = max(0.01, self.speed_multiplier)
                        steps = max(1, int(dist / 1.0))
                        total_t = dist / rapid_mm_s
                        dt = (total_t / steps) / spd

                        vec = p2 - p1
                        for s in range(steps + 1):
                            if not self.is_running: break
                            self._general_pause_event.wait()
                            if not self.is_running: break
                            self.current_pos = p1 + (vec * (s / steps))
                            time.sleep(dt)

                    elif itype == "cut":
                        # Play path
                        path = data

                        if len(item) > 2:
                            self.current_radius = float(item[2])
                        if len(item) > 3:
                            self.current_tool_id = str(item[3])
                        # Real cutting feed (mm/min) attached by calculate_paths.
                        cut_feed = float(item[4]) if len(item) > 4 else DEFAULT_CUT_FEED_MM_MIN
                        cut_mm_s = max(0.001, cut_feed / 60.0)

                        cut_tilts = None
                        if tilts is not None and cut_counter < len(tilts):
                            ct = tilts[cut_counter]
                            if ct is not None and len(ct) == len(path):
                                cut_tilts = ct
                        self.current_pass_idx = cut_counter   # #63: drives the deformed blank
                        cut_counter += 1

                        spd = max(0.01, self.speed_multiplier)

                        # Play the first point, then walk each segment paced by the
                        # operation's real feed (mm/s) and subdivided into ~1 mm
                        # sub-steps. A 2-point straight finish then travels at the
                        # correct feed instead of whipping through; a dense pass keeps
                        # its feel (each segment is already < 1 mm, so subs == 1).
                        if len(path):
                            self.current_pos = path[0]
                            if cut_tilts is not None:
                                self.current_tilt = float(cut_tilts[0])
                        for _cpi in range(1, len(path)):
                            if not self.is_running: break
                            p_prev = np.asarray(path[_cpi - 1], dtype=float)
                            p_cur = np.asarray(path[_cpi], dtype=float)
                            seg = float(np.linalg.norm(p_cur - p_prev))
                            subs = max(1, int(seg / CUT_SIM_STEP_MM))
                            dt = (seg / cut_mm_s / subs) / spd
                            t_prev = float(cut_tilts[_cpi - 1]) if cut_tilts is not None else None
                            t_cur = float(cut_tilts[_cpi]) if cut_tilts is not None else None
                            for s in range(1, subs + 1):
                                if not self.is_running: break
                                self._general_pause_event.wait()
                                if not self.is_running: break
                                f = s / subs
                                self.current_pos = p_prev + (p_cur - p_prev) * f
                                if t_prev is not None:
                                    self.current_tilt = t_prev + (t_cur - t_prev) * f
                                time.sleep(dt)

                    elif itype == "toolchange":
                        # Park the roller at the change point and flag the cue, then
                        # dwell in REAL time (not divided by speed) so it's visible
                        # even on a fast run. Interruptible by stop / general pause.
                        self.current_pos = np.asarray(data, dtype=float)
                        self.tool_change_pos = np.asarray(data, dtype=float)
                        self.tool_change_from = str(item[2]) if len(item) > 2 else ""
                        self.tool_change_to = str(item[3]) if len(item) > 3 else ""
                        self.tool_change_active = True
                        _end = time.time() + max(0.0, self.tool_change_dwell)
                        while self.is_running and time.time() < _end:
                            self._general_pause_event.wait()
                            if not self.is_running:
                                break
                            time.sleep(0.02)
                        self.tool_change_active = False

                    # Step-mode pause: hold after every sequence item until Step is clicked
                    if self.step_mode and self.is_running:
                        self._wait_for_step()

            else:
                # Legacy Mode (Just Paths)
                spd = max(0.01, self.speed_multiplier)
                for pass_idx, path in enumerate(paths):
                    if not self.is_running: break

                    self.current_pass_idx = pass_idx   # #63: drives the deformed blank
                    self.current_radius = default_rad
                    cut_tilts = None
                    if tilts is not None and pass_idx < len(tilts):
                        ct = tilts[pass_idx]
                        if ct is not None and len(ct) == len(path):
                            cut_tilts = ct

                    step_delay = 0.002
                    if len(path) < 100: step_delay = 0.01

                    for _cpi, pt in enumerate(path):
                        if not self.is_running: break
                        self._general_pause_event.wait()
                        if not self.is_running: break
                        self.current_pos = pt
                        if cut_tilts is not None:
                            self.current_tilt = float(cut_tilts[_cpi])
                        time.sleep(step_delay / spd)

                    if self.step_mode and self.is_running:
                        self._wait_for_step()

        except Exception as e:
            logger.error(f"Simulation Thread Error: {e}")
        finally:
            self.is_running = False
            self.is_paused = False
            self.current_pos = None
            self.current_pass_idx = -1
            self.current_tilt = None
            self.current_tool_id = ""
            self.tool_change_active = False
            self.tool_change_pos = None
            logger.info("Simulation Thread Finished.")
