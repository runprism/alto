"""
Classes for the various kinds of entrypoints users can specify within their
configuration file.
"""

# Imports
from pathlib import Path
import re
from typing import Any, Dict

# Internal imports
from nomad.constants import (
    SUPPORTED_ENTRYPOINTS,
)
from nomad.utils import (
    ConfigurationKey,
    _check_key_in_conf,
    _check_optional_key_in_conf,
)


# Metaclass
class MetaEntrypoint(type):

    classes: Dict[Any, Any] = {}

    def __new__(cls, name, bases, dct):
        result = super().__new__(cls, name, bases, dct)
        cls.classes[name.lower()] = result
        return result

    @classmethod
    def get_entrypoint(cls, name):
        return cls.classes.get(name)


# Base class
class BaseEntrypoint(metaclass=MetaEntrypoint):

    def __init__(self,
        entrypoint_conf: Dict[str, Any],
        nomad_wkdir: Path
    ):
        self.entrypoint_conf = entrypoint_conf
        self.nomad_wkdir = nomad_wkdir

        # Check configuration
        self.check_conf()

    def check_conf(self):
        """
        Confirm that the entrypoint configuration is acceptable
        """
        required_keys = [
            ConfigurationKey("type", str, SUPPORTED_ENTRYPOINTS),
            ConfigurationKey("cmd", str),
        ]
        for _k in required_keys:
            _check_key_in_conf(_k, self.entrypoint_conf, "entrypoint")

        # Optional keys
        optional_keys = [
            ConfigurationKey("src", str),

        ]
        for _k in optional_keys:
            _check_optional_key_in_conf(_k, self.entrypoint_conf)

        # Update class attributes
        self.type: str = self.entrypoint_conf["type"]
        self.cmd: str = self.entrypoint_conf["cmd"]
        self.src: str = ""
        if "src" in self.entrypoint_conf.keys():
            self.src = self.entrypoint_conf["src"]

        # Check if `src` directory exists. Note that if `src` is blank, then Pathlib
        # will just check if the Nomad configuration file's directory exists.
        if not Path(self.nomad_wkdir / self.src).is_dir():
            raise ValueError("could not parse `src` for entrypoint")

    def build_command(self):
        if self.src != "":
            return f"cd {self.src} && {self.cmd}"
        else:
            return self.cmd


class Script(BaseEntrypoint):
    """
    Script entrypoint. We need this so out MetaEntrypoint class can create the
    appropriate child class based on the user's `type`.
    """
    pass


class Project(BaseEntrypoint):
    """
    Project entrypoint. We need this so out MetaEntrypoint class can create the
    appropriate child class based on the user's `type`.
    """
    pass


class Function(BaseEntrypoint):

    def check_conf(self):
        """
        Confirm that the entrypoint configuration is acceptable
        """
        super().check_conf()
        optional_keys = [
            ConfigurationKey("kwargs", dict)

        ]
        for _k in optional_keys:
            _check_optional_key_in_conf(_k, self.entrypoint_conf)

        # Update class attributes
        self.kwargs = {}
        if "kwargs" in self.entrypoint_conf.keys():
            self.kwargs = self.entrypoint_conf["kwargs"]

        # Check the format of the `cmd`. It should be something like <module
        # name>.<function name>`.
        cmd_structure = r'(?i)^([^\.]+)\.([^\.]+)$'
        matches = re.findall(cmd_structure, self.cmd)
        if len(matches) != 1:
            raise ValueError("`cmd` value not properly formatted...should be <module_name>.<function_name>")  # noqa: E501
        match = matches[0]
        self.module, self.function = match[0], match[1]

        # Check if `module` exists as a file
        if not (self.nomad_wkdir / self.src / f"{self.module}.py").is_file():
            raise ValueError(
                f"could not find module {str(self.nomad_wkdir / self.src / f'{self.module}.py')}"  # noqa: E501
            )

    def build_command(self):
        kwargs_str = ", ".join([
            f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}" for k, v in self.kwargs.items()  # noqa: E501
        ])
        base_python_cmd = f"python -c 'from {self.module} import {self.function}; {self.function}({kwargs_str})'"  # noqa: E501
        if self.src != "":
            return f"cd {self.src} && {base_python_cmd}"
        else:
            return base_python_cmd


class Jupyter(BaseEntrypoint):
    """
    Jupyter entrypoint. This entrypoint is used to execute an entire Jupyter notebook on
    a user-specified cloud resource.
    """
