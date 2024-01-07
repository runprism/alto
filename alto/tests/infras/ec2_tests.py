"""
EC2 infra configuration tests
"""

# --------------------------------------------------------------------------------------
# cmd

NORMAL_FORMAT = {
    "type": "ec2",
    "instance_type": "c1.medium",
    "ami_image": "ami-01c647eace872fc02"
}


# --------------------------------------------------------------------------------------
# Instance type

BAD_INSTANCE_TYPE = {
    "type": "ec2",
    "instance_type": "t2.abcedfg",
}


# --------------------------------------------------------------------------------------
# Python version (major only)

PYTHON_VERSION_MAJOR = {
    "type": "ec2",
    "instance_type": "c1.medium",
    "python_version": 2,
}


# --------------------------------------------------------------------------------------
# Python version (major, minor)

PYTHON_VERSION_MAJOR_MINOR = {
    "type": "ec2",
    "instance_type": "c1.medium",
    "python_version": 3.6,
}


# --------------------------------------------------------------------------------------
# Python version (major, minor, micro)

PYTHON_VERSION_MAJOR_MINOR_MICRO = {
    "type": "ec2",
    "instance_type": "c1.medium",
    "python_version": "3.11.6",
}


# --------------------------------------------------------------------------------------
# Bad Python version

BAD_PYTHON_VERSION = {
    "type": "ec2",
    "instance_type": "c1.medium",
    "python_version": "3.11.89",
}
