import logging
import sys
import os

def setup_logger(name="SpinningCam"):
    """
    Configures and returns a dedicated logger for the SpinningCam application.
    Handlers:
      - Console (stdout)
      - File ('spinning_cam.log')
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Capture everything, handlers will filter
    
    # Avoid duplicate handlers if setup is called multiple times
    if logger.handlers:
        return logger

    # Format
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')

    # 1. Console Handler
    # Turkish Windows consoles are cp1254 and cannot encode θ/→/° used in the
    # PARAM_DEBUG messages; without 'replace' every such log line dumps a full
    # UnicodeEncodeError traceback to stderr (dozens per path calculation).
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO) # Console sees INFO and above
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. File Handler
    try:
        # Determine log path (next to executable or script)
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
            
        log_file = os.path.join(base_path, "spinning_cam.log")

        # Keep the PREVIOUS session before truncating this one.
        #
        # mode='w' wipes the log at every launch. That is fine while developing
        # and useless in the field: an operator who hits a fault, closes the
        # program, and reopens it to send a report has already destroyed the
        # only record of the fault. One generation back is enough — the fault
        # and the report are almost always adjacent runs — and it keeps the disk
        # cost bounded at two files with no rotation policy to get wrong.
        prev_file = os.path.join(base_path, "spinning_cam.prev.log")
        rotate_error = None
        try:
            if os.path.exists(log_file):
                if os.path.exists(prev_file):
                    os.remove(prev_file)
                os.replace(log_file, prev_file)
        except OSError as e:
            # A second instance holding the file open, or a read-only folder.
            # Losing the previous log is a nuisance; failing to start is not
            # acceptable, so carry on and let mode='w' truncate as before.
            # Reported through the logger below rather than printed: this fires
            # for every concurrent process (the test suite, a second app
            # window), and a warning on stdout in those runs is pure noise.
            rotate_error = e

        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG) # File sees everything
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info(f"Logging initialized. Log file: {log_file}")
        if rotate_error is not None:
            logger.debug(f"Previous log not kept: {rotate_error}")
    except Exception as e:
        print(f"FAILED TO SETUP FILE LOGGING: {e}")

    return logger

# Create a default instance for easy import
logger = setup_logger()
