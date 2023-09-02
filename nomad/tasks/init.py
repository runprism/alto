"""
Task called via the `nomad init` CLI command
"""

# Imports
import argparse
import yaml
from pathlib import Path
import logging

# Internal imports
from nomad.templates import TEMPLATES_DIR
from nomad.nomad_logger import (
    set_up_logger
)
from nomad.constants import DEFAULT_LOGGER_NAME
from nomad.ui import (
    BRIGHT_GREEN,
    RESET,
)


# Class definition
class InitTask:

    def __init__(self,
        args: argparse.Namespace,
    ):
        self.args = args
        self.nomad_wkdir = Path(self.args.wkdir)

        # Set up logger
        set_up_logger(self.args.log_level)

    def run(self):
        """
        Create a configuration file in the user's current working directory
        """
        DEFAULT_LOGGER = logging.getLogger(DEFAULT_LOGGER_NAME)

        # Grab args
        agent_type = self.args.type
        filename = self.args.file

        # Log
        DEFAULT_LOGGER.info("Building configuration file...")

        # Check if the file exists. If it does, throw an error
        if Path(self.nomad_wkdir / filename).is_file():
            raise ValueError(f"`{Path(self.nomad_wkdir / filename)}` already exists!")

        # Grab the template associated with `type` and write it to the appropriate
        # filename.
        with open(TEMPLATES_DIR / f"{agent_type}.yml", 'r') as f:
            template = yaml.safe_load(f)
        with open(self.nomad_wkdir / filename, 'w') as f:
            yaml.safe_dump(template, f, sort_keys=False)

        DEFAULT_LOGGER.info(f"{BRIGHT_GREEN}Done!{RESET}")
        return 0