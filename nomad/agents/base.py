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
from nomad.infras import BaseInfra
from nomad.images import BaseImage
from nomad.config import ConfigMixin

# Standard library imports
import argparse
from typing import Any, Dict, Optional
from pathlib import Path


####################
# Class definition #
####################

class Agent(ConfigMixin, metaclass=MetaAgent):
    """
    Base Agent class
    """

    def __init__(self,
        args: argparse.Namespace,
        nomad_wkdir: Path,
        agent_name: str,
        agent_conf: Dict[str, Any],
        infra: BaseInfra,
        entrypoint: BaseEntrypoint,
        image: Optional[BaseImage],
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
        self.infra = infra
        self.entrypoint = entrypoint
        self.image: Optional[BaseImage] = image

        # Check the configuration
        self.check_conf(self.agent_conf)

    def check_conf(self, conf: Dict[str, Any]):
        return True

    def apply(self, overrides={}):
        raise ValueError("`run` method not yet implemented!")

    def run(self, overrides={}):
        raise ValueError("`run` method not yet implemented!")

    def delete(self, overrides={}):
        raise ValueError("`run` method not yet implemented!")
