"""
Util functions
"""

# Imports
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Union


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
    raises:
        ValueError if any of the above conditions are not satisfied
    """
    if _k.key_name not in conf.keys():
        return True

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
