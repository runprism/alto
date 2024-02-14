"""
`run` integration tests (i.e., full runs on micro EC2 instances).
"""

# Imports
import os
from pathlib import Path
from alto.tests.integration.utils import (
    cli_runner,
    _resources_exist,
    _apply_integration_test,
    _run_integration_test,
)
from alto.constants import (
    PYTHON_VERSION,
    PLATFORM,
)


# Constants
TEST_DIR = Path(__file__).parent
TEST_FUNCTION = TEST_DIR / 'function'
TEST_JUPYTER = TEST_DIR / 'jupyter'
TEST_PROJECT = TEST_DIR / 'project'
TEST_SCRIPT = TEST_DIR / 'script'
TEST_DOWNLOAD_FILES = TEST_DIR / 'artifacts'


# Tests
def test_function():
    """
    Test the output of a function deployment
    """
    # Run test, no Docker
    _apply_integration_test(TEST_FUNCTION)
    _run_integration_test(
        "test_function",
        ['run', '-f', 'alto.yml', '--no-delete-success', '--no-delete-failure']
    )

    # Run test, with Docker
    _apply_integration_test(TEST_FUNCTION, "alto_docker.yml", True)
    _run_integration_test(
        "test_function",
        ['run', '-f', 'alto_docker.yml', '--no-delete-success', '--no-delete-failure'],
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
        ['run', '-f', 'alto.yml', '--no-delete-success', '--no-delete-failure']
    )

    # Run test, with Docker
    _apply_integration_test(TEST_SCRIPT, "alto_docker.yml", True)
    _run_integration_test(
        "test_script",
        ['run', '-f', 'alto_docker.yml', '--no-delete-success', '--no-delete-failure']
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
        ['run', '-f', 'alto.yml', '--no-delete-success', '--no-delete-failure']
    )

    # Run test, with Docker
    _apply_integration_test(TEST_PROJECT, "alto_docker.yml", True)
    _run_integration_test(
        "test_project",
        ['run', '-f', 'alto_docker.yml', '--no-delete-success', '--no-delete-failure']
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
    proc = cli_runner(["run", "-f", "alto.yml", "--no-delete-success", "--no-delete-failure"])  # noqa: E501
    assert proc.returncode == 0

    # We should see the executed notebook in our folder
    exec_nb_path = Path(TEST_JUPYTER / 'alto_nb_exec.ipynb')
    assert exec_nb_path.is_file()
    os.unlink(exec_nb_path)

    # Run, with Docker
    _apply_integration_test(TEST_JUPYTER, "alto_docker.yml", True)
    proc = cli_runner(["run", "-f", "alto_docker.yml", "--no-delete-success", "--no-delete-failure"])  # noqa: E501
    assert proc.returncode == 0
    assert exec_nb_path.is_file()
    os.unlink(exec_nb_path)


def test_artifacts():
    """
    Files in `artifacts` are successfully downloaded upon a project's successful
    execution.
    """
    # Run, no Docker
    _apply_integration_test(TEST_DOWNLOAD_FILES)
    proc = cli_runner(["run", "-f", "alto.yml", "--no-delete-success", "--no-delete-failure"])  # noqa: E501
    assert proc.returncode == 0

    # We should see the executed notebook in our folder
    output_key = f"{PLATFORM}_{PYTHON_VERSION}_test_artifacts".replace(".", "")
    downloaded_file = Path(TEST_DOWNLOAD_FILES / f'{output_key}.txt')
    assert downloaded_file.is_file()

    # Contents of file
    with open(downloaded_file, 'r') as f:
        downloaded_file_txt = f.read()
    expected_txt = f"Hello world from our `{PLATFORM}.{PYTHON_VERSION}.test_artifacts` test case!"  # noqa: E501
    assert downloaded_file_txt == expected_txt
    os.unlink(downloaded_file)

    # Run, with Docker
    _apply_integration_test(TEST_DOWNLOAD_FILES, "alto_docker.yml", True)
    proc = cli_runner(["run", "-f", "alto_docker.yml", "--no-delete-success", "--no-delete-failure"])  # noqa: E501
    assert proc.returncode == 0

    # We should see the executed notebook in our folder
    output_key = f"{PLATFORM}_{PYTHON_VERSION}_test_artifacts".replace(".", "")
    downloaded_file = Path(TEST_DOWNLOAD_FILES / f'{output_key}.txt')
    assert downloaded_file.is_file()

    # Contents of file
    with open(downloaded_file, 'r') as f:
        downloaded_file_txt = f.read()
    expected_txt = f"Hello world from our `{PLATFORM}.{PYTHON_VERSION}.test_artifacts` test case!"  # noqa: E501
    assert downloaded_file_txt == expected_txt
    os.unlink(downloaded_file)
