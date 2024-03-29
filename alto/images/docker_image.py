"""
Docker Image.
"""

###########
# Imports #
###########

# Standard library imports
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union
import json
from jinja2 import Environment, FileSystemLoader
import shutil
import requests

# Alto imports
from alto.entrypoints import BaseEntrypoint
from alto.images.meta import BaseImage
from alto.config import ConfigMixin
from alto.constants import (
    DEFAULT_LOGGER_NAME,
)
import alto.ui
from alto.agents.scripts import SCRIPTS_DIR
from alto.utils import (
    paths_flattener,
    ConfigurationKey,
    _check_optional_key_in_conf
)
from alto.output import OutputManager
from alto.utils import requires_dependencies


##########
# Logger #
##########

import logging
logger = logging.getLogger(DEFAULT_LOGGER_NAME)


####################
# Class definition #
####################


class Docker(BaseImage, ConfigMixin):

    # Class
    SERVER_URL: str | None
    CLIENT: Any
    image_version: Optional[str] = None

    @requires_dependencies(
        "docker",
        "docker",
    )
    def __init__(self,
        alto_wkdir: Path,
        image_name: str,
        image_conf: Dict[str, Any],
        output_mgr: OutputManager
    ):
        # Place server URL and client inside the class definition
        import docker
        self.SERVER_URL = os.environ.get("__ALTO_DOCKER_SERVER_URL__", None)
        if self.SERVER_URL is not None:
            self.CLIENT = docker.from_env(environment={
                "DOCKER_HOST": self.SERVER_URL
            })
        else:
            self.CLIENT = docker.from_env()

        BaseImage.__init__(
            self, alto_wkdir, image_name, image_conf, output_mgr
        )

        # Image name, version
        alto_project_name = self.alto_wkdir.name.replace("_", "-")
        self.image_name = f"{alto_project_name}-{self.image_name}"

        # Create a low-level API client. We need this to capture the logs when
        # actually building the image.
        if self.SERVER_URL is not None:
            self.build_client = docker.APIClient(base_url=self.SERVER_URL)
        else:
            self.build_client = docker.APIClient(base_url=self.server_url)

        # Iterate through current images and get all images that resemble our image
        # name.
        img_list = self.CLIENT.images.list()
        self.prev_images = []
        self.prev_img_names: List[str] = []
        self.prev_img_versions: List[str] = []
        for img in img_list:
            if img.tags == []:
                continue
            else:
                for _tag in img.tags:
                    if len(re.findall(
                        self.image_name + r"\:[0-9\.]+",  # noqa: E501
                        _tag
                    )) > 0:  # noqa: E501
                        name = _tag.split(":")[0]
                        version = _tag.split(":")[1]
                        self.prev_images.append(_tag)
                        self.prev_img_names.append(name)
                        self.prev_img_versions.append(version)

        # If more than one image is found, then raise a warning and default to the
        # latest image.
        self.prev_img_versions = list(set(self.prev_img_versions))
        if len(self.prev_img_versions) > 1:

            # We need to capture the float and string formats of the image version.
            latest_version_float = max([float(x) for x in self.prev_img_versions])
            latest_version_str: str
            for v in self.prev_img_versions:
                if float(v) == latest_version_float:
                    latest_version_str = v

            # Make sure there is a corresponding image to this version. This should
            # always be the case...
            try:
                _ = self.prev_img_names[self.prev_img_versions.index(latest_version_str)]  # noqa
            except KeyError:
                raise ValueError(
                    f"could not find image associated with `{latest_version_str}`"
                )

            # Notify user that we're defaulting to the latest version
            logger.warning(
                f"More than one tag found for {self.image_name}...defaulting to {latest_version_str}"  # noqa: E501
            )
            self.image_version = latest_version_str

        # If only one image is found, then we're fine
        elif len(self.prev_img_versions) == 1:
            self.image_version = self.prev_img_versions[0]

        # Otherwise, this is the first time we're creating the docker image.
        else:
            self.image_version = None

    def check_conf(self):
        """
        Confirm that the image configuration is acceptable
        """
        super().check_conf()

        # Optional keys
        optional_keys = [
            ConfigurationKey("base", str),
            ConfigurationKey("context", str),
            ConfigurationKey("server_url", str),
        ]
        for _k in optional_keys:
            _check_optional_key_in_conf(_k, self.image_conf)

        # Docker images should either have `base` or `context`. These are mutually
        # exclusive. If the user specifies base, then we build the Dockerfile for them.
        # Otherwise, they can provide a path to the Dockerfile.
        flag_has_base = "base" in self.image_conf.keys()
        flag_has_context = "context" in self.image_conf.keys()
        if flag_has_base and flag_has_context:
            raise ValueError("\n".join([
                "`base` and `context` are mutually exclusive! Use `context` to specify a path to your own Dockerfile,",  # noqa
                "otherwise, use `base` to specify the base image you wish to use for your image"  # noqa
            ]))

        # Attributes
        if flag_has_base:
            base = self.image_conf["base"]
            if bool(re.match(r'^\s*$', base)):
                raise ValueError("`base` is blank!")
            self.base = base
            self.context = ""

        if flag_has_context:
            context = self.image_conf["context"]
            if bool(re.match(r'^\s*$', context)):
                raise ValueError("`context` is blank!")

            # Convert to a Path and check if the Dockerfile exists
            context = self.alto_wkdir / context
            if not (Path(context) / 'Dockerfile').is_file():
                raise ValueError(
                    f"`{str(Path(context / 'Dockerfile'))}` not found!"
                )
            self.context = context
            self.base = ""

        if "server_url" in self.image_conf.keys():
            server_url = self.image_conf["server_url"]
            if bool(re.match(r'^\s*$', server_url)):
                raise ValueError("`server_url` is blank!")
            self.server_url = server_url
        else:
            self.server_url = ""

    def prepare_mount_copy_cmds(self,
        docker_context_path: Path,
        alto_wkdir: Path,
        mounts: List[str],
    ) -> Dict[Union[str, Path], str]:
        """
        Prepare the `COPY` statements for the Dockerfile. Note that we don't store our
        Dockerfile as a file within the project directory. Rather, we create a folder
        called .docker_context/ and place it there. This allows us to access paths
        outside of our current working directory.

        args:
            alto_wkdir: Alto working directory
            entrypoint: agent's entrypoint
            mounts: additional paths to copy into your infrastructure
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
        all_paths = [alto_wkdir] + mounts
        flattened_paths = paths_flattener(all_paths)

        # Copy directories into tmpdir
        for full, flat in zip(all_paths, flattened_paths):
            if flat in copy_commands.keys():
                continue

            # Copy
            if Path(full).is_dir():
                shutil.copytree(
                    src=full,
                    dst=docker_context_path / flat,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(
                        *[docker_context_path.name, "requirements"]
                    )
                )
            else:
                shutil.copy2(
                    src=full,
                    dst=docker_context_path / flat,
                )

            # Add copy command
            copy_commands[flat] = f"COPY {str(flat)}/ ./{str(flat)}"

        # Return copy commands
        return copy_commands

    def docker_image_kwargs(self):
        return {}

    def build(self,
        agent_conf: Dict[str, Any],
        entrypoint: BaseEntrypoint,
        jinja_template_overrides: Dict[str, Any] = {},
        build_kwargs: Dict[str, Any] = {},
    ):
        """
        Create the Docker image
        """
        context = self.context

        # Update the version number. If there is no image, then set the first image
        # to be version 1.0
        if self.image_version is None:
            new_img_version = "1.0"
        else:
            new_img_version = str(round(float(self.image_version) + 0.1, 1))

        # If the context is not specified, then the base image must be specified. Build
        # the Dockerfile from the configuration YAML.
        if context == "":

            # requirements.txt path
            requirements_relative_path = self.parse_requirements(
                self.alto_wkdir,
                agent_conf,
                absolute=False
            )

            # Path for Dockerfile
            docker_context_path = self.alto_wkdir / '.docker_context'

            # Post-build commands
            processed_image_build_cmds = []
            raw_image_build_commands = self.parse_image_build_cmds(
                self.image_conf, entrypoint
            )
            for pbc in raw_image_build_commands:
                processed_image_build_cmds.append(f'RUN {pbc}')
            image_build_commands_dockerfile = "\n".join(processed_image_build_cmds)

            # Copy commands
            mounts = self.parse_mounts(agent_conf)
            mount_cmds = self.prepare_mount_copy_cmds(
                docker_context_path, self.alto_wkdir, mounts
            )
            mount_cmds_dockerfile = "\n".join([
                str(cmd) for _, cmd in mount_cmds.items()
            ])

            # Flattened wkdir. Save this as an attribute so we can access it using a
            # class instance.
            alto_wkdir_name = list(mount_cmds.keys())[0]
            self.workdir = alto_wkdir_name

            # Copy requirements into the docker context. If the requirements are not
            # specified, create a blank requirements.txt file in the Docker context
            if str(requirements_relative_path) != "":
                shutil.copyfile(
                    src=(self.alto_wkdir / requirements_relative_path).resolve(),
                    dst=docker_context_path / "requirements.txt",
                )
            else:
                with open(docker_context_path / "requirements.txt", 'w') as f:
                    f.write("")
            requirements_relative_path = Path("requirements.txt")
            requirements_relative_str = str(requirements_relative_path)

            # Environment dictionary
            env_dict = self.parse_environment_variables(agent_conf)
            env_dockerfile = "\n".join([f"ENV {k}={v}" for k, v in env_dict.items()])

            # Open Jinja template
            env = Environment(loader=FileSystemLoader(SCRIPTS_DIR / 'docker'))
            jinja_template = env.get_template("Dockerfile")
            rendered_template = jinja_template.render(
                base_image=jinja_template_overrides.get("base_image", self.base),
                image_build_cmds=jinja_template_overrides.get("image_build_cmds", image_build_commands_dockerfile),  # noqa
                requirements_txt=jinja_template_overrides.get("requirements_txt", requirements_relative_str),  # noqa
                alto_wkdir_name=jinja_template_overrides.get("alto_wkdir_name", alto_wkdir_name),  # noqa
                mount_cmds=jinja_template_overrides.get("mount_cmds", mount_cmds_dockerfile),  # noqa
                env=jinja_template_overrides.get("env", env_dockerfile),
                cmd=jinja_template_overrides.get("cmd", entrypoint.build_command()),  # noqa
            )

            # Write the Dockerfile
            dockerfile_path = self.alto_wkdir / ".docker_context" / "Dockerfile"
            with open(dockerfile_path, 'w') as f:
                f.write(rendered_template)
        # If a Dockerfile path is given, then just use that
        else:
            dockerfile_path = Path(context) / "Dockerfile"

        # Create image
        self.output_mgr.step_starting("[dodger_blue2]Building image[/dodger_blue2]")
        resp = self.build_client.build(
            path=str(dockerfile_path.parent),
            tag=f"{self.image_name}:{new_img_version}",
            rm=True,
            pull=True,
            **build_kwargs
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
                    self.output_mgr.log_output(
                        agent_img_name=self.image_name,
                        stage=alto.ui.StageEnum.IMAGE_BUILD,
                        level="info",
                        msg=log,
                    )

        # Remove the old image
        if self.image_version is not None:
            self.prev_images = list(set(self.prev_images))
            for img in self.prev_images:
                try:
                    self.CLIENT.images.remove(
                        image=img,
                        force=True
                    )

                # We sometimes see this because previous, deleted images are still
                # returned by the Docker API call. Ignore.
                except requests.exceptions.HTTPError:
                    continue

        self.image_version = new_img_version

        # If nothing has gone wrong, then we should be able to get the image
        try:
            _ = self.CLIENT.images.get(
                name=f"{self.image_name}:{new_img_version}",
            )
        except Exception as e:
            self.output_mgr.step_failed()
            raise e

        self.output_mgr.step_completed("Built image!")
        self.output_mgr.stop_live()

        # Push the image
        self.registry.push(
            docker_client=self.CLIENT,
            image_name=self.image_name,
            image_tag=self.image_version
        )

    def delete(self):
        """
        Delete the Docker agent
        """
        self.output_mgr.step_starting("[dodger_blue2]Deleting image[/dodger_blue2]")

        # Remove all images with the label "stage=intermediate"
        images = self.CLIENT.images.list(
            filters={"label": "stage=intermediate"}
        )
        for img in images:
            if len(img.tags) > 0:
                for curr_tag in img.tags:
                    if self.image_name in curr_tag and self.image_version in curr_tag:
                        try:
                            self.CLIENT.images.remove(
                                image=curr_tag,
                                force=True,
                            )
                            self.output_mgr.log_output(
                                agent_img_name=self.image_name,
                                stage=alto.ui.StageEnum.AGENT_DELETE,
                                level="info",
                                msg=f"Deleting image {alto.ui.MAGENTA}{curr_tag}{alto.ui.RESET}",  # noqa
                            )

                        # Just in case...
                        except requests.exceptions.HTTPError:
                            continue
        self.output_mgr.step_completed("Deleted image!")
