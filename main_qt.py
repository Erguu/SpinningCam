
import sys
import os
import signal
from qtpy.QtWidgets import QApplication, QMainWindow, QDockWidget
from qtpy.QtCore import Qt
from pyvistaqt import QtInteractor
import pyvista as pv

# Import Project Modules
from main import SpinningApp
from ui_sidebar import SidebarWidget
from logger_config import logger

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpinningCam Pro - Modern Control")
        self.resize(1600, 900)

        # 1. Setup Central 3D Widget (PyVistaQt)
        self.plotter = QtInteractor(self)
        self.setCentralWidget(self.plotter)
        
        # 2. Setup Spinning Logic (Headless-like mode)
        # We pass the Qt plotter to the app so it renders to our window
        self.app_logic = SpinningApp(plotter=self.plotter, headless=True)
        
        # 3. Setup UI Sidebar
        self.sidebar = SidebarWidget(self.app_logic.params)
        self.dock = QDockWidget("Kontrol Paneli", self)
        self.dock.setWidget(self.sidebar)
        self.dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        
        # 4. Connect Signals
        self.sidebar.param_changed.connect(self.on_param_change)
        self.sidebar.action_triggered.connect(self.on_action)
        
        # 5. Initial Render
        self.app_logic.update_scene("all")
        self.plotter.reset_camera()
        
    def on_param_change(self, key, val, mode):
        logger.debug(f"Param change: {key} -> {val} ({mode})")
        self.app_logic.on_param_change(key, val, mode)
        
    def on_action(self, action_name):
        logger.info(f"Action triggered: {action_name}")
        if action_name == "save_gcode":
            self.app_logic.save_gcode(True)
        elif action_name == "run_sim":
            # PyQt simülasyonu için thread gerekebilir, şimdilik basit blocking veya timer
            # SimulationController logic'i Qt Timer ile entegre edilebilir ama 
            # şimdilik mevcut yapıyı use edelim (main loop içinde process_events vs yapan)
            self.app_logic.sim_controller.run(True, self.app_logic.path_gen.last_calculated_paths, self.app_logic.params)
        elif action_name == "stop_sim":
            self.app_logic.sim_controller.stop(True)

def main():
    # Handle Ctrl+C
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
