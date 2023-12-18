"""
Registry class. Registries allow us to push our Docker images to various cloud
repositories. People primarily use ECR and Dockerhub, but others definitely exist. We
create this class to enable maximum flexibility.
"""

# Imports
import boto3
import click
from pathlib import Path
from typing import Any, Dict, Union, Optional
from botocore.exceptions import NoCredentialsError
import base64
import re

# Internal imports
from nomad.constants import (
    DEFAULT_LOGGER_NAME,
    SUPPORTED_IMAGE_REGISTRIES,
)
from nomad.utils import (
    ConfigurationKey,
    _check_key_in_conf,
    _check_optional_key_in_conf,
)
import nomad.ui

# Logger
import logging
logger = logging.getLogger(DEFAULT_LOGGER_NAME)


# Metaclass
class MetaRegistry(type):

    classes: Dict[Any, Any] = {}

    def __new__(cls, name, bases, dct):
        result = super().__new__(cls, name, bases, dct)
        cls.classes[name.lower()] = result
        return result

    @classmethod
    def get_registry(cls, name):
        return cls.classes.get(name)


# Base class
class BaseRegistry(metaclass=MetaRegistry):

    def __init__(self,
        infra_conf: Dict[str, Union[str, Dict[str, Any]]],
        nomad_wkdir: Path,
    ):
        self.infra_conf = infra_conf
        self.nomad_wkdir = nomad_wkdir

        # Check configuration
        self.check_conf()

    def check_conf(self):
        """
        Confirm that the registry configuration is acceptable

        args:
            registry_conf: user-inputted registry configuration
        returns:
            True if the registry configuration is acceptable
        raises:
            ValueError if the registry configuration has an error
        """
        required_keys = [
            ConfigurationKey("registry", str, SUPPORTED_IMAGE_REGISTRIES)
        ]
        for _k in required_keys:
            _check_key_in_conf(_k, self.infra_conf, "infra")

        optional_keys = [
            ConfigurationKey("registry_conf", dict)
        ]
        for _k in optional_keys:
            _check_optional_key_in_conf(_k, self.infra_conf)

        # Registry creds
        if "registry_creds" in self.infra_conf.keys():

            # For mypy
            if not isinstance(self.infra_conf["registry_creds"], dict):
                raise ValueError("`registry_creds` must be a dict!")

            required_keys = [
                ConfigurationKey("username", str),
                ConfigurationKey("password", str),
            ]
            for _k in required_keys:
                _check_key_in_conf(
                    _k, self.infra_conf["registry_creds"], "registry_creds"
                )
        else:
            self.infra_conf["registry_creds"] = {}

        # Registry conf
        self.registry_conf: Dict[str, Union[str, Dict[str, str]]] = {
            "registry": self.infra_conf["registry"],
            "registry_creds": self.infra_conf["registry_creds"],
        }

    def push(self,
        docker_client,
        image_name: str,
        image_tag: Optional[str],
    ):
        """
        Push the image to the registry
        """
        pass


class Ecr(BaseRegistry):

    def __init__(self,
        infra_conf: Dict[str, str | Dict[str, Any]],
        nomad_wkdir: Path,
    ):
        super().__init__(infra_conf, nomad_wkdir)

        # Region
        my_session = boto3.session.Session()
        self.region = my_session.region_name

    def get_ecr_login_info(self):
        """
        Get the ECR registry, username, and password

        args:
            None
        returns:
            tuple of registry, username, and password
        raises:
            NoCredentialsError if ECR creds don't exist
        """
        ecr_client = boto3.client('ecr', region_name=self.region)

        try:
            response = ecr_client.get_authorization_token()
            auth_data = response['authorizationData'][0]
            token = auth_data['authorizationToken']
            registry = auth_data['proxyEndpoint']

            # Decode the base64-encoded Docker credentials
            username, password = base64.b64decode(token).decode().split(':')

            # Update the registry
            self.infra_conf["registry"] = registry

            # Add to the configuration
            for k, v in zip(["username", "password"], [username, password]):
                self.registry_conf["registry_creds"][k] = v  # type: ignore
                self.infra_conf["registry_creds"][k] = v  # type: ignore

            return registry, username, password
        except NoCredentialsError:
            logger.error("Credentials not available")
            raise

    def create_ecr_repository(self,
        repository_name: str,
        image_tag: Optional[str],
        region: str = 'us-east-1'
    ) -> bool:
        """
        Create a new Amazon ECR repository.

        args:
            repository_name: The name of the ECR repository to be created.
            region: AWS region where the ECR repository should be created.
                Default is 'us-east-1'.
        returns:
            True if the repository was created successfully, False otherwise.
        """
        ecr_client = boto3.client('ecr', region_name=region)
        prefix = f"{nomad.ui.AGENT_EVENT}{repository_name}:{image_tag}{nomad.ui.AGENT_WHICH_PUSH}[push] {nomad.ui.RESET}"  # noqa: E501

        try:
            # Create ECR repository
            _ = ecr_client.create_repository(repositoryName=repository_name)
            logger.info(f"{prefix} | ECR repository '{repository_name}' created successfully.")  # noqa
            return True
        except ecr_client.exceptions.RepositoryAlreadyExistsException:
            logger.info(f"{prefix} | ECR repository '{repository_name}' already exists.")  # noqa
            return True
        except NoCredentialsError:
            logger.error("{prefix} | Credentials not available. Unable to create ECR repository.")  # noqa
            return False
        except Exception as e:
            logger.error(f"{prefix} | Error creating ECR repository: {e}")
            return False

    def push(self,
        docker_client,
        image_name: str,
        image_tag: Optional[str],
    ):
        """
        Push the image to the ECR registry
        """
        # ECR info
        registry, username, password = self.get_ecr_login_info()

        # Create the ECR repository, if it doesn't exist
        self.create_ecr_repository(image_name, image_tag, self.region)

        # Tag the local Docker image with the ECR repository URI
        ecr_image = f"{registry.replace('https://', '')}/{image_name}"

        # Tag docker image with ECR info
        image = docker_client.images.get(
            name=f"{image_name}:{image_tag}"
        )
        image.tag(ecr_image, tag=image_tag)

        docker_client.login(username, password, registry=self.infra_conf["registry"])

        # Push the Docker image to ECR
        for line in docker_client.images.push(
            ecr_image,
            tag=image_tag,
            stream=True,
            decode=True,
            auth_config={'username': username, 'password': password}
        ):
            # Construct the message
            msg = []
            if "status" in line.keys():
                msg.append(line["status"])
            if "progress" in line.keys():
                msg.append(line["progress"])
            if "error" in line.keys():
                raise ValueError(line["error"])
            if " ".join(msg) != "":
                log = " ".join(msg)
                logger.info(
                    f"{nomad.ui.AGENT_EVENT}{image_name}:{image_tag}{nomad.ui.AGENT_WHICH_PUSH}[push] {nomad.ui.RESET} | {log}"  # noqa: E501
                )


class Dockerhub(BaseRegistry):

    def check_conf(self):
        """
        We were initially going make the Dockerhub username and Dockerhub password
        required, but instead, we'll prompt the user for these.
        """
        super().check_conf()

        # Update the registry
        self.infra_conf["registry"] = "https://index.docker.io/v1/"

        # Update the registry creds
        if self.registry_conf["registry_creds"] == {}:
            username = click.prompt("Enter your Dockerhub username")
            password = click.prompt("Enter your Dockerhub password")

            for k, v in zip(["username", "password"], [username, password]):
                self.registry_conf["registry_creds"][k] = v  # type: ignore
                self.infra_conf["registry_creds"][k] = v  # type: ignore

    def push(self,
        docker_client,
        image_name: str,
        image_tag: Optional[str],
    ):
        """
        Push the image to the ECR registry
        """
        # Dockerhub username and password
        username = self.infra_conf["registry_creds"]["username"]  # type: ignore
        password = self.infra_conf["registry_creds"]["password"]  # type: ignore
        docker_client.login(username, password, registry=self.infra_conf["registry"])

        # For the username, remove the `@xxx.com` if it exists
        username = re.sub(
            pattern=r'(?i)(\@[a-z]+\.com)$',
            repl="",
            string=username,
        )

        # Tag the image
        dockerhub_image = f"{username}/{image_name}"
        image = docker_client.images.get(
            name=f"{image_name}:{image_tag}"
        )
        image.tag(dockerhub_image, tag=image_tag)

        # Push the Docker image to ECR
        for line in docker_client.images.push(
            dockerhub_image,
            tag=image_tag,
            stream=True,
            decode=True,
        ):
            # Construct the message
            msg = []
            if "status" in line.keys():
                msg.append(line["status"])
            if "progress" in line.keys():
                msg.append(line["progress"])
            if "error" in line.keys():
                raise ValueError(line["error"])
            if " ".join(msg) != "":
                log = " ".join(msg)
                logger.info(
                    f"{nomad.ui.AGENT_EVENT}{image_name}:{image_tag}{nomad.ui.AGENT_WHICH_PUSH}[push] {nomad.ui.RESET} | {log}"  # noqa: E501
                )