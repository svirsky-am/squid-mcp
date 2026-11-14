import logging
import sys
from pathlib import Path
from src.config import AppConfig

def get_logger(name: str) -> logging.Logger:
    config = AppConfig()
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = config.logs_dir / "msp_service.log"
    
    logger = logging.getLogger(name)
    
    if not logger.hasHandlers():
        logger.setLevel(logging.INFO)
        
        # File handler
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(logging.INFO)
        
        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        logger.addHandler(fh)
        logger.addHandler(ch)
        
    return logger