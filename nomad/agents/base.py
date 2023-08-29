"""
Users can run their code on cloud environments, which we call Agents. This script
contains the base class for the agent.
"""


###########
# Imports #
###########

# Internal imports
from nomad.agents.meta import MetaAgent
from nomad.entrypoints import BaseEntrypoint

# Standard library imports
import argparse
from typing import Any, Dict
from pathlib import Path


####################
# Class definition #
####################

class Agent(metaclass=MetaAgent):
    """
    The `agents.yml` file will be formatted as follows:

    agents:
      <agent name here>:
        type: docker
        ...
    """

    def __init__(self,
        args: argparse.Namespace,
        nomad_wkdir: Path,
        agent_name: str,
        agent_conf: Dict[str, Any],
        entrypoint: BaseEntrypoint,
        mode: str = "prod"
    ):
        """
        Create agent

        args:
            args: user arguments
            agent_conf: agent configuration as a dictionary
            mode: either `prod` of `test`. This allows us to test agents without
                instantiating cloud resources
        """
        self.args = args
        self.nomad_wkdir = nomad_wkdir
        self.agent_name = agent_name
        self.agent_conf = agent_conf
        self.entrypoint = entrypoint

        # Check the configuration
        self.check_conf(self.agent_conf)

    def check_conf(self, conf: Dict[str, Any]):
        return True

    def parse_requirements(self, agent_conf: Dict[str, Any]):
        """
        Get the requirements.txt path and construct the pip install statement.

        args:
            agent_conf: agent configuration as dictionary
        returns:
            requirements path
        """
        # Not all Nomad projects will have a `requirements` file.
        if "requirements" not in agent_conf.keys():
            return ""

        # We already know that the agent configuration is valid. Therefore, it must have
        # a requirements key.
        requirements = agent_conf["requirements"]

        # The `requirements.txt` path should always be specified relative to the
        # directory of the Nomad configuration file.
        absolute_requirements_path = Path(self.nomad_wkdir / requirements).resolve()

        # Check if this file exists
        if not absolute_requirements_path.is_file():
            raise ValueError(f"no file found at {absolute_requirements_path}")
        return absolute_requirements_path

    def parse_post_build_cmds(self, agent_conf: Dict[str, Any]):
        """
        Get the post-build commands for the cloud environment

        args:
            agent_conf: agent configuration as dictionary
        returns:
            post-build cmds as a list. If no post-build commands are specified, then
            return an empty list.
        """
        # Not all Nomad projects will have a `requirements` file.
        if "post_build_cmds" not in agent_conf.keys():
            return []
        post_build_cmds = agent_conf["post_build_cmds"]
        return post_build_cmds

    def parse_download_files(self, agent_conf: Dict[str, Any]):
        """
        Get the files to download from the cloud environment

        args:
            agent_conf: agent configuration as dictionary
        returns:
            files to donwload as a list. If no download files are specified, then
            return an empty list.
        """
        # Not all Nomad projects will have a `requirements` file.
        if "download_files" not in agent_conf.keys():
            return []
        download_files = agent_conf["download_files"]
        return download_files

    def apply(self):
        raise ValueError("`run` method not yet implemented!")

    def run(self):
        raise ValueError("`run` method not yet implemented!")

    def delete(self):
        raise ValueError("`run` method not yet implemented!")
