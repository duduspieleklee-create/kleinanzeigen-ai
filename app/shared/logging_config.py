import logging
import sys
from logging.handlers import RotatingFileHandler
import os

def setup_logging():
    """
    Centralized logging configuration for kleinanzeigen-ai.
    Suitable for Milestone 1 (simple but effective).
    """

    # Create logs directory if it doesn't exist
    log_dir = "/tmp/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Define log format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Create formatter
    formatter = logging.Formatter(log_format)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (rotating logs)
    file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,   # 10 MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Reduce noise from some libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    return logging.getLogger("kleinanzeigen-ai")


# Create logger instance
logger = setup_logging()
