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
