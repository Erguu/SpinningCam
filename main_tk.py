import sys
import logging
from ui.main_window import SpinningCamWindow

# Setup Logging
logging.basicConfig(
    filename='spinning_cam.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("SpinningCam")

if __name__ == "__main__":
    app = SpinningCamWindow()
    app.mainloop()
