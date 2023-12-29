"""
Util functions
"""

# Imports
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Union
from pathlib import Path


# Functions / Utils
@dataclass
class ConfigurationKey:
    key_name: str
    key_type: Union[type, List[type]]
    key_supported_values: Optional[List[str]] = None


def _check_key_in_conf(
    _k: ConfigurationKey,
    conf: Dict[str, Any],
    conf_name: str,
):
    """
    Internal function to help us determine if a key exists in a configuration

    args:
        _k: ConfigurationKey
        conf: configuration (or configuration component)
        conf_name: name of configuration (or configuration component)
    returns:
        True if the key exists, is the right type, and is a supported value
    raises:
        ValueError if any of the above conditions are not satisfied
    """
    if _k.key_name not in conf.keys():
        raise ValueError(
            f"`{_k.key_name}` not found in `{conf_name}`'s configuration!"
        )
    _v = conf[_k.key_name]

    # The `key_type` property can be either a single type or a list of types
    if not isinstance(_k.key_type, list):
        if not isinstance(_v, _k.key_type):
            raise ValueError(
                f"`{_k.key_name}` is not the correct type...should be a {str(_k.key_type)}"  # noqa: E501
            )

    # For a list of types, check if the inputted value is any of the inputted types.
    else:
        flag_any_type = False
        for _type in _k.key_type:
            if isinstance(_v, _type):
                flag_any_type = True

        # Check if any of the inputted types were recognized
        if not flag_any_type:
            raise ValueError(
                f"`{_k.key_name}` is not the correct type...should be one of {str(_k.key_type)}"  # noqa: E501
            )

    if _k.key_supported_values is not None:
        if _v not in _k.key_supported_values:
            raise ValueError(
                f"Unsupported value `{_v}` for key `{_k.key_name}`"
            )
    return True


def _check_optional_key_in_conf(
    _k: ConfigurationKey,
    conf: Dict[str, Any],
):
    """
    Internal function to help us determine if an *optional* key exists in a
    configuration

    args:
        _k: ConfigurationKey
        conf: configuration (or configuration component)
        conf_name: name of configuration (or configuration component)
    returns:
        True if the key exists, is the right type, and is a supported value
        False if the key doesn't exist
    raises:
        ValueError if any of the above conditions are not satisfied
    """
    if _k.key_name not in conf.keys():
        return False

    _v = conf[_k.key_name]

    # The `key_type` property can be either a single type or a list of types
    if not isinstance(_k.key_type, list):
        if not isinstance(_v, _k.key_type):
            raise ValueError(
                f"`{_k.key_name}` is not the correct type...should be a {str(_k.key_type)}"  # noqa: E501
            )

    # For a list of types, check if the inputted value is any of the inputted types.
    else:
        flag_any_type = False
        for _type in _k.key_type:
            if isinstance(_v, _type):
                flag_any_type = True

        # Check if any of the inputted types were recognized
        if not flag_any_type:
            raise ValueError(
                f"`{_k.key_name}` is not the correct type...should be one of {str(_k.key_type)}"  # noqa: E501
            )
    if _k.key_supported_values is not None:
        if _v not in _k.key_supported_values:
            raise ValueError(
                f"Unsupported value `{_v}` for key `{_k.key_name}`"
            )

    if _v is None:
        return False
    else:
        return True


def paths_flattener(list_of_paths: List[Union[str, Path]]) -> List[Path]:
    """
    "Flatten" a list of paths, i.e., remove all the redundant parents. For example, if
        list_of_paths = [
            '/Users/username/Documents/test/project/',
            '/Users/username/Documents/test/common1/',
            '/Users/username/Desktop/common2/'
        ]
    then the list of flattened paths will be:
        flattened_paths = [
            '/Documents/test/project/'
            '/Documents/test/common1/'
            '/Desktop/common/
        ]

    args:
        list_of_paths: list of paths to flatten
    returns:
        flattened list of paths
    """
    total_paths = len(list_of_paths)
    split_paths: List[List[str]] = []
    parent_counts: Dict[str, int] = {}
    for path in list_of_paths:

        # Convert path to a string a split
        split_path = str(path).split("/")
        split_paths.append(split_path)
        for parent in split_path[:-1]:
            parent_counts[parent] = parent_counts.get(parent, 0) + 1

    # Now, remove all parents that appear in all the files
    parents_keep = []
    for parent, count in parent_counts.items():
        if count < total_paths:
            parents_keep.append(parent)

    # Flatten
    flattened_paths = []
    for spath in split_paths:
        for parent in spath[:-1]:
            if parent not in parents_keep:
                spath.remove(parent)
        flattened_paths.append(Path("/".join(spath)))

    return flattened_paths
