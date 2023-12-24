"""
Image class — users use this to deploy an image (rather than raw code) onto their
infrastructure.
"""

# Imports
from pathlib import Path
from typing import Any, Dict

# Internal imports
from nomad.constants import (
    SUPPORTED_IMAGES,
    DEFAULT_LOGGER_NAME,
    SUPPORTED_IMAGE_REGISTRIES,
)
from nomad.utils import (
    ConfigurationKey,
    _check_key_in_conf,
    _check_optional_key_in_conf,
)
import nomad.ui
from nomad.images.registries import MetaRegistry, BaseRegistry
from nomad.entrypoints import BaseEntrypoint


# Logger
import logging
DEFAULT_LOGGER = logging.getLogger(DEFAULT_LOGGER_NAME)


# Metaclass
class MetaImage(type):

    classes: Dict[Any, Any] = {}

    def __new__(cls, name, bases, dct):
        result = super().__new__(cls, name, bases, dct)
        cls.classes[name.lower()] = result
        return result

    @classmethod
    def get_image(cls, name):
        return cls.classes.get(name)


# Base class
class BaseImage(metaclass=MetaImage):

    def __init__(self,
        nomad_wkdir: Path,
        image_name: str,
        image_conf: Dict[str, Any],
    ):
        self.nomad_wkdir = nomad_wkdir
        self.image_name = image_name
        self.image_conf = image_conf

        # Check configuration
        self.check_conf()

    def check_conf(self):
        """
        Confirm that the image configuration is acceptable
        """
        required_keys = [
            ConfigurationKey("type", str, SUPPORTED_IMAGES),
        ]
        for _k in required_keys:
            _check_key_in_conf(_k, self.image_conf, "image")

        # Optional keys
        optional_keys = [
            ConfigurationKey("registry", str, SUPPORTED_IMAGE_REGISTRIES),
            ConfigurationKey("registry_creds", dict),
        ]
        for _k in optional_keys:
            _check_optional_key_in_conf(_k, self.image_conf)

        # Define the registry
        if "registry" not in self.image_conf.keys():
            DEFAULT_LOGGER.info(
                f"Did not find `registry` key in infra...defaulting to {nomad.ui.MAGENTA}ECR{nomad.ui.RESET}"  # noqa
            )
            registry = "ecr"
            self.image_conf["registry"] = registry
        else:
            registry = self.image_conf["registry"]

        # Create the registry class instance
        self.registry: BaseRegistry = MetaRegistry.get_registry(registry)(
            image_conf=self.image_conf,
            nomad_wkdir=self.nomad_wkdir,
        )

    def build(self,
        agent_conf: Dict[str, Any],
        entrypoint: BaseEntrypoint,
        jinja_template_overrides: Dict[str, Any] = {},
        build_kwargs: Dict[str, Any] = {},
    ):
        raise ValueError(f"`build` not implemented for {self.__class__.__name__}!")

    def delete(self):
        raise ValueError(f"`build` not implemented for {self.__class__.__name__}!")
