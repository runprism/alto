"""
UI for logging events
"""

from enum import Enum
from typing import Final
from dataclasses import dataclass


####################
# ANSI color codes #
####################

BLACK = "\u001b[30m"
RED = "\u001b[31m"
GREEN = "\u001b[32m"
YELLOW = "\u001b[33m"
DARK_BLUE = "\u001b[34m"
BLUE = "\u001b[38;5;69m"
PURPLE = "\u001b[38;5;99m"
MAGENTA = "\u001b[38;5;213m"
CYAN = "\u001b[36m"
WHITE = "\u001b[37m"
RESET = "\u001b[0m"
BRIGHT_WHITE = "\u001b[37;1m"
BRIGHT_YELLOW = "\u001b[33;1m"
BRIGHT_GREEN = "\u001b[32;1m"
BOLD = "\u001b[1m"
HEADER_GRAY = "\u001b[0m"
GRAY_PINK = "\u001b[38;5;96m"
ORANGE_BROWN = "\u001b[38;5;180m"
ORANGE = "\u001b[38;5;208m"
GRAY = "\u001b[38;5;232m"

# Event colors
EVENT_COLOR = "\u001b[38;5;103m"

# Image colors
IMAGE_EVENT = "\u001b[38;5;75m"
IMAGE_PUSH_EVENT = "\u001b[38;5;147m"

# Agent colors
AGENT_EVENT = "\u001b[37m"
AGENT_WHICH_BUILD = "\u001b[38;5;178m"
AGENT_WHICH_RUN = "\u001b[38;5;10m"


###########
# Classes #
###########

LOG_DIVIDERS = [
    "image",
    "push",
    "build",
    "delete",
    "run",
]
MAX_LENGTH = max([len(x) for x in LOG_DIVIDERS])


class Divider:

    def __init__(self, divider: str):
        self.divider = divider

    def __str__(self) -> str:
        return f"{BOLD}[{self.divider}]" + " " * ((MAX_LENGTH + 1) - len(self.divider))


class UiEvent(str, Enum):
    IMAGE_BUILD: Final = "\u001b[38;5;75m"
    IMAGE_PUSH: Final = "\u001b[38;5;147m"
    AGENT_BUILD: Final = "\u001b[38;5;178m"
    AGENT_RUN: Final = "\u001b[38;5;10m"
    AGENT_DELETE: Final = "\u001b[31m"


@dataclass
class Stage:
    name: str
    event: UiEvent

    def __str__(self) -> str:
        divider: Divider = Divider(self.name)
        return f"{self.event}{divider.__str__()}{RESET}"


class StageEnum(str, Enum):
    IMAGE_BUILD: Final = Stage("image", UiEvent.IMAGE_BUILD).__str__()
    IMAGE_PUSH: Final = Stage("push", UiEvent.IMAGE_PUSH).__str__()
    AGENT_BUILD: Final = Stage("build", UiEvent.AGENT_BUILD).__str__()
    AGENT_RUN: Final = Stage("run", UiEvent.AGENT_RUN).__str__()
    AGENT_DELETE: Final = Stage("delete", UiEvent.AGENT_DELETE).__str__()


##################
# Terminal width #
##################

TERMINAL_WIDTH = 80
