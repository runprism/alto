"""
`apply` integration tests (i.e., full runs on micro EC2 instances).
"""

# Imports
import os
from pathlib import Path
# import pytest
from click.testing import CliRunner
from nomad.main import cli
from nomad.tests.integration.utils import (
    key_pair_exists,
    security_group_exists,
    running_instance_exists
)


# Constants
TEST_DIR = Path(__file__).parent
TEST_FUNCTION = TEST_DIR / 'function'
TEST_ERROR = TEST_DIR / 'test_apply_error'


# Tests
def test_apply_delete_normal():
    """
    Test the `apply` and `delete` commands
    """
    os.chdir(TEST_FUNCTION)
    runner = CliRunner()

    # Invoke the `apply` command
    result = runner.invoke(
        cli, ["apply", "-f", "nomad.yml"]
    )

    # Check if EC2 resources exist
    resource_name = "my_cloud_agent"
    assert key_pair_exists(resource_name)
    assert security_group_exists(resource_name)
    assert running_instance_exists(resource_name)
    assert result.exit_code == 0

    # Delete the resources
    result = runner.invoke(
        cli, ["delete", "-f", "nomad.yml"]
    )
    assert result.exit_code == 0
    assert not key_pair_exists(resource_name)
    assert not security_group_exists(resource_name)
    assert not running_instance_exists(resource_name)


def test_apply_delete_error():
    """
    If there is an error in the `apply` command, *all* EC2 resources will automatically
    get deleted.
    """
    os.chdir(TEST_ERROR)
    runner = CliRunner()

    # Invoke the `apply` command
    result = runner.invoke(
        cli, ["apply", "-f", "nomad.yml"]
    )

    # Check if EC2 resources exist
    resource_name = "my_cloud_agent"
    assert not key_pair_exists(resource_name)
    assert not security_group_exists(resource_name)
    assert not running_instance_exists(resource_name)
    assert not result.exit_code == 0
