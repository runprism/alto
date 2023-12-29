"""
Users can run their code on cloud environments, which we call Agents. This script
contains the base class for the agent.
"""


###########
# Imports #
###########

# Internal imports
from nomad.agents.meta import MetaAgent
from nomad.entrypoints import BaseEntrypoint, Jupyter
from nomad.infras import BaseInfra
from nomad.images import BaseImage, Docker as DockerImage
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

        # Define the post-buld commands for the infrastructure
        self.define_post_build_cmds()

    def define_post_build_cmds(self):
        """
        Define actions to be performed before the code is executed. These could be
        anything, but they must be specified as a list of bash commands.

        For certain entrypoints, we use this function to augment the `post_build_cmds`
        that the user specifies, if any.
        """
        if "post_build_cmds" not in self.infra.infra_conf.keys():
            self.infra.infra_conf["post_build_cmds"] = []

        # We run this function *after* checking the infra and entrypoint
        # configuration.
        post_build_cmds = self.infra.infra_conf["post_build_cmds"]

        # For `jupyter` entrypoints, we need to install the ipython kernel.
        if isinstance(self.entrypoint, Jupyter):

            # If we're using an image, then don't do anything...the Jupyter stuff will
            # be installed in the Docker image itself.
            if isinstance(self.image, DockerImage):
                True  # do nothing
            else:
                # Technically, the user's requirements should install ipython and the
                # ipykernel, but we'll do it again here anyways.
                for cmd in [
                    "pip install ipython ipykernel papermill",
                    f'ipython kernel install --name "{self.entrypoint.kernel}" --user'
                ]:
                    if cmd not in post_build_cmds:
                        post_build_cmds.append(cmd)

        # Update the class attributes
        self.infra.infra_conf["post_build_cmds"] = post_build_cmds

    def check_conf(self, conf: Dict[str, Any]):
        return True

    def apply(self, overrides={}):
        raise ValueError("`run` method not yet implemented!")

    def run(self, overrides={}):
        raise ValueError("`run` method not yet implemented!")

    def delete(self, overrides={}):
        raise ValueError("`run` method not yet implemented!")
