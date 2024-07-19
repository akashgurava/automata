import os
from typing import IO
from loguru import logger
from datetime import datetime
import sys

# Configure logger to write to both console and file
logger.remove()  # Remove the default handler
logger.add(sys.stderr, level="INFO")  # Add a handler for console output


def ensure_dir_exists(path: str, mode: int = 0o755):
    """
    Ensures a directory exists.
    If the directory does not exist creates it with permissions.
    """
    if not os.path.exists(path):
        logger.info(f"Path: {path}. Directory does not exist. Creating directory.")
        os.makedirs(path)
        os.chmod(path, mode)
    else:
        logger.debug(f"Path: {path}. Directory already exists.")


ensure_dir_exists("./logs")

# Generate the log filename with current timestamp
log_filename = f"./logs/run_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logger.add(log_filename, level="DEBUG")  # Add a handler for file output

logger.info("Log File: {}. Writing logs.", log_filename)


def log_subprocess_output(pipe: IO[bytes]) -> None:
    """
    Reads output from a subprocess pipe and logs each line at DEBUG level.

    This function is designed to be used with subprocess.Popen output pipes
    (stdout and stderr). It reads the pipe line by line and logs each line
    using the logger at DEBUG level, which in the current configuration
    will only write to the log file, not to the console.

    Args:
        pipe (IO[bytes]): A file-like object representing the subprocess pipe
                          (typically subprocess.Popen.stdout or subprocess.Popen.stderr)

    Note:
        This function assumes that the global 'logger' object is already configured
        and available in the scope where this function is called.
    """
    for line in iter(pipe.readline, b""):  # b'' is an empty byte string
        logger.debug(line.decode().strip())
