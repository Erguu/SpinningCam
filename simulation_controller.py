import time
import threading
import numpy as np
from logger_config import logger

class SimulationController:
    def __init__(self, plotter, ui_manager, get_actors_callback):
        self.plotter = plotter
        self.ui = ui_manager # Not used in thread
        self.get_actors_callback = get_actors_callback
        
        self.is_running = False
        self.current_pos = None
        self.current_radius = 25.0
        self.current_tool_id = ""
        self.thread = None
        self.cleanup_needed = False
        self.speed_multiplier = 1.0  # 1.0 = normal, >1 = faster, <1 = slower

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

    def run(self, v, paths, params, sequence=None):
        if not v: return
        if self.is_running:
            logger.warning("Simulation is already running.")
            return

        self.is_running = True
        self.cleanup_needed = True
        self._general_pause_event.set()  # ensure not paused when starting

        # Start Thread
        self.thread = threading.Thread(target=self._worker, args=(paths, params, sequence))
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

    def _worker(self, paths, params, sequence):
        try:
            num_passes = len(paths)
            default_rad = params.get("roller_visual_radius", 25.0)

            # Set default radius
            self.current_radius = default_rad

            logger.info(f"Starting Simulation Thread. Sequence Mode: {sequence is not None}")

            if sequence:
                # Sequence Mode (Smooth Rapids)
                for i, item in enumerate(sequence):
                    if not self.is_running: break

                    itype = item[0]
                    data = item[1]

                    if itype == "rapid":
                        # Interpolate segment
                        p1, p2 = data[0], data[1]
                        dist = np.linalg.norm(p2 - p1)
                        steps = int(dist / 5.0)
                        if steps < 1: steps = 1

                        vec = p2 - p1
                        spd = max(0.01, self.speed_multiplier)
                        for s in range(steps + 1):
                            if not self.is_running: break
                            self._general_pause_event.wait()
                            if not self.is_running: break
                            t = s / steps
                            self.current_pos = p1 + (vec * t)
                            time.sleep(0.002 / spd)

                    elif itype == "cut":
                        # Play path
                        path = data

                        if len(item) > 2:
                            self.current_radius = float(item[2])
                        if len(item) > 3:
                            self.current_tool_id = str(item[3])

                        step_delay = 0.002
                        if len(path) < 100: step_delay = 0.005 # Slower for short paths

                        spd = max(0.01, self.speed_multiplier)
                        for pt in path:
                            if not self.is_running: break
                            self._general_pause_event.wait()
                            if not self.is_running: break
                            self.current_pos = pt
                            time.sleep(step_delay / spd)

                    # Step-mode pause: hold after every sequence item until Step is clicked
                    if self.step_mode and self.is_running:
                        self._wait_for_step()

            else:
                # Legacy Mode (Just Paths)
                spd = max(0.01, self.speed_multiplier)
                for pass_idx, path in enumerate(paths):
                    if not self.is_running: break

                    self.current_radius = default_rad

                    step_delay = 0.002
                    if len(path) < 100: step_delay = 0.01

                    for pt in path:
                        if not self.is_running: break
                        self._general_pause_event.wait()
                        if not self.is_running: break
                        self.current_pos = pt
                        time.sleep(step_delay / spd)

                    if self.step_mode and self.is_running:
                        self._wait_for_step()

        except Exception as e:
            logger.error(f"Simulation Thread Error: {e}")
        finally:
            self.is_running = False
            self.is_paused = False
            self.current_pos = None
            self.current_tool_id = ""
            logger.info("Simulation Thread Finished.")
