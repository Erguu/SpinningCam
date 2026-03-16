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
        self.thread = None
        self.cleanup_needed = False

    def set_widgets(self, start_btn, stop_btn):
        pass # Deprecated widget control from logic

    def stop(self, v=True):
        if not v: return
        logger.info("Simulation STOP command received.")
        self.is_running = False

    def run(self, v, paths, params, sequence=None):
        if not v: return
        if self.is_running:
            logger.warning("Simulation is already running.")
            return

        self.is_running = True
        self.cleanup_needed = True 
        
        # Start Thread
        self.thread = threading.Thread(target=self._worker, args=(paths, params, sequence))
        self.thread.daemon = True 
        self.thread.start()

    def _worker(self, paths, params, sequence):
        try:
            num_passes = len(paths)
            tc_active = params.get("tool_change_active", False)
            rough_rad = params.get("roller_visual_radius", 25.0)
            finish_rad = params.get("finish_tool_radius", 25.0)
            
            # Set default radius
            self.current_radius = rough_rad
            
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
                        for s in range(steps + 1):
                            if not self.is_running: break
                            t = s / steps
                            self.current_pos = p1 + (vec * t)
                            time.sleep(0.002)
                            
                    elif itype == "cut":
                        # Play path
                        path = data
                        
                        if len(item) > 2:
                            self.current_radius = float(item[2])
                        
                        step_delay = 0.002 
                        if len(path) < 100: step_delay = 0.005 # Slower for short paths
                        
                        for pt in path:
                            if not self.is_running: break
                            self.current_pos = pt
                            time.sleep(step_delay)
            
            else:
                # Legacy Mode (Just Paths)
                for pass_idx, path in enumerate(paths):
                    if not self.is_running: break
                    
                    is_last_pass = (pass_idx == num_passes - 1)
                    current_rad = finish_rad if (is_last_pass and tc_active) else rough_rad
                    self.current_radius = current_rad
                    
                    step_delay = 0.002 
                    if len(path) < 100: step_delay = 0.01
                    
                    for pt in path:
                        if not self.is_running: break
                        self.current_pos = pt
                        time.sleep(step_delay)
                    
        except Exception as e:
            logger.error(f"Simulation Thread Error: {e}")
        finally:
            self.is_running = False
            self.current_pos = None
            logger.info("Simulation Thread Finished.")
