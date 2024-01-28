"""
Dividers used in Alto's logging
"""

import alto.ui

# Constants
LOG_DIVIDERS = [
    "image",
    "push",
    "build",
    "delete",
    "run",
]
MAX_LENGTH = max([len(x) for x in LOG_DIVIDERS])


# Class
class Divider:

    def __init__(self, divider: str):
        self.divider = divider

    def __str__(self) -> str:
        return f"{alto.ui.BOLD}[{self.divider}]" + " " * ((MAX_LENGTH + 1) - len(self.divider))  # noqa
