"""
`build` integration tests (i.e., full runs on micro EC2 instances).
"""

# Imports
import os
from pathlib import Path
from typing import List


from alto.constants import PLATFORM, PYTHON_VERSION
from alto.tests.integration.utils import (
    _apply_integration_test,
    _build_integration_test_with_s3_file,
    cli_runner,
)


# Constants
TEST_DIR = Path(__file__).parent
TEST_FUNCTION = TEST_DIR / 'function'
TEST_JUPYTER = TEST_DIR / 'jupyter'
TEST_PROJECT = TEST_DIR / 'project'
TEST_SCRIPT = TEST_DIR / 'script'
TEST_ARTIFACTS = TEST_DIR / 'artifacts'


# Tests
def test_function_ssh():
    """
    Test the output of a function deployment
    """
    _build_integration_test_with_s3_file(
        TEST_FUNCTION,
        "test_function"
    )
    _build_integration_test_with_s3_file(
        TEST_FUNCTION,
        "test_function",
        "alto_docker.yml",
        True
    )


def test_function_ssm():
    """
    Test the output of a function deployment
    """
    _build_integration_test_with_s3_file(
        TEST_FUNCTION,
        "test_function",
        "alto_ssm.yml",
        resources_to_check=["instance", "instance_profile"],
        resource_name_suffix="-ssm",
    )
    _build_integration_test_with_s3_file(
        TEST_FUNCTION,
        "test_function",
        "alto_ssm_docker.yml",
        True,
        resources_to_check=["instance", "instance_profile"],
        resource_name_suffix="-ssm",
    )


def test_script_ssh():
    """
    Test the output of a function deployment
    """
    _build_integration_test_with_s3_file(
        TEST_SCRIPT,
        "test_script"
    )
    _build_integration_test_with_s3_file(
        TEST_SCRIPT,
        "test_script",
        "alto_docker.yml",
        True
    )


def test_script_ssm():
    _build_integration_test_with_s3_file(
        TEST_SCRIPT,
        "test_script",
        "alto_ssm.yml",
        resources_to_check=["instance", "instance_profile"],
        resource_name_suffix="-ssm",
    )
    _build_integration_test_with_s3_file(
        TEST_SCRIPT,
        "test_script",
        "alto_ssm_docker.yml",
        True,
        resources_to_check=["instance", "instance_profile"],
        resource_name_suffix="-ssm",
    )


def _jupyter_run(
    conf_fname: str,
    docker: bool = False,
    resources_to_check: List[str] = ["key_pair", "security_group", "instance"],
    resource_name_suffix: str = ""
):
    _apply_integration_test(
        test_path=TEST_JUPYTER,
        conf_fname=conf_fname,
        docker=docker,
        resources_to_check=resources_to_check,
        resource_name_suffix=resource_name_suffix,
    )
    proc = cli_runner(["run", "-f", conf_fname, "--no-delete-success", "--no-delete-failure", "--verbose"])  # noqa: E501
    assert proc.returncode == 0

    # We should see the executed notebook in our folder
    exec_nb_path = Path(TEST_JUPYTER / 'src' / 'alto_nb_exec.ipynb')
    assert exec_nb_path.is_file()
    os.unlink(exec_nb_path)


def test_jupyter_ssh():
    """
    Test that a Jupyter notebook executes and that we download the executed notebook
    after a successful run.
    """
    _jupyter_run("alto.yml")
    _jupyter_run("alto_docker.yml", docker=True)


def test_jupyter_ssm():
    _jupyter_run(
        "alto_ssm.yml",
        resources_to_check=["instance", "instance_profile"],
        resource_name_suffix="-ssm",
    )
    _jupyter_run(
        "alto_ssm_docker.yml",
        docker=True,
        resources_to_check=["instance", "instance_profile"],
        resource_name_suffix="-ssm",
    )


def _artifacts_run(
    conf_fname: str,
    docker: bool = False,
    resources_to_check: List[str] = ["key_pair", "security_group", "instance"],
    resource_name_suffix: str = "",
):
    _apply_integration_test(
        test_path=TEST_ARTIFACTS,
        conf_fname=conf_fname,
        docker=docker,
        resources_to_check=resources_to_check,
        resource_name_suffix=resource_name_suffix,
    )
    proc = cli_runner(["run", "-f", conf_fname, "--no-delete-success", "--no-delete-failure", "--verbose"])  # noqa: E501
    assert proc.returncode == 0

    # We should see the executed notebook in our folder
    output_key = f"{PLATFORM}_{PYTHON_VERSION}_test_artifacts".replace(".", "")
    downloaded_file = Path(TEST_ARTIFACTS / f'{output_key}.txt')
    assert downloaded_file.is_file()

    # Contents of file
    with open(downloaded_file, 'r') as f:
        downloaded_file_txt = f.read()
    expected_txt = f"Hello world from our `{PLATFORM}.{PYTHON_VERSION}.test_artifacts` test case!"  # noqa: E501
    assert downloaded_file_txt == expected_txt
    os.unlink(downloaded_file)


def test_artifacts_ssh():
    """
    Files in `artifacts` are successfully downloaded upon a project's successful
    execution.
    """
    _artifacts_run("alto.yml")
    _artifacts_run("alto_docker.yml", docker=True)


def test_artifacts_ssm():
    _artifacts_run(
        "alto_ssm.yml",
        resources_to_check=["instance", "instance_profile"],
        resource_name_suffix="-ssm",
    )
    _artifacts_run(
        "alto_ssm_docker.yml",
        docker=True,
        resources_to_check=["instance", "instance_profile"],
        resource_name_suffix="-ssm",
    )
