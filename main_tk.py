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
    # Packaging self-test: proves a frozen build is complete without opening the GUI.
    # Used by check_packaging.py --post-build (see packaging_manifest.run_selfcheck).
    if "--selfcheck" in sys.argv:
        from packaging_manifest import run_selfcheck
        sys.exit(run_selfcheck())

    app = SpinningCamWindow()
    app.mainloop()
