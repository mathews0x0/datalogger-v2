import logging
import sys

class CustomAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        data = kwargs.pop('data', {})
        if data:
            msg = f"{msg} | Data: {data}"
        return msg, kwargs

def get_logger(name: str):
    """
    Get a configured logger instance (Adapter).
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)
    
    return CustomAdapter(logger, {})
