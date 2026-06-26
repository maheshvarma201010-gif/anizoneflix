import logging
import sys

def setup_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(handler)

    return logger

# Global loggers
bot_logger = setup_logger("BOT")
userbot_logger = setup_logger("USERBOT")
forwarder_logger = setup_logger("FORWARDER")
database_logger = setup_logger("DATABASE")
