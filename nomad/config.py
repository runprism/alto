"""
Configuration class. Used to store common functions for parsing a YAML configuration
file.
"""

# Imports
from typing import Any, Dict, List
from pathlib import Path


# Class definition
class ConfigMixin:

    def parse_requirements(self,
        nomad_wkdir: Path,
        agent_conf: Dict[str, Any],
        absolute: bool = True
    ):
        """
        Get the requirements.txt path and construct the pip install statement.

        args:
            agent_conf: agent configuration as dictionary
            absolute: whether to return the absolute path; if False, then return the
                relative path. Default is True.
        returns:
            requirements path
        """
        # Not all Nomad projects will have a `requirements` file.
        if "requirements" not in agent_conf.keys():
            return ""

        # We already know that the agent configuration is valid. Therefore, it must have
        # a requirements key.
        requirements = agent_conf["requirements"]

        # The `requirements.txt` path should always be specified relative to the
        # directory of the Nomad configuration file.
        absolute_requirements_path = Path(nomad_wkdir / requirements).resolve()

        # Check if this file exists
        if not absolute_requirements_path.is_file():
            raise ValueError(f"no file found at {absolute_requirements_path}")

        if absolute:
            return absolute_requirements_path
        else:
            return requirements

    def parse_infra_key(self,
        infra_conf: Dict[str, Any],
        key: str,
    ) -> Any:
        """
        Get the`key` from the infra configuration

        args:
            infra_conf: infra configuration
            key: the key to retrieve
        returns:
            the value associated with `key` in the infra configuration
        """
        try:
            return infra_conf[key]
        except KeyError:
            return None

    def parse_download_files(self, agent_conf: Dict[str, Any]):
        """
        Get the files to download from the cloud environment

        args:
            agent_conf: agent configuration as dictionary
        returns:
            files to donwload as a list. If no download files are specified, then
            return an empty list.
        """
        # Not all Nomad projects will have a `requirements` file.
        if "download_files" not in agent_conf.keys():
            return []
        download_files = agent_conf["download_files"]
        return download_files

    def parse_python_version(self, agent_conf: Dict[str, Any]):
        """
        Get the Python version to use in the cloud environment

        args:
            agent_conf: agent configuration as dictionary
        returns:
            Python version, as a string
        """
        return agent_conf["python_version"]

    def parse_environment_variables(self,
        agent_conf: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Get environment variables from the agent's configuration and store in a
        dictionary

        args:
            agent_conf: agent configuration as dictionary
        returns:
            environment variables as a dictionary
        """
        if "env" in agent_conf.keys():
            env_vars: Dict[str, str] = agent_conf["env"]
            return env_vars
        else:
            return {}

    def parse_additional_paths(self,
        agent_conf: Dict[str, Any]
    ) -> List[str]:
        """
        Parse `additional_paths` in the agent's configuration

        args:
            agent_conf: agent configuration as dictionary
        returns:
            additional paths as a list of strings
        """
        if "additional_paths" not in agent_conf.keys():
            return []
        additional_paths: List[str] = agent_conf["additional_paths"]
        return additional_paths
