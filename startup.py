import sys
import os
import logging
from logging.handlers import RotatingFileHandler


app_wd = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

log_dir = os.path.join(app_wd, "log")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
log_file = os.path.join(log_dir, "app.log")
logging.basicConfig(
    format="%(asctime)s %(message)s",
    handlers=[
        RotatingFileHandler(filename=log_file, mode="w", maxBytes=1024 * 1024, backupCount=50, encoding="UTF-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
