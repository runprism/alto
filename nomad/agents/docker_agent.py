"""
Docker Agent.
"""


###########
# Imports #
###########


# Standard library imports
import argparse
import docker
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union
import json
from jinja2 import Environment, FileSystemLoader
import shutil
import requests

# Nomad imports
from nomad.agents.base import Agent
from nomad.entrypoints import BaseEntrypoint
from nomad.infras import BaseInfra
from nomad.constants import (
    DEFAULT_LOGGER_NAME
)
import nomad.ui
from nomad.agents.scripts import SCRIPTS_DIR
from nomad.utils import paths_flattener


##########
# Logger #
##########

import logging
logger = logging.getLogger(DEFAULT_LOGGER_NAME)


#################
# Docker client #
#################

# For testing
SERVER_URL = os.environ.get("__NOMAD_DOCKER_SERVER_URL__", None)
if SERVER_URL is not None:
    client = docker.from_env(environment={
        "DOCKER_HOST": SERVER_URL
    })
else:
    client = docker.from_env()


####################
# Class definition #
####################

class Docker(Agent):

    def __init__(self,
        args: argparse.Namespace,
        nomad_wkdir: Path,
        agent_name: str,
        agent_conf: Dict[str, Any],
        infra: BaseInfra,
        entrypoint: BaseEntrypoint,
        mode: str = "prod"
    ):
        Agent.__init__(
            self, args, nomad_wkdir, agent_name, agent_conf, infra, entrypoint, mode
        )

        if mode == "prod":
            # Image name, version
            nomad_project_name = self.nomad_wkdir.name.replace("_", "-")
            self.image_name = f"{nomad_project_name}-{self.agent_name}"
            self.image_version: Optional[str] = None

            # Create a low-level API client. We need this to capture the logs when
            # actually building the image.
            if SERVER_URL is not None:
                self.build_client = docker.APIClient(base_url=SERVER_URL)
            else:
                server_url = self.parse_infra_key(self.infra.infra_conf, "server_url")
                self.build_client = docker.APIClient(base_url=server_url)

            # Iterate through current images and get all images that resemble our image
            # name.
            img_list = client.images.list()
            img_names = []
            img_versions = []
            for img in img_list:
                if img.tags == []:
                    continue
                else:
                    for _tag in img.tags:
                        if len(re.findall(
                            r"^" + nomad_project_name + r"\-" + self.agent_name + r"\:[0-9\.]+$",  # noqa: E501
                            _tag
                        )) > 0:  # noqa: E501
                            name = _tag.split(":")[0]
                            version = _tag.split(":")[1]
                            img_names.append(name)
                            img_versions.append(version)

            # If more than one image is found, then raise a warning and default to the
            # latest image.
            if len(img_versions) > 1:

                # We need to capture the float and string formats of the image version.
                latest_version_float = max([float(x) for x in img_versions])
                latest_version_str: str
                for v in img_versions:
                    if float(v) == latest_version_float:
                        latest_version_str = v

                # Make sure there is a corresponding image to this version. This should
                # always be the case...
                try:
                    _ = img_names[img_versions.index(latest_version_str)]
                except KeyError:
                    raise ValueError(
                        f"could not find image associated with `{latest_version_str}`"
                    )

                # Notify user that we're defaulting to the latest version
                logger.warning(
                    f"More than one agent found like {self.image_name}...defaulting to {latest_version_str}"  # noqa: E501
                )
                self.image_version = latest_version_str

            # If only one image is found, then we're fine
            elif len(img_versions) == 1:
                self.image_version = img_versions[0]

            # Otherwise, this is the first time we're creating the docker image.
            else:
                self.image_version = None

    def prepare_copy_commands(self,
        docker_context_path: Path,
        nomad_wkdir: Path,
        additional_paths: List[str],
    ) -> Dict[Union[str, Path], str]:
        """
        Prepare the `COPY` statements for the Dockerfile. Note that we don't store our
        Dockerfile as a file within the project directory. Rather, we create a folder
        called .docker_context/ and place it there. This allows us to access paths
        outside of our current working directory.

        args:
            nomad_wkdir: Nomad working directory
            entrypoint: agent's entrypoint
            additional_paths: additional paths to copy into your infrastructure
        returns:
            list of COPY statements
        """
        # Docker context folder
        if docker_context_path.is_dir():
            shutil.rmtree(docker_context_path)
        docker_context_path.mkdir()

        # Copy commands
        copy_commands: Dict[Union[str, Path], str] = {}

        # Flatten the list of paths
        all_paths = [nomad_wkdir] + additional_paths
        flattened_paths = paths_flattener(all_paths)

        # Copy directories into tmpdir
        for full, flat in zip(all_paths, flattened_paths):
            if flat in copy_commands.keys():
                continue

            # Copy
            shutil.copytree(
                src=full,
                dst=docker_context_path / flat,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(*[docker_context_path.name])
            )

            # Add copy command
            copy_commands[flat] = f"COPY {str(flat)}/ ./{str(flat)}"

        # Return copy commands
        return copy_commands

    def docker_image_kwargs(self):
        return {}

    def apply(self, overrides={}):
        """
        Create the Docker image
        """
        # Infra
        base_image = self.parse_infra_key(self.infra.infra_conf, "base_image")

        # requirements.txt path
        requirements_relative_path = self.parse_requirements(
            self.agent_conf,
            absolute=False
        )
        requirements_relative_str = str(requirements_relative_path)

        # Post-build commands
        processed_other_build_commands = []
        raw_other_build_commands = self.parse_post_build_cmds(self.agent_conf)
        for pbc in raw_other_build_commands:
            processed_other_build_commands.append(f'RUN {pbc}')
        other_build_cmds_dockerfile = "\n".join(processed_other_build_commands)

        # Copy commands
        docker_context_path = self.nomad_wkdir / '.docker_context'
        additional_paths = self.parse_additional_paths(self.agent_conf)
        copy_commands = self.prepare_copy_commands(
            docker_context_path, self.nomad_wkdir, additional_paths
        )
        copy_commands_dockerfile = "\n".join([
            str(cmd) for _, cmd in copy_commands.items()
        ])

        # Copy requirements into the docker context
        shutil.copy(
            src=self.nomad_wkdir / requirements_relative_path,
            dst=docker_context_path / "requirements.txt",
        )

        # Environment dictionary
        env_dict = self.parse_environment_variables(self.agent_conf)
        env_dockerfile = "\n".join([f"ENV {k}={v}" for k, v in env_dict.items()])

        # Update the version number. If there is no image, then set the first image to
        # be version 1.0
        if self.image_version is None:
            new_img_version = "1.0"
        else:
            new_img_version = str(round(float(self.image_version) + 0.1, 1))

        # Open Jinja template
        env = Environment(loader=FileSystemLoader(SCRIPTS_DIR / 'docker'))
        jinja_template = env.get_template("Dockerfile")
        rendered_template = jinja_template.render(
            base_image=overrides.get("base_image", base_image),
            other_build_cmds=overrides.get("other_build_cmds", other_build_cmds_dockerfile),  # noqa
            requirements_txt=overrides.get("requirements_txt", requirements_relative_str),  # noqa
            nomad_wkdir_name=overrides.get("nomad_wkdir_name", self.nomad_wkdir.name),
            copy_commands=overrides.get("copy_commands", copy_commands_dockerfile),
            env=overrides.get("env", env_dockerfile),
            cmd=overrides.get("cmd", self.entrypoint.build_command()),
        )

        # Write the Dockerfile
        dockerfile_path = self.nomad_wkdir / ".docker_context" / "Dockerfile"
        with open(dockerfile_path, 'w') as f:
            f.write(rendered_template)

        # Create image
        resp = self.build_client.build(
            path=str(dockerfile_path.parent),
            tag=f"{self.image_name}:{new_img_version}",
            rm=True,
            pull=True,
            **self.docker_image_kwargs()
        )
        for _l in resp:
            _l_str = _l.decode('utf-8').strip('\r\n')
            streams = _l_str.split('\n')
            for stm in streams:
                if "stream" in stm:
                    log = json.loads(
                        stm.replace('\r', '').replace('\\n', '')
                    )["stream"]
                    if len(re.findall(r'^\s*$', log)) > 0:
                        continue
                    logger.info(
                        f"{nomad.ui.AGENT_EVENT}{self.image_name}:{new_img_version}{nomad.ui.AGENT_WHICH_BUILD}[build]{nomad.ui.RESET} | {log}"  # noqa: E501
                    )

        # Remove the old image
        if self.image_version is not None:
            client.images.remove(
                image=f"{self.image_name}:{self.image_version}",
                force=True
            )
        self.image_version = new_img_version

        # If nothing has gone wrong, then we should be able to get the image
        _ = client.images.get(
            name=f"{self.image_name}:{new_img_version}",
        )

    def run(self, overiddes={}):
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
        log_prefix = f"{nomad.ui.AGENT_EVENT}{self.image_name}:{self.image_version}{nomad.ui.RED}[delete]{nomad.ui.RESET}"  # noqa: E501

        # Remove all images with the label "stage=intermediate"
        images = client.images.list(
            filters={"label": "stage=intermediate"}
        )
        for img in images:
            if len(img.tags) > 0:
                for curr_tag in img.tags:
                    if self.image_name in curr_tag and self.image_version in curr_tag:
                        try:
                            client.images.remove(
                                image=curr_tag,
                                force=True,
                            )
                            logger.info(
                                f"{log_prefix} | Deleting image {nomad.ui.MAGENTA}{curr_tag}{nomad.ui.RESET}"  # noqa: E501
                            )

                        # Just in case...
                        except requests.exceptions.HTTPError:
                            continue
