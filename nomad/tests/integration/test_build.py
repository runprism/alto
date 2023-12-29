"""
`build` integration tests (i.e., full runs on micro EC2 instances).
"""

# Imports
import os
from pathlib import Path
from nomad.tests.integration.utils import (
    _resources_exist,
    s3_file_exists,
    delete_s3_file,
    cli_runner,
    ecr_repository_exists,
)
from nomad.constants import (
    PYTHON_VERSION,
    PLATFORM,
)


# Constants
TEST_DIR = Path(__file__).parent
TEST_FUNCTION = TEST_DIR / 'function'
TEST_JUPYTER = TEST_DIR / 'jupyter'
TEST_PROJECT = TEST_DIR / 'project'
TEST_SCRIPT = TEST_DIR / 'script'


# Tests
def _build_integration_test(
    test_path: Path,
    fname_name: str,
    conf_fname: str = "nomad.yml",
    image: bool = False
):
    os.chdir(test_path)

    # Delete file in S3, if it exists
    output_key = f"{PLATFORM}_{PYTHON_VERSION}_{fname_name}".replace(".", "")
    file_s3_uri = f"s3://nomad-dev-tests/tests/{output_key}.txt"
    delete_s3_file(file_s3_uri)

    # Invoke the `build` command
    proc = cli_runner(["build", "-f", conf_fname, "--no-delete-success", "--no-delete-failure"])  # noqa: E501

    # Check if EC2 resources exist
    resource_name = f"{test_path.name}-my_cloud_agent-{PYTHON_VERSION}"
    resources = _resources_exist(resource_name)
    assert resources["key_pair"]
    assert resources["security_group"]
    assert resources["instance"]
    assert proc.returncode == 0

    # Check output
    test_output = s3_file_exists(file_s3_uri)
    expected_output = f"Hello world from our `{PLATFORM}.{PYTHON_VERSION}.{fname_name}` test case!"  # noqa: E501
    assert test_output == expected_output

    # Check if the Docker image exists
    if image:
        ecr_repository_exists(f"{test_path.name}-my_cloud_agent-{PYTHON_VERSION}")


def test_function():
    """
    Test the output of a function deployment
    """
    _build_integration_test(TEST_FUNCTION, "test_function")
    _build_integration_test(TEST_FUNCTION, "test_function", "nomad_docker.yml", True)


def test_script():
    """
    Test the output of a function deployment
    """
    _build_integration_test(TEST_SCRIPT, "test_script")
    _build_integration_test(TEST_SCRIPT, "test_script", "nomad_docker.yml", True)


def test_project():
    """
    Test the output of a function deployment
    """
    _build_integration_test(TEST_PROJECT, "test_project")
    _build_integration_test(TEST_PROJECT, "test_project", "nomad_docker.yml", True)
