"""
Test configurations for the BaseInfra class
"""

# --------------------------------------------------------------------------------------
# type

UNSUPPORTED_TYPE = {
    "type": "unsupported_type_here",
}


BAD_TYPE = {
    "type": ["jupyter", "python"],
}


NO_TYPE = {
    "instance_type": "t2.micro"
}
