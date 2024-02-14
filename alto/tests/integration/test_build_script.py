"""
`build` integration tests (i.e., full runs on micro EC2 instances).
"""

# Imports
from pathlib import Path
from alto.tests.integration.utils import (
    _build_integration_test
)


# Constants
TEST_DIR = Path(__file__).parent
TEST_FUNCTION = TEST_DIR / 'function'
TEST_JUPYTER = TEST_DIR / 'jupyter'
TEST_PROJECT = TEST_DIR / 'project'
TEST_SCRIPT = TEST_DIR / 'script'


# Tests
def test_function():
    """
    Test the output of a function deployment
    """
    _build_integration_test(TEST_FUNCTION, "test_function")
    _build_integration_test(TEST_FUNCTION, "test_function", "alto_docker.yml", True)


def test_script():
    """
    Test the output of a function deployment
    """
    _build_integration_test(TEST_SCRIPT, "test_script")
    _build_integration_test(TEST_SCRIPT, "test_script", "alto_docker.yml", True)


def test_project():
    """
    Test the output of a function deployment
    """
    _build_integration_test(TEST_PROJECT, "test_project")
    _build_integration_test(TEST_PROJECT, "test_project", "alto_docker.yml", True)
