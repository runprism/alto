"""
Test cases for YmlParser class
"""

# Imports
from pathlib import Path
from nomad.constants import (
    PLATFORM,
    PYTHON_VERSION,
)
from nomad.examples import EXAMPLES_DIR
from nomad.parsers.yml import YmlParser


# Constants
EC2_EXAMPLES_DIR = EXAMPLES_DIR / 'ec2'
INTEGRATION_TEST_DIR = Path(__file__).parent / 'integration'
EC2_EXAMPLES = [
    EC2_EXAMPLES_DIR / 'additional_paths.yml',
    EC2_EXAMPLES_DIR / 'basic_function.yml',
    EC2_EXAMPLES_DIR / 'basic_project.yml',
    EC2_EXAMPLES_DIR / 'basic_script.yml',
    EC2_EXAMPLES_DIR / 'env_vars.yml',
    EC2_EXAMPLES_DIR / 'basic_jupyter.yml',
    EC2_EXAMPLES_DIR / 'download_files.yml',
    INTEGRATION_TEST_DIR / 'download_files' / 'nomad.yml'
]


# Tests
def test_yml_parser():
    confs = []

    # Load and check the task name
    for _p in EC2_EXAMPLES:
        parser = YmlParser(_p)
        conf = parser.parse()
        confs.append(conf)

    # Expected configurations
    expected_conf_0 = {
        "my_cloud_agent": {
            "infra": {
                "type": "ec2",
                "instance_type": "t2.micro",
                "ami_image": "ami-01c647eace872fc02",
            },
            "requirements": "requirements.txt",
            "entrypoint": {
                "type": "function",
                "cmd": "<script_name>.<function_name>",
                "kwargs": {
                    "kwarg1": "value1",
                }
            },
            "additional_paths": [
                str(EC2_EXAMPLES_DIR)
            ]
        }
    }

    expected_conf_1 = {
        "my_cloud_agent": {
            "infra": {
                "type": "ec2",
                "instance_type": "t2.micro",
                "ami_image": "ami-01c647eace872fc02",
            },
            "requirements": "requirements.txt",
            "entrypoint": {
                "type": "function",
                "cmd": "<script_name>.<function_name>",
                "kwargs": {
                    "kwarg1": "value1",
                }
            },
        }
    }

    expected_conf_2 = {
        "my_cloud_agent": {
            "infra": {
                "type": "ec2",
                "instance_type": "t2.micro",
                "ami_image": "ami-01c647eace872fc02",
            },
            "requirements": "requirements.txt",
            "entrypoint": {
                "type": "project",
                "src": "app/",
                "cmd": "python <script_name>.py"
            },
        }
    }

    expected_conf_3 = {
        "my_cloud_agent": {
            "infra": {
                "type": "ec2",
                "instance_type": "t2.micro",
                "ami_image": "ami-01c647eace872fc02",
            },
            "requirements": "requirements.txt",
            "entrypoint": {
                "type": "script",
                "cmd": "python <script_name>.py"
            },
        }
    }

    expected_conf_4 = {
        "my_cloud_agent": {
            "infra": {
                "type": "ec2",
                "instance_type": "t2.micro",
                "ami_image": "ami-01c647eace872fc02",
            },
            "requirements": "requirements.txt",
            "entrypoint": {
                "type": "script",
                "cmd": "python <script_name>.py"
            },
            "env": {
                "ENV_VAR_1": "ENV_VALUE_1"
            }
        }
    }

    expected_conf_5 = {
        "my_cloud_agent": {
            "infra": {
                "type": "ec2",
                "instance_type": "t2.micro",
                "ami_image": "ami-01c647eace872fc02",
            },
            "requirements": "requirements.txt",
            "entrypoint": {
                "type": "jupyter",
                "kernel": "python3",
                "cmd": "papermill <notebook_path>.ipynb <output_path>.ipynb"
            },
        }
    }

    expected_conf_6 = {
        "my_cloud_agent": {
            "infra": {
                "type": "ec2",
                "instance_type": "t2.micro",
                "ami_image": "ami-01c647eace872fc02",
            },
            "requirements": "requirements.txt",
            "entrypoint": {
                "type": "script",
                "cmd": "python <script name>.py --dim1 DIM1 --dim2 DIM2"
            },
            "download_files": ["file1.txt", "file2.txt"]
        }
    }

    expected_conf_7 = {
        f"my_cloud_agent-{PYTHON_VERSION}": {
            "infra": {
                "type": "ec2",
                "instance_type": "t2.micro",
                "ami_image": "ami-01c647eace872fc02",
            },
            "entrypoint": {
                "type": "script",
                "cmd": f"python main.py --output-name test_download_files --python-version {PYTHON_VERSION} --platform {PLATFORM}"  # noqa: E501
            },
            "download_files": [f'{PLATFORM}_{PYTHON_VERSION.replace(".", "")}_test_download_files.txt']  # noqa: E501
        }
    }

    assert confs[0] == expected_conf_0
    assert confs[1] == expected_conf_1
    assert confs[2] == expected_conf_2
    assert confs[3] == expected_conf_3
    assert confs[4] == expected_conf_4
    assert confs[5] == expected_conf_5
    assert confs[6] == expected_conf_6
    assert confs[7] == expected_conf_7
