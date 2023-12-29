"""
Base task class
"""

# Imports
import argparse
from pathlib import Path
from typing import Any, Dict


# Internal imports
from nomad.constants import (
    SUPPORTED_AGENTS,
    SUPPORTED_IMAGES,
)
from nomad.utils import (
    ConfigurationKey,
    _check_key_in_conf,
    _check_optional_key_in_conf,
)
from nomad.parsers.yml import YmlParser
from nomad.nomad_logger import (
    set_up_logger
)
from nomad.entrypoints import (  # noqa
    MetaEntrypoint,
    BaseEntrypoint,
    Project,
    Function,
    Jupyter,
)
from nomad.infras import (  # noqa
    MetaInfra,
    BaseInfra,
    Ec2,
)
from nomad.images import (  # noqa
    MetaImage,
    BaseImage,
    Docker
)


# Class definition
class BaseTask:

    def __init__(self,
        args: argparse.Namespace,
    ):
        self.args = args

        # Current working directory. This is the directory containing the nomad.yml
        # file.
        self.nomad_wkdir = Path(self.args.wkdir)

        # Args will definitely have a `file` attribute
        self.conf_fpath = Path(self.args.file)
        raw_conf = self.parse_conf_fpath(self.conf_fpath)

        # If the user specified a specific agent to use in their args, then use that
        if hasattr(self.args, "name") and self.args.name is not None:
            self.name = args.name

        # Otherwise, the user should only have one agent in their configuration
        else:
            all_names = list(raw_conf.keys())
            if len(all_names) > 1:
                msg1 = f"multiple agents found in `{self.conf_fpath}`"
                msg2 = "specify one to use and try again"
                raise ValueError("...".join([msg1, msg2]))
            self.name = all_names[0]

        # Get the specific agent configuration
        self.conf = raw_conf[self.name]

        # Set up logger
        set_up_logger(self.args.log_level)

    def check(self):
        """
        Check all configuration requirements
        """
        self.check_conf(self.conf, self.name)
        self.confirm_matrix_conf_structure(self.conf)
        self.confirm_entrypoint_conf_structure(self.conf)
        self.confirm_additional_paths_conf_structure(self.conf)
        self.confirm_image_conf_structure(self.conf)
        self.conf = self.define_download_files(self.conf)

    def parse_conf_fpath(self,
        conf_fpath: Path
    ) -> Dict[str, Any]:
        """
        Parse the configuration file path and return the configuration YAML as a
        dictionary

        args:
            conf_fpath: file path to configuration YML
        """
        parser = YmlParser(fpath=conf_fpath)
        return parser.parse()

    def check_conf(self,
        conf: Dict[str, Any],
        name: str,
    ):
        """
        Check configuration structure

        args:
            conf: agent configuration
            name: name of agent
        returns:
            True if the `conf` is properly structured
        raises:
            ValueError if `conf` is not properly structured
        """
        required_keys = [
            ConfigurationKey("infra", dict),
            ConfigurationKey("entrypoint", dict),
        ]
        for _k in required_keys:
            _check_key_in_conf(_k, conf, name)

        # Create the infra
        type_key = ConfigurationKey("type", str, SUPPORTED_AGENTS)
        _check_key_in_conf(type_key, conf["infra"], "infra")
        conf_type = conf["infra"]["type"].replace("-", "")
        self.infra = MetaInfra.get_infra(conf_type)(
            infra_conf=conf["infra"],
            nomad_wkdir=self.nomad_wkdir
        )

        # Other optional keys
        optional_keys = [
            ConfigurationKey("image", dict),
            ConfigurationKey("env", dict),
            ConfigurationKey("requirements", str),
            ConfigurationKey("post_build_cmds", list),
            ConfigurationKey("download_files", list),
        ]
        for _k in optional_keys:
            _check_optional_key_in_conf(_k, conf)

        return True

    def confirm_matrix_conf_structure(self,
        conf: Dict[str, Any]
    ):
        """
        Confirm that the `matrix` section of the configuration is properly structured

        args:
            conf: agent configuration
        returns:
            True if the `matrix` section is properly structured
        raises:
            ValueError() if the `matrix` section is not properly structured
        """
        if "matrix" not in conf.keys():
            return True
        matrix = conf["matrix"]

        # Only one required value: max_concurrency. This controls how many cloud
        # instances are instantiated at once
        required_keys = [
            ConfigurationKey("max_concurrency", int)
        ]
        for _k in required_keys:
            _check_key_in_conf(_k, matrix, "matrix")

        # All other values should be a list
        for key, value in matrix.items():
            if key in [_k.key_name for _k in required_keys]:
                continue
            if not isinstance(value, list):
                raise ValueError(
                    f"Invalid argument `{value}` in `matrix`...this only supports list arguments"  # noqa: E501
                )

    def confirm_entrypoint_conf_structure(self,
        conf: Dict[str, Any]
    ):
        """
        At this point, we know that the `entrypoint` key exists and is a
        dictionary. Confirm that the `entrypoint` section of the configuration is
        properly structured

        args:
            conf: agent configuration
        returns:
            True if the `entrypoint` section is properly structured
        raises:
            ValueError() if the `entrypoint` section is not properly structured
        """
        entrypoint = conf["entrypoint"]
        if "type" not in entrypoint.keys():
            raise ValueError(
                "`entrypoint` does not have a nested `type` key"
            )
        self.entrypoint = MetaEntrypoint.get_entrypoint(entrypoint["type"])(
            entrypoint_conf=entrypoint,
            nomad_wkdir=self.nomad_wkdir,
        )

    def confirm_image_conf_structure(self,
        conf: Dict[str, Any]
    ):
        """
        At this point, the `image` key may or may not exist. If it does exist, then we
        want to create the associated `Image` class instance.

        args:
            conf: agent configuration
        returns:
            True if the `image` section is properly structured
        raises:
            ValueError() if the `image` section is not properly structured
        """
        if "image" in conf.keys():
            image = conf["image"]
            if image == {}:
                return None

            # Check that `type` exists
            if "type" not in image.keys():
                raise ValueError(
                    "`image` configuration missing a `type`!"
                )
            if image["type"] not in SUPPORTED_IMAGES:
                raise ValueError(
                    f"unrecognized image type `{image['type']}`"
                )
            self.image = MetaImage.get_image(image["type"])(
                nomad_wkdir=self.nomad_wkdir,
                image_name=self.name,
                image_conf=image,
            )

        else:
            self.image = None

    def confirm_additional_paths_conf_structure(self,
        conf: Dict[str, Any]
    ):
        """
        If the `additional_paths` section exists (remember, it's an optional key),
        confirm that it is properly structured

        args:
            conf: agent configuration
        returns:
            True if the `additional_paths` section doesn't exist or exists and is
            properly structured
        raises:
            ValueError() if the `additional_paths` section is not properly structured
        """
        optional_key = ConfigurationKey("additional_paths", list)
        _check_optional_key_in_conf(optional_key, conf)
        return True

    def define_download_files(self,
        conf: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Define the files to be downloaded from the agent after the agent has
        successfully run. This will be specified within the `download_files` key in the
        agent configuration.

        For certain entrypoints, we use this function to augment the `download_files`
        that the user specifies, if any.

        args:
            conf: agent configuration
        returns:
            configuration with augmented `download_files`
        """
        # We run this function *after* checking the agent configuration and entrypoint
        # configuration.
        download_files = []
        if "download_files" in conf.keys():
            download_files = conf["download_files"]

        # At this point, we should know what our entrypoint type is
        if not hasattr(self, "entrypoint"):
            raise ValueError("entrypoint attribute not defined!")
        ep: BaseEntrypoint = self.entrypoint

        # For `jupyter` entrypoints, we need to install the ipython kernel. Since we're
        # running these actions after the requirements are installed, then the
        if isinstance(ep, Jupyter):

            # We should donwload the executed notebook. The path of the executed
            # notebook will be relative to `src`.
            output_path = Path(ep.src) / ep.output_path
            if str(output_path) not in download_files:
                download_files.append(str(output_path))

        # Update configuration
        conf["download_files"] = download_files
        return conf
