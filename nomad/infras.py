"""
Classes for the various kinds of infra the users can specify within their
configuration file.
"""

# Imports
from pathlib import Path
from typing import Any, Dict

# Internal imports
from nomad.constants import (
    SUPPORTED_AGENTS,
    EC2_SUPPORTED_INSTANCE_TYPES,
)
from nomad.utils import (
    ConfigurationKey,
    _check_key_in_conf,
    _check_optional_key_in_conf,
)


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
        super().check_conf()

        # Check for the `instance_type` and `ami_image` keys
        keys = [
            ConfigurationKey("instance_type", str, EC2_SUPPORTED_INSTANCE_TYPES),
            ConfigurationKey("ami_image", str),
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
