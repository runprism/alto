"""
Test cases for Infra class
"""

# Imports
import pytest
from pathlib import Path
import requests


# Internal imports
from nomad.infras import (  # noqa
    MetaInfra,
    BaseInfra,
    Ec2 as Ec2Infra,
)
from nomad.tests.infras import (  # noqa
    base_tests,
    ec2_tests,
)


# Constants
INFRA_WKDIR = Path(__file__).parent / 'infras'


# Test functions
def test_bad_types():
    """
    An unsupported infra `type`, an incorrect infra `type` type, and a missing
    `type` key all throw an error.
    """
    # Unsupported type
    conf = base_tests.UNSUPPORTED_TYPE
    with pytest.raises(ValueError) as cm:
        _ = BaseInfra(infra_conf=conf, nomad_wkdir=INFRA_WKDIR)
    expected_msg = "Unsupported value `unsupported_type_here` for key `type`"
    assert str(cm.value) == expected_msg

    # Bad type
    conf = base_tests.BAD_TYPE
    with pytest.raises(ValueError) as cm:
        _ = BaseInfra(infra_conf=conf, nomad_wkdir=INFRA_WKDIR)
    expected_msg = "`type` is not the correct type...should be a <class 'str'>"
    assert str(cm.value) == expected_msg

    # Missing type
    conf = base_tests.NO_TYPE
    with pytest.raises(ValueError) as cm:
        _ = BaseInfra(infra_conf=conf, nomad_wkdir=INFRA_WKDIR)
    expected_msg = "`type` not found in `infra`'s configuration!"
    assert str(cm.value) == expected_msg


def test_normal_ec2_infra():
    """
    A normal EC2 infra is parsed as expected
    """
    conf = ec2_tests.NORMAL_FORMAT
    infra = Ec2Infra(infra_conf=conf, nomad_wkdir=INFRA_WKDIR)

    # Expected conf
    expected_conf = {
        "type": "ec2",
        "instance_type": "c1.medium",
        "ami_image": "ami-01c647eace872fc02",
        "python_version": "",
    }
    assert infra.infra_conf == expected_conf


def test_bad_ec2():
    """
    A normal EC2 infra is parsed as expected
    """
    conf = ec2_tests.BAD_INSTANCE_TYPE
    with pytest.raises(ValueError) as cm:
        _ = Ec2Infra(infra_conf=conf, nomad_wkdir=INFRA_WKDIR)
    expected_msg = "Unsupported value `t2.abcedfg` for key `instance_type`"
    assert str(cm.value) == expected_msg


def test_python_major():
    """
    Test Python version when only the `major` version is specified. The `major` version
    is 2.
    """
    conf = ec2_tests.PYTHON_VERSION_MAJOR
    infra = Ec2Infra(infra_conf=conf, nomad_wkdir=INFRA_WKDIR)
    assert "2.7.18" == infra.infra_conf["python_version"]


def test_python_major_minor():
    """
    Test Python version when the `major` and `minor` versions are specified.
    """
    conf = ec2_tests.PYTHON_VERSION_MAJOR_MINOR
    infra = Ec2Infra(infra_conf=conf, nomad_wkdir=INFRA_WKDIR)
    assert "3.6.15" == infra.infra_conf["python_version"]


def test_python_major_minor_micro():
    """
    Test Python version when the `major`, `minor`, and `micro` are all specified
    """
    conf = ec2_tests.PYTHON_VERSION_MAJOR_MINOR_MICRO
    infra = Ec2Infra(infra_conf=conf, nomad_wkdir=INFRA_WKDIR)
    assert "3.11.6" == infra.infra_conf["python_version"]


def test_python_bad_version():
    """
    Test Python version when the `major`, `minor`, and `micro` are all specified
    """
    conf = ec2_tests.BAD_PYTHON_VERSION
    with pytest.raises(requests.exceptions.HTTPError) as cm:
        _ = Ec2Infra(infra_conf=conf, nomad_wkdir=INFRA_WKDIR)
    expected_msg = "404 Client Error: Not Found for url: https://www.python.org/ftp/python/3.11.89/"  # noqa
    assert expected_msg == str(cm.value)
