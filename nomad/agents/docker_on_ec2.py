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
from typing import Any, Dict

# Nomad imports
from nomad.agents.ec2 import Ec2
from nomad.agents.docker_agent import Docker, SERVER_URL
from nomad.entrypoints import BaseEntrypoint
from nomad.infras import BaseInfra
from nomad.constants import (
    DEFAULT_LOGGER_NAME
)
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

    def set_apply_command_attributes(self):
        """
        Set the acceptable apply command parameters
        """
        super().set_apply_command_attributes()

        # Accepted optargs
        self.apply_command.set_accepted_apply_optargs(['-p', '-u', '-n'])

        # Additional optargs. Note that this function is called AFTER we push our image
        # to our registry, so our registry configuration should have all the information
        # we need.
        registry: BaseRegistry = self.infra.registry  # type: ignore
        username = registry.registry_conf["registry_creds"]["username"]  # type: ignore
        password = registry.registry_conf["registry_creds"]["password"]  # type: ignore
        additional_optargs = {
            '-a': username,
            '-z': password,
            '-r': self.infra.infra_conf["registry"],
            '-i': f"{self.image_name}:{self.image_version}"
        }
        self.apply_command.set_additional_optargs(additional_optargs)

    def set_run_command_attributes(self):
        """
        Set the acceptable run command parameters
        """
        super().set_run_command_attributes()

        # Accepted optargs
        self.run_command.set_accepted_apply_optargs(['-p', '-u', '-n'])

        # Additional optargs
        registry_obj: BaseRegistry = self.infra.registry
        registry, username, password = registry_obj.get_login_info()
        additional_optargs = {
            '-a': username,
            '-z': password,
            '-r': registry,
            '-i': f"{self.image_name}:{self.image_version}"
        }
        self.run_command.set_additional_optargs(additional_optargs)

    def docker_image_kwargs(self):
        return {"platform": "linux/amd64"}

    def apply(self, overrides={}):
        """
        Create the Docker image, push it to the registry, and then build the EC2
        instance.
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
        Run the Docker image on the EC2 instance.
        """
        returncode = Ec2.run(self)
        return returncode

    def delete(self, overrides={}):
        """
        Delete the Docker agent
        """
        Docker.delete(self, overrides)
        Ec2.delete(self, overrides)
