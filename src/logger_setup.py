import logging
import sys
from app_config import AppConfig

def setup_logger(config: AppConfig) -> logging.Logger:
    logger = logging.getLogger("wb_msp")
    logger.setLevel(logging.INFO)
    
    log_file = config.logs_dir / "service.log"
    fh = logging.FileHandler(log_file, encoding='utf-8')
    ch = logging.StreamHandler(sys.stdout)
    
    formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(ch)
        
    return logger