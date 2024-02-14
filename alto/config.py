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
        alto_wkdir: Path,
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
        # Not all Alto projects will have a `requirements` file.
        if "requirements" not in agent_conf.keys():
            return ""

        # We already know that the agent configuration is valid. Therefore, it must have
        # a requirements key.
        requirements = agent_conf["requirements"]

        # The `requirements.txt` path should always be specified relative to the
        # directory of the Alto configuration file.
        absolute_requirements_path = Path(alto_wkdir / requirements).resolve()

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

    def parse_artifacts(self, agent_conf: Dict[str, Any]):
        """
        Get the files to download from the cloud environment

        args:
            agent_conf: agent configuration as dictionary
        returns:
            files to donwload as a list. If no download files are specified, then
            return an empty list.
        """
        # Not all Alto projects will have a `requirements` file.
        if "artifacts" not in agent_conf.keys():
            return []
        artifacts = agent_conf["artifacts"]

        # Convert the files to absolute paths
        return [Path(_df).resolve() for _df in artifacts]

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

    def parse_mounts(self,
        agent_conf: Dict[str, Any]
    ) -> List[str]:
        """
        Parse `mounts` in the agent's configuration

        args:
            agent_conf: agent configuration as dictionary
        returns:
            additional paths as a list of strings
        """
        if "mounts" not in agent_conf.keys():
            return []
        mounts: List[str] = [str(Path(x).resolve()) for x in agent_conf["mounts"]]
        return mounts
