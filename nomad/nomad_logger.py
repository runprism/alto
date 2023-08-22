"""
Custom logger for Nomad project
"""

# Imports
import re
import copy
import logging
from nomad.ui import (
    CYAN,
    YELLOW,
    RED,
    ORANGE_BROWN,
    RESET,
)
from io import StringIO
from typing import Optional

# Internal imports
from nomad.constants import DEFAULT_LOGGER_NAME


# Logger
DEFAULT_LOGGER = logging.getLogger(DEFAULT_LOGGER_NAME)


# Functions
def escape_ansi(string: str) -> str:
    """
    Replace ANSI escape codes with ''

    args:
        string: string containing ANSI codes
    returns:
        inputted string without ANSI codes
    """
    ansi_regex = re.compile('\x1b[^m]*m')
    return ansi_regex.sub('', string)


def custom_ljust(string: str, width: int, char: str) -> str:
    """
    Python's native `ljust` does not account for ANSI escape codes; create a custom
    ljust function for the console output.

    args:
        string: string to ljust
        width: width for ljust
        char: character to use for ljust
    returns:
        ljust applied input string after ignoring ANSI escape codes
    """
    # Regex pattern for ANSI codes
    ansi_regex = re.compile('\x1b[^m]*m')

    # ANSI matches
    matches = [(m.start(), m.end()) for m in re.finditer(ansi_regex, string)]

    # Replace ANSI matches with ''
    string_with_ansi_replaced = ansi_regex.sub('', string)

    # ljust
    string_ljust = string_with_ansi_replaced.ljust(width, char)

    # Add ANSI characters back in
    string_ljust_with_ansi = copy.deepcopy(string_ljust)
    for match in matches:
        start = match[0]
        end = match[1]
        string_ljust_with_ansi = string_ljust_with_ansi[:start] + \
            string[start:end] + \
            string_ljust_with_ansi[start:]
    return string_ljust_with_ansi


# Formatting class
class FormatterWithAnsi(logging.Formatter):

    logging_format = "%(asctime)s | {color}{level}{reset} | %(message)s"
    logging_notset_format = "%(message)s"

    FORMATS = {
        logging.INFO: logging_format.format(color=CYAN, level="INFO ", reset=RESET),
        logging.WARNING: logging_format.format(color=YELLOW, level="WARN ", reset=RESET),  # noqa: E501
        logging.ERROR: logging_format.format(color=RED, level="ERROR", reset=RESET),
        logging.DEBUG: logging_format.format(
            color=ORANGE_BROWN, level="DEBUG", reset=RESET
        ),
        logging.NOTSET: logging_notset_format,
    }

    def format(self, record):
        # For empty lines / separator events, don't have any formatting
        if re.findall(r"^[\-\s]+$", record.msg):
            formatter = logging.Formatter("%(message)s")
            return formatter.format(record)

        # Otherwise, adjust the formatting based on the level
        else:
            log_fmt = self.FORMATS.get(record.levelno)
            formatter = logging.Formatter(log_fmt, "%H:%M:%S")
            return formatter.format(record)


class StringHandlerFormatter(FormatterWithAnsi):
    def format(self, record):
        return escape_ansi(super().format(record))


# String handler
STRING_STREAMER = StringIO()
STRING_STREAM_HANDLER = logging.StreamHandler(stream=STRING_STREAMER)
STRING_STREAM_HANDLER.setFormatter(StringHandlerFormatter())


def set_up_logger(
    log_level: Optional[str],
    logger: logging.Logger = DEFAULT_LOGGER
):
    """
    Set up the logger
    """
    def _set_level(obj, level: Optional[str]):
        if level == 'info':
            obj.setLevel(logging.INFO)
        elif level == 'warn':
            obj.setLevel(logging.WARN)
        elif level == 'error':
            obj.setLevel(logging.ERROR)
        elif level == 'debug':
            obj.setLevel(logging.DEBUG)
        else:
            obj.setLevel(logging.NOTSET)
        return obj

    # Set the appropriate log level
    logger = _set_level(logger, log_level)

    # Stream handler
    handler = logging.StreamHandler()
    handler = _set_level(handler, log_level)
    handler.setFormatter(FormatterWithAnsi())

    # Add handlers
    logger.addHandler(handler)
    logger.addHandler(STRING_STREAM_HANDLER)
