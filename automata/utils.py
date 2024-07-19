import logging
import os

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)


def ensure_dir_exists(path: str, mode: int = 0o755):
    """Ensures a directory exists, creating it if necessary."""
    if not os.path.exists(path):
        LOGGER.info(f"Path: {path}. Directory does not exist. Creating directory.")
        os.makedirs(path)
        os.chmod(path, mode)
    else:
        LOGGER.debug(f"Path: {path}. Directory already exists.")
