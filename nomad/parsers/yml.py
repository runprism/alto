"""
YAML parser class
"""


# Imports
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import os
import yaml
from typing import Any, Dict, Optional
import sys


# Class definition
class YmlParser:

    def __init__(self,
        fpath: Path
    ):
        self.fpath = fpath
        self.fname = fpath.name

    def env(self, var: str) -> str:
        """
        Get environment variable {var}. Can be called in YAML file via {{ env(...) }}
        """
        val: Optional[str] = os.environ.get(var, None)
        if val is None:
            raise ValueError(f"environment variable `{var}` not found")
        return val

    def string_to_pathlib(self, str):
        """
        Convert string to a Path object. This enables users to use the Path API within
        their YAML file.
        """
        return Path(str)

    def create_yml_dict(self,
        rendered_str: str
    ) -> Dict[Any, Any]:
        """
        Created dict representation of YAML file from rendered string

        args:
            rendered_str: rendered string
        return:
            yml_dict: YAML file represented as dictionary
        """
        temp_dict: Optional[Dict[Any, Any]] = yaml.safe_load(rendered_str)
        if temp_dict is None:
            return {}
        return temp_dict

    def render(self,
        parent_path: Path,
        filename: str,
        func_dict: Dict[Any, Any]
    ) -> str:
        """
        Interpret/execute Jinja syntax in `filename` and return `filename` as a string

        args:
            parent_path: path containing YAML file (for loading Environment)
            filename: name of template
            func_dict: function dictionary for Jinja globals
        returns:
            rendered_string: `filename` with executed Jinja
        """
        # Load environment and template
        env = Environment(loader=FileSystemLoader(str(parent_path)))
        jinja_template = env.get_template(filename)
        self.globals = jinja_template.globals

        # Store the path of the file itself in `__file__`
        self.globals["__file__"] = str(self.fpath)
        self.globals["__version__"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"  # noqa: E501
        self.globals["__platform__"] = sys.platform

        # Update template globals with inputted function dictinoary
        jinja_template.globals.update(func_dict)

        # Render string
        rendered_string = jinja_template.render()
        if not isinstance(rendered_string, str):
            raise ValueError(f'invalid return type `{str(type(rendered_string))}`')
        return rendered_string

    def parse(self) -> Dict[Any, Any]:
        """
        Parse YAML file with Jinja syntax

        args:
            None
        returns:
            yml_dict: YAML file represented as dictionary
        """
        # Define function dictionary
        func_dict = {
            "env": self.env,
            "Path": self.string_to_pathlib,
        }

        # Rendered string
        rendered_string = self.render(self.fpath.parent, self.fpath.name, func_dict)

        # Return YAML dict
        yml_dict = self.create_yml_dict(rendered_string)
        return yml_dict
