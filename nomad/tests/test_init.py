"""
`init` integration tests
"""

# Imports
import os
from pathlib import Path
from click.testing import CliRunner
from nomad.main import cli
import yaml


# Nomad imports
from nomad.tests.integration.utils import (
    cli_runner
)
from nomad.templates import TEMPLATES_DIR


# Constants
TEST_DIR = Path(__file__).parent
TEST_INIT = TEST_DIR / 'init'


# Common template
with open(TEMPLATES_DIR / 'common.yml', 'r') as f:
    COMMON_TEMPLATE = yaml.safe_load(f)


def _init_test_case(_type: str, _file: str, entrypoint: str):
    os.chdir(TEST_INIT)

    # Remove the test YML, if it exits
    if (TEST_INIT / _file).is_file():
        os.unlink(TEST_INIT / _file)

    # Run init
    proc = cli_runner([
        "init",
        "--type", _type,
        "--file", _file,
        "--entrypoint", entrypoint
    ])
    assert (TEST_INIT / _file).is_file()
    assert proc.returncode == 0

    # Load the YML
    with open(TEST_INIT / _file, 'r') as f:
        init_yml = yaml.safe_load(f)
    return init_yml


def test_normal_init_iterations():
    """
    Test the output of a function deployment
    """
    for infra in ["ec2"]:
        for ep in ["script", "project", "jupyter", "function"]:
            actual_template = _init_test_case(
                _type=infra,
                _file=f"normal_{infra}_{ep}.yml",
                entrypoint=ep,
            )

            # Create the expected template
            with open(TEMPLATES_DIR / 'infra' / f"{infra}.yml", 'r') as f:
                infra_template = yaml.safe_load(f)
            with open(TEMPLATES_DIR / 'entrypoints' / f"{ep}.yml", 'r') as f:
                entrypoint_template = yaml.safe_load(f)
            expected_template = {
                "my_cloud_agent": {
                    "infra": infra_template["infra"],
                    "entrypoint": entrypoint_template["entrypoint"]
                }
            }
            expected_template["my_cloud_agent"].update(COMMON_TEMPLATE)

            # Test
            assert actual_template == expected_template


def test_init_bad_type():
    """
    An unsupported type produces an error
    """
    _file = "error_emr_script.yml"
    runner = CliRunner()
    result = runner.invoke(cli, [
        "init",
        "--type", "emr",
        "--file", _file,
        "--entrypoint", "script"
    ])
    assert result.exit_code != 0
    assert not (TEST_INIT / _file).is_file()


def test_init_bad_entrypoint():
    """
    An unsupported entrypoint produces an error
    """
    _file = "error_ec2_unsupportedep.yml"
    runner = CliRunner()
    result = runner.invoke(cli, [
        "init",
        "--type", "ec2",
        "--file", _file,
        "--entrypoint", "unsupportedep"
    ])
    assert result.exit_code != 0
    assert not (TEST_INIT / _file).is_file()
