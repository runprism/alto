"""
Pytest configuration
"""

# Imports
import os
from pathlib import Path
from click.testing import CliRunner
from nomad.main import cli
from nomad.tests.integration.utils import (
    key_pair_exists,
    security_group_exists,
    running_instance_exists,
    cli_runner
)
from nomad.constants import (
    PYTHON_VERSION,
    PLATFORM
)


# Constants
TEST_DIR = Path(__file__).parent
TEST_FUNCTION = TEST_DIR / 'function'
TEST_ERROR = TEST_DIR / 'test_apply_error'


# Tests
def pytest_sessionstart():
    """
    Create the EC2 agent
    """
    # First, test that the apply command doesn't create resources if there is an error
    # in the configuration file.
    os.chdir(TEST_ERROR)

    # Invoke the `apply` command
    proc = cli_runner(["apply", "-f", "nomad.yml"])

    # Check if EC2 resources exist
    resource_name = f"bad_cloud_agent-{PLATFORM}-{PYTHON_VERSION}"
    assert not key_pair_exists(resource_name)
    assert not security_group_exists(resource_name)
    assert not running_instance_exists(resource_name)
    assert not proc.returncode == 0

    # Now, invoke the `apply` command and create a proper EC2 agent.
    os.chdir(TEST_FUNCTION)
    proc = cli_runner(["apply", "-f", "nomad.yml"])

    # Check if EC2 resources exist
    resource_name = f"my_cloud_agent-{PLATFORM}-{PYTHON_VERSION}"
    assert key_pair_exists(resource_name)
    assert security_group_exists(resource_name)
    assert running_instance_exists(resource_name)
    assert proc.returncode == 0


def pytest_sessionfinish():
    """
    Delete the EC2 agent
    """
    # Delete the resources
    os.chdir(TEST_FUNCTION)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["delete", "-f", "nomad.yml"]
    )

    # Resources should no longer exist
    resource_name = f"my_cloud_agent-{PLATFORM}-{PYTHON_VERSION}"
    assert result.exit_code == 0
    assert not key_pair_exists(resource_name)
    assert not security_group_exists(resource_name)
    assert not running_instance_exists(resource_name)
