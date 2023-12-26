"""
Classes for the various kinds of infra the users can specify within their
configuration file.
"""

# Imports
from pathlib import Path
from typing import Any, Dict
import re
import requests

# Internal imports
from nomad.constants import (
    DEFAULT_LOGGER_NAME,
    SUPPORTED_AGENTS,
    EC2_SUPPORTED_INSTANCE_TYPES,
)
from nomad.utils import (
    ConfigurationKey,
    _check_key_in_conf,
    _check_optional_key_in_conf,
)

# Logger
import logging
DEFAULT_LOGGER = logging.getLogger(DEFAULT_LOGGER_NAME)


# Metaclass
class MetaInfra(type):

    classes: Dict[Any, Any] = {}

    def __new__(cls, name, bases, dct):
        result = super().__new__(cls, name, bases, dct)
        cls.classes[name.lower()] = result
        return result

    @classmethod
    def get_infra(cls, name):
        return cls.classes.get(name)


# Base class
class BaseInfra(metaclass=MetaInfra):

    def __init__(self,
        infra_conf: Dict[str, Any],
        nomad_wkdir: Path
    ):
        self.infra_conf = infra_conf
        self.nomad_wkdir = nomad_wkdir

        # Check configuration
        self.check_conf()

    def check_conf(self):
        """
        Confirm that the infra configuration is acceptable
        """
        # The `type` value must be specified. This is redundant, since we parse the
        # `type` in order to instantiate the correct subclass. But whatever...
        type_key = ConfigurationKey("type", str, SUPPORTED_AGENTS)
        _check_key_in_conf(type_key, self.infra_conf, "infra")

        # Post build commands. We process these in our Agent class, since some of the
        # post-build commands depend on the specific entrypoint the user uses.
        post_build_cmds_key = ConfigurationKey("post_build_cmds", list)
        _check_optional_key_in_conf(post_build_cmds_key, self.infra_conf)


class Ec2(BaseInfra):
    """
    Ec2 infra. This is defined as an infra conf with `type` = ec2. Acceptable nested
    key-value pairs are:

        instance_type: the EC2 instance type. This defaults to t2.micro.
        ami_image    : the Amazon machine image to use. This defaults to
                       ami-0889a44b331db0194
    """

    def check_conf(self):
        """
        Confirm that the infra configuration is acceptable
        """
        BaseInfra.check_conf(self)

        # Check for the `instance_type` and `ami_image` keys
        keys = [
            ConfigurationKey("instance_type", str, EC2_SUPPORTED_INSTANCE_TYPES),
            ConfigurationKey("ami_image", str),
            ConfigurationKey("python_version", [str, int, float]),
        ]
        for _k in keys:
            _check_optional_key_in_conf(_k, self.infra_conf)

        # If the instance type doesn't exist, default to `t2.micro`
        if "instance_type" not in self.infra_conf.keys():
            self.infra_conf["instance_type"] = "t2.micro"
        elif self.infra_conf["instance_type"] is None:
            self.infra_conf["instance_type"] = "t2.micro"

        # Same with AMI image
        if "ami_image" not in self.infra_conf.keys():
            self.infra_conf["ami_image"] = "ami-01c647eace872fc02"
        elif self.infra_conf["ami_image"] is None:
            self.infra_conf["ami_image"] = "ami-01c647eace872fc02"

        # Python version
        self.infra_conf = self.define_python_version(self.infra_conf)

    def define_python_version(self,
        infra_conf: Dict[str, Any]
    ):
        if "python_version" not in infra_conf.keys():
            infra_conf["python_version"] = ""
            return infra_conf

        # Grab / update the python version
        python_version = str(infra_conf["python_version"])

        # Check if major, minor, and micro version are all specified
        _split = python_version.split(".")
        if len(_split) > 3:
            raise ValueError(f"invalid Python version `{python_version}`")
        version_format = ""
        if len(_split) == 1:
            version_format = "major"
        elif len(_split) == 2:
            version_format = "major.minor"
        else:
            version_format = "major.minor.micro"

        # If a full version of Python is specified, then confirm that it exists and
        # return that.
        if version_format == "major.minor.micro":
            resp = requests.get(f"https://www.python.org/ftp/python/{python_version}/")
            if resp.status_code != 200:
                resp.raise_for_status()

            infra_conf["python_version"] = python_version
            return infra_conf

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
                if matches is None:
                    continue
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
                        infra_conf["python_version"] = _version
                        return infra_conf

                elif version_format == "major.minor":
                    _version_split = _version.split(".")
                    if f"{_version_split[0]}.{_version_split[1]}" == python_version:

                        # Check that the version exists in Python's archive
                        resp = requests.get(f"https://www.python.org/ftp/python/{_version}/")  # noqa: E501
                        if resp.status_code != 200:
                            resp.raise_for_status()

                        # If it does, return
                        infra_conf["python_version"] = _version
                        return infra_conf
