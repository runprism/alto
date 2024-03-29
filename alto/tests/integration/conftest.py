"""
Pytest configuration
"""

# Imports
import os
from pathlib import Path
from alto.tests.integration.utils import (
    key_pair_exists,
    security_group_exists,
    running_instance_exists,
    cli_runner,
    ecr_repository_exists,
    delete_ecr_repository,
    instance_profile_exists,
)
from alto.constants import (
    PYTHON_VERSION,
)
import shutil


# Constants
TEST_DIR = Path(__file__).parent
TEST_FUNCTION = TEST_DIR / 'function'
TEST_SCRIPT = TEST_DIR / 'script'
TEST_JUPYTER = TEST_DIR / 'jupyter'
TEST_ARTIFACTS = TEST_DIR / 'artifacts'
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
    proc = cli_runner(["apply", "-f", "alto.yml"])

    # Check if EC2 resources exist
    bad_resource_name = f"bad_cloud_agent-{PYTHON_VERSION}"
    assert not key_pair_exists(bad_resource_name)
    assert not security_group_exists(bad_resource_name)
    assert not running_instance_exists(bad_resource_name)
    assert not proc.returncode == 0

    # Now, invoke the `apply` command and create a proper EC2 agent. We'll also install
    # Docker on our EC2 agent.
    os.chdir(TEST_FUNCTION)
    resource_name = f"{TEST_FUNCTION.name}-my_cloud_agent-{PYTHON_VERSION}"
    delete_ecr_repository(resource_name)
    assert not ecr_repository_exists(resource_name)
    proc = cli_runner(["apply", "-f", "alto_docker.yml"])

    # Check if ECS repository exists
    assert ecr_repository_exists(resource_name)

    # Check if EC2 resources exist
    assert key_pair_exists(resource_name)
    assert security_group_exists(resource_name)
    assert running_instance_exists(resource_name)
    assert proc.returncode == 0


def pytest_sessionfinish():
    """
    Delete the EC2 agent
    """
    for _dir in [
        TEST_FUNCTION,
        TEST_SCRIPT,
        TEST_JUPYTER,
        TEST_ARTIFACTS,
    ]:

        # Delete the resources
        os.chdir(_dir)
        proc = cli_runner(["delete", "-f", "alto_docker.yml"])
        assert proc.returncode == 0
        proc = cli_runner(["delete", "-f", "alto_ssm_docker.yml"])
        assert proc.returncode == 0

        # Resources should no longer exist
        for res in [
            f"{_dir.name}-my_cloud_agent-{PYTHON_VERSION}",
            f"{_dir.name}-my_cloud_agent-ssm-{PYTHON_VERSION}",
        ]:
            assert not key_pair_exists(res)
            assert not security_group_exists(res)
            assert not running_instance_exists(res)
            assert not instance_profile_exists(f"{res}-profile")

            # Also, delete the ECR repositories
            delete_ecr_repository(res)
            assert not ecr_repository_exists(res)

        if Path(_dir / '.docker_context').is_dir():
            shutil.rmtree(_dir / '.docker_context', ignore_errors=True)
