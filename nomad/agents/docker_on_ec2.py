"""
Docker Agent.
"""


###########
# Imports #
###########


# Standard library imports
import argparse
import docker
from pathlib import Path
import re
from typing import Any, Dict

# Nomad imports
from nomad.agents.ec2 import Ec2
from nomad.agents.docker_agent import Docker, SERVER_URL
from nomad.entrypoints import BaseEntrypoint
from nomad.infras import BaseInfra
from nomad.constants import (
    DEFAULT_LOGGER_NAME
)
import nomad.ui
from nomad.agents.scripts import SCRIPTS_DIR
from nomad.registries import BaseRegistry

##########
# Logger #
##########

import logging
logger = logging.getLogger(DEFAULT_LOGGER_NAME)


#################
# Docker client #
#################

# For testing
if SERVER_URL is not None:
    client = docker.from_env(environment={
        "DOCKER_HOST": SERVER_URL
    })
else:
    client = docker.from_env()


####################
# Class definition #
####################

class DockerOnEc2(Docker, Ec2):

    def __init__(self,
        args: argparse.Namespace,
        nomad_wkdir: Path,
        agent_name: str,
        agent_conf: Dict[str, Any],
        infra: BaseInfra,
        entrypoint: BaseEntrypoint,
        mode: str = "prod"
    ):
        # Initialize the Docker and EC2 agents
        Docker.__init__(
            self, args, nomad_wkdir, agent_name, agent_conf, infra, entrypoint, mode
        )
        Ec2.__init__(
            self, args, nomad_wkdir, agent_name, agent_conf, infra, entrypoint, mode
        )

        # Set scripts paths
        self.set_scripts_paths(
            apply_script=SCRIPTS_DIR / "docker-on-ec2" / "apply.sh",
            run_script=SCRIPTS_DIR / "docker-on-ec2" / "run.sh"
        )

    def define_accepted_apply_optargs(self):
        """
        Define accepted optargs for the `apply` command
        """
        return ['-p', '-u', '-n']

    def define_additional_apply_optargs(self):
        """
        Define accepted optargs for the `apply` command
        """
        registry: BaseRegistry = self.infra.registry  # type: ignore
        username = registry.registry_conf["registry_creds"]["username"]  # type: ignore
        password = registry.registry_conf["registry_creds"]["password"]  # type: ignore
        return {
            '-a': username,
            '-z': password,
            '-r': self.infra.infra_conf["registry"]
        }

    def apply(self, overrides={}):
        """
        Create the Docker image
        """
        # First, create the Docker image
        Docker.apply(
            self,
            overrides={
                "other_build_cmds": "",
            }
        )

        # Next, push the Docker image to ECR
        if not hasattr(self.infra, "registry"):
            raise ValueError("could not find `registry` attribute")
        registry: BaseRegistry = self.infra.registry
        registry.push(
            docker_client=client,
            image_name=self.image_name,
            image_tag=self.image_version
        )

        # Finally, create the EC2 instance and pull the Docker image
        returncode = Ec2.apply(self)
        return returncode

    def run(self, overrides={}):
        """
        Run the project using the Docker agent
        """

        # Run container
        container = client.containers.run(
            f"{self.image_name}:{self.image_version}",
            detach=True,
            stdout=True,
            remove=True,
        )

        # Get the container logs
        container = client.containers.get(container_id=container.id)
        for log in container.logs(stream=True, stdout=True, stderr=True):
            log_str = log.decode('utf-8')
            no_newline = log_str.replace("\n", "")
            if not re.findall(r"^[\-]+$", no_newline):
                logger.info(  # type: ignore
                    f"{nomad.ui.AGENT_EVENT}{self.image_name}:{self.image_version}{nomad.ui.AGENT_WHICH_RUN}[run]  {nomad.ui.RESET} | {no_newline}"  # noqa: E501
                )
        return 0

    def delete(self, overrides={}):
        """
        Delete the Docker agent
        """
        Docker.delete(self, overrides)
        Ec2.delete(self, overrides)
