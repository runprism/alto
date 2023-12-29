"""
`run` integration tests (i.e., full runs on micro EC2 instances).
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
from typing import List
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
TEST_DOWNLOAD_FILES = TEST_DIR / 'download_files'


# Tests
def _apply_integration_test(
    test_path: Path,
    conf_fname: str = "nomad.yml",
    docker: bool = False,
):
    os.chdir(test_path)
    proc = cli_runner(["apply", "-f", conf_fname])

    # Check if EC2 resources exist
    resource_name = f"{test_path.name.replace('_', '-')}-my_cloud_agent-{PYTHON_VERSION}"  # noqa: E501
    resources = _resources_exist(resource_name)
    assert resources["key_pair"]
    assert resources["security_group"]
    assert resources["instance"]
    assert proc.returncode == 0

    # Check if the repository exists
    if docker:
        assert ecr_repository_exists(resource_name)


def _run_integration_test(
    fname_name: str,
    run_args: List[str],
):
    # Delete file in S3, if it exists
    output_key = f"{PLATFORM}_{PYTHON_VERSION}_{fname_name}".replace(".", "")
    file_s3_uri = f"s3://nomad-dev-tests/tests/{output_key}.txt"
    delete_s3_file(file_s3_uri)

    # Run
    proc = cli_runner(run_args)
    assert proc.returncode == 0
    test_output = s3_file_exists(file_s3_uri)
    expected_output = f"Hello world from our `{PLATFORM}.{PYTHON_VERSION}.{fname_name}` test case!"  # noqa: E501
    assert test_output == expected_output
    delete_s3_file(file_s3_uri)


def test_function():
    """
    Test the output of a function deployment
    """
    # Run test, no Docker
    _apply_integration_test(TEST_FUNCTION)
    _run_integration_test(
        "test_function",
        ['run', '-f', 'nomad.yml', '--no-delete-success', '--no-delete-failure']
    )

    # Run test, with Docker
    _apply_integration_test(TEST_FUNCTION, "nomad_docker.yml", True)
    _run_integration_test(
        "test_function",
        ['run', '-f', 'nomad_docker.yml', '--no-delete-success', '--no-delete-failure'],
    )

    # The resources should still exist.
    resource_name = f"{TEST_FUNCTION.name}-my_cloud_agent-{PYTHON_VERSION}"
    resources = _resources_exist(resource_name)
    assert resources["key_pair"]
    assert resources["security_group"]
    assert resources["instance"]


def test_script():
    """
    Test the output of a function deployment
    """
    # Run test, no Docker
    _apply_integration_test(TEST_SCRIPT)
    _run_integration_test(
        "test_script",
        ['run', '-f', 'nomad.yml', '--no-delete-success', '--no-delete-failure']
    )

    # Run test, with Docker
    _apply_integration_test(TEST_SCRIPT, "nomad_docker.yml", True)
    _run_integration_test(
        "test_script",
        ['run', '-f', 'nomad_docker.yml', '--no-delete-success', '--no-delete-failure']
    )

    # The resources should still exist.
    resource_name = f"{TEST_SCRIPT.name}-my_cloud_agent-{PYTHON_VERSION}"
    resources = _resources_exist(resource_name)
    assert resources["key_pair"]
    assert resources["security_group"]
    assert resources["instance"]


def test_project():
    """
    Test the output of a function deployment
    """
    # Run test, no Docker
    _apply_integration_test(TEST_PROJECT)
    _run_integration_test(
        "test_project",
        ['run', '-f', 'nomad.yml', '--no-delete-success', '--no-delete-failure']
    )

    # Run test, with Docker
    _apply_integration_test(TEST_PROJECT, "nomad_docker.yml", True)
    _run_integration_test(
        "test_project",
        ['run', '-f', 'nomad_docker.yml', '--no-delete-success', '--no-delete-failure']
    )

    # The resources should still exist.
    resource_name = f"{TEST_PROJECT.name}-my_cloud_agent-{PYTHON_VERSION}"
    resources = _resources_exist(resource_name)
    assert resources["key_pair"]
    assert resources["security_group"]
    assert resources["instance"]


def test_jupyter():
    """
    Test that a Jupyter notebook executes and that we download the executed notebook
    after a successful run.
    """
    # Run, no Docker
    _apply_integration_test(TEST_JUPYTER)
    proc = cli_runner(["run", "-f", "nomad.yml", "--no-delete-success", "--no-delete-failure"])  # noqa: E501
    assert proc.returncode == 0

    # We should see the executed notebook in our folder
    exec_nb_path = Path(TEST_JUPYTER / 'nomad_nb_exec.ipynb')
    assert exec_nb_path.is_file()
    os.unlink(exec_nb_path)

    # Run, with Docker
    _apply_integration_test(TEST_JUPYTER, "nomad_docker.yml", True)
    proc = cli_runner(["run", "-f", "nomad_docker.yml", "--no-delete-success", "--no-delete-failure"])  # noqa: E501
    assert proc.returncode == 0
    assert exec_nb_path.is_file()
    os.unlink(exec_nb_path)


def test_download_files():
    """
    Files in `download_files` are successfully downloaded upon a project's successful
    execution.
    """
    # Run, no Docker
    _apply_integration_test(TEST_DOWNLOAD_FILES)
    proc = cli_runner(["run", "-f", "nomad.yml", "--no-delete-success", "--no-delete-failure"])  # noqa: E501
    assert proc.returncode == 0

    # We should see the executed notebook in our folder
    output_key = f"{PLATFORM}_{PYTHON_VERSION}_test_download_files".replace(".", "")
    downloaded_file = Path(TEST_DOWNLOAD_FILES / f'{output_key}.txt')
    assert downloaded_file.is_file()

    # Contents of file
    with open(downloaded_file, 'r') as f:
        downloaded_file_txt = f.read()
    expected_txt = f"Hello world from our `{PLATFORM}.{PYTHON_VERSION}.test_download_files` test case!"  # noqa: E501
    assert downloaded_file_txt == expected_txt
    os.unlink(downloaded_file)

    # Run, with Docker
    _apply_integration_test(TEST_DOWNLOAD_FILES, "nomad_docker.yml", True)
    proc = cli_runner(["run", "-f", "nomad_docker.yml", "--no-delete-success", "--no-delete-failure"])  # noqa: E501
    assert proc.returncode == 0

    # We should see the executed notebook in our folder
    output_key = f"{PLATFORM}_{PYTHON_VERSION}_test_download_files".replace(".", "")
    downloaded_file = Path(TEST_DOWNLOAD_FILES / f'{output_key}.txt')
    assert downloaded_file.is_file()

    # Contents of file
    with open(downloaded_file, 'r') as f:
        downloaded_file_txt = f.read()
    expected_txt = f"Hello world from our `{PLATFORM}.{PYTHON_VERSION}.test_download_files` test case!"  # noqa: E501
    assert downloaded_file_txt == expected_txt
    os.unlink(downloaded_file)
