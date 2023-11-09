"""
Test cases for util functions
"""

# Imports
from pathlib import Path
from nomad.utils import paths_flattener


# Tests
def test_paths_flattener_1():
    list_of_paths = [
        Path('/Users/username/Documents/test/project/'),
        Path('/Users/username/Documents/test/common1/'),
        Path('/Users/username/Desktop/common2/'),
    ]
    flattened_paths = paths_flattener(list_of_paths)
    expected_flattened_paths = [
        Path('Documents/test/project/'),
        Path('Documents/test/common1/'),
        Path('Desktop/common2/'),
    ]
    assert flattened_paths == expected_flattened_paths


def test_paths_flattener_2():
    list_of_paths = [
        Path('/Users/username/Documents/test/project/'),
        Path('/Users/username/Documents/test/common1/'),
    ]
    flattened_paths = paths_flattener(list_of_paths)
    expected_flattened_paths = [
        Path('project/'),
        Path('common1/'),
    ]
    assert flattened_paths == expected_flattened_paths


def test_paths_flattener_single_item():
    list_of_paths = [
        Path('/Users/username/Documents/test/project/'),
    ]
    flattened_paths = paths_flattener(list_of_paths)
    expected_flattened_paths = [
        Path('project/'),
    ]
    assert flattened_paths == expected_flattened_paths
