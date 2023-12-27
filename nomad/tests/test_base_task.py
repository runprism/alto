"""
Test cases for BaseTask (and its children)
"""

# Imports
import argparse
from pathlib import Path
from nomad.tasks.base import BaseTask
import pytest


# Constants
TEST_DIR = Path(__file__).parent
CONFs = TEST_DIR / 'confs'


# Util functions
def _create_task(path: Path):
    args = argparse.Namespace()
    args.file = str(path)
    args.log_level = 'info'
    args.wkdir = str(CONFs)
    task = BaseTask(args)

    # Task name
    assert task.name == "my_cloud_agent"
    return task


# Tests
def test_normal_conf():
    """
    If `additional_paths` is not a list, throw an error
    """
    task = _create_task(path=(CONFs / 'normal_conf.yml'))
    task.check()

    # Expected configuration
    expected_conf = {
        "infra": {
            "type": "ec2",
            "instance_type": "t2.micro",
            "ami_image": "ami-01c647eace872fc02",
            "python_version": "",
        },
        "requirements": "requirements.txt",
        "entrypoint": {
            "type": "function",
            "src": "scripts",
            "cmd": "test_fn.print_value",
            "kwargs": {
                "value": "hello world",
            }
        },
        "additional_paths": [
            str(CONFs)
        ],
        "env": {
            "ENV_VAR_1": "VALUE1",
            "ENV_VAR_2": "VALUE2",
        },
        "download_files": [],
    }
    assert expected_conf == task.conf


def test_bad_yml_additional_paths():
    """
    If `additional_paths` is not a list, throw an error
    """
    task = _create_task(path=(CONFs / 'bad_additional_paths.yml'))

    # Run the check
    with pytest.raises(ValueError) as cm:
        task.confirm_additional_paths_conf_structure(task.conf)
    expected_msg = "`additional_paths` is not the correct type...should be a <class 'list'>"  # noqa: E501
    assert expected_msg == str(cm.value)


def test_no_infra():
    """
    If `type` does not exist, throw an error
    """
    task = _create_task(path=(CONFs / 'no_infra.yml'))

    # Run the check
    with pytest.raises(ValueError) as cm:
        task.check_conf(task.conf, task.name)
    expected_msg = "`infra` not found in `my_cloud_agent`'s configuration!"  # noqa: E501
    assert expected_msg == str(cm.value)


def test_infra_bad_type():
    """
    If `type` is not currently supported, throw an error
    """
    task = _create_task(path=(CONFs / 'infra_bad_type.yml'))

    # Run the check
    with pytest.raises(ValueError) as cm:
        task.check_conf(task.conf, task.name)
    expected_msg = "Unsupported value `emr` for key `type`"  # noqa: E501
    assert expected_msg == str(cm.value)


def test_infra_no_type():
    """
    If `type` does not exist, throw an error
    """
    task = _create_task(path=(CONFs / 'infra_no_type.yml'))

    # Run the check
    with pytest.raises(ValueError) as cm:
        task.check_conf(task.conf, task.name)
    expected_msg = "`type` not found in `infra`'s configuration!"  # noqa: E501
    assert expected_msg == str(cm.value)


def test_bad_requirements():
    """
    `requirements` should be a string representing the path to the project's
    dependencies. If it isn't, throw an error.
    """
    task = _create_task(path=(CONFs / 'bad_requirements.yml'))

    # Run the check
    with pytest.raises(ValueError) as cm:
        task.check_conf(task.conf, task.name)
    expected_msg = "`requirements` is not the correct type...should be a <class 'str'>"  # noqa: E501
    assert expected_msg == str(cm.value)


def test_bad_env():
    """
    `requirements` should be a dictionary of environment variables. If it isn't, throw
    an error.
    """
    task = _create_task(path=(CONFs / 'bad_env.yml'))

    # Run the check
    with pytest.raises(ValueError) as cm:
        task.check_conf(task.conf, task.name)
    expected_msg = "`env` is not the correct type...should be a <class 'dict'>"  # noqa: E501
    assert expected_msg == str(cm.value)


def test_no_entrypoint():
    """
    If `entrypoint` doesn't exist, throw an error. We parse the actual contents of the
    `entrypoint` dictionary in a separate test module.
    """
    task = _create_task(path=(CONFs / 'no_entrypoint.yml'))

    # Run the check
    with pytest.raises(ValueError) as cm:
        task.check_conf(task.conf, task.name)
    expected_msg = "`entrypoint` not found in `my_cloud_agent`'s configuration!"
    assert expected_msg == str(cm.value)


def test_bad_entrypoint():
    """
    If `entrypoint` doesn't exist, throw an error. We parse the actual contents of the
    `entrypoint` dictionary in a separate test module.
    """
    task = _create_task(path=(CONFs / 'bad_entrypoint.yml'))

    # Run the check
    with pytest.raises(ValueError) as cm:
        task.check_conf(task.conf, task.name)
    expected_msg = "`entrypoint` is not the correct type...should be a <class 'dict'>"
    assert expected_msg == str(cm.value)


def test_jupyter_entrypoint():
    """
    Test a normal Jupyter entrypoint
    """
    task = _create_task(path=(CONFs / 'normal_conf_jupyter.yml'))
    task.check()
    expected_conf = {
        "infra": {
            "type": "ec2",
            "instance_type": "t2.micro",
            "ami_image": "ami-01c647eace872fc02",
            "python_version": "",
        },
        "requirements": "requirements.txt",
        "entrypoint": {
            "type": "jupyter",
            "kernel": "python3",
            "src": "scripts",
            "cmd": "nomad_nb.ipynb",
        },
        "env": {
            "ENV_VAR_1": "VALUE1",
            "ENV_VAR_2": "VALUE2",
        },
        "download_files": [
            "scripts/nomad_nb_exec.ipynb",
        ],
    }
    assert expected_conf == task.conf
