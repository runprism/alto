"""
Base task class
"""

# Imports
import argparse
from pathlib import Path
from typing import Any, Dict
import re
import requests


# Internal imports
from nomad.constants import (
    SUPPORTED_AGENTS,
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
    Jupyter
)
from nomad.infras import (  # noqa
    MetaInfra,
    BaseInfra,
    Ec2,
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
        self.conf = self.define_python_version(self.conf)
        self.conf = self.define_post_build_cmds(self.conf)
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
        self.infra = MetaInfra.get_infra(conf["infra"]["type"])(
            infra_conf=conf["infra"],
            nomad_wkdir=self.nomad_wkdir
        )

        # Other optional keys
        optional_keys = [
            ConfigurationKey("python_version", [str, int, float]),
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

    def define_post_build_cmds(self,
        conf: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Define actions to be performed before the code is executed. These could be
        anything, but they must be specified as a list of bash commands.

        For certain entrypoints, we use this function to augment the `post_build_cmds`
        that the user specifies, if any.

        args:
            conf: agent configuration
        returns:
            configuration with augmented `post_build_cmds`
        """
        # We run this function *after* checking the agent configuration and entrypoint
        # configuration.
        post_build_cmds = []
        if "post_build_cmds" in conf.keys():
            post_build_cmds = conf["post_build_cmds"]

        # At this point, we should know what our entrypoint type is
        if not hasattr(self, "entrypoint"):
            raise ValueError("entrypoint attribute not defined!")
        ep: BaseEntrypoint = self.entrypoint

        # For `jupyter` entrypoints, we need to install the ipython kernel. Since we're
        # running these actions after the requirements are installed, then the
        if isinstance(ep, Jupyter):
            # Technically, the user's requirements should install ipython and the
            # ipykernel, but we'll do it again here anyways.
            for cmd in [
                "pip install ipython ipykernel papermill",
                f'ipython kernel install --name "{ep.kernel}" --user'
            ]:
                if cmd not in post_build_cmds:
                    post_build_cmds.append(cmd)

        # Define class attribute
        if post_build_cmds != []:
            conf["post_build_cmds"] = post_build_cmds
        return conf

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

    def define_python_version(self,
        conf: Dict[str, Any]
    ):
        if "python_version" not in conf.keys():
            conf["python_version"] = ""
            return conf

        # Grab / update the python version
        python_version = str(conf["python_version"])

        # Check if major, minor, and patch version are all specified
        _split = python_version.split(".")
        if len(_split) > 3:
            raise ValueError(f"invalid Python version `{python_version}`")
        version_format = ""
        if len(_split) == 1:
            version_format = "major"
        elif len(_split) == 2:
            version_format = "major.minor"
        else:
            version_format = "major.minor.patch"

        # If a full version of Python is specified, then confirm that it exists and
        # return that.
        if version_format == "major.minor.patch":
            resp = requests.get(f"https://www.python.org/ftp/python/{python_version}/")
            if resp.status_code != 200:
                resp.raise_for_status()

            conf["python_version"] = python_version
            return conf

        # If only the major or major/minor are specified, then grab the latest
        # associated version of Python.
        else:

            # Place imports in this inner `if` clause, because we don't want to import
            # stuff unnecessarily.
            from bs4 import BeautifulSoup

            # Get all available versions
            url = "https://www.python.org/doc/versions/"
            response = requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")

            # All python versions are stored in a single div
            div = soup.find("div", attrs={"id": "python-documentation-by-version"})

            # Python versions are stored in <li> elements, i.e., something like
            #   <li>
            #       <a class="reference external" href="https://docs.python.org/release/3.11.0/">Python 3.11.0</a>  # noqa
            #       " , documentation released on 24 October 2022."
            #   </li>
            lis = div.find_all("a", class_="reference external")

            # Versions are specified in descending order, with the most recent version
            # specified first.
            for li in lis:
                matches = re.search("Python (.*)$", li.contents[0])
                _version = matches.group(1)

                # Find the first Python version that agrees with the inputted "major" /
                # "major.minor" version.
                if version_format == "major":
                    if _version.split(".")[0] == python_version:

                        # Check that the version exists in Python's archive
                        resp = requests.get(f"https://www.python.org/ftp/python/{_version}/")  # noqa: E501
                        if resp.status_code != 200:
                            resp.raise_for_status()

                        # If it does, return
                        conf["python_version"] = _version
                        return conf

                elif version_format == "major.minor":
                    _version_split = _version.split(".")
                    if f"{_version_split[0]}.{_version_split[1]}" == python_version:

                        # Check that the version exists in Python's archive
                        resp = requests.get(f"https://www.python.org/ftp/python/{_version}/")  # noqa: E501
                        if resp.status_code != 200:
                            resp.raise_for_status()

                        # If it does, return
                        conf["python_version"] = _version
                        return conf
