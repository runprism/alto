"""
Test cases for Infra class
"""

# Imports
import pytest
from pathlib import Path


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
        "ami_image": "ami-01c647eace872fc02"
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
