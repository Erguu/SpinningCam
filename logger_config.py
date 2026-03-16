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
        
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG) # File sees everything
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        logger.info(f"Logging initialized. Log file: {log_file}")
    except Exception as e:
        print(f"FAILED TO SETUP FILE LOGGING: {e}")

    return logger

# Create a default instance for easy import
logger = setup_logger()
