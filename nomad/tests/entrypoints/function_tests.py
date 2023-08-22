"""
Tess configuration for the Function child class
"""

# --------------------------------------------------------------------------------------
# cmd

BAD_COMMAND_FORMAT = {
    "type": "function",
    "src": "scripts",
    "cmd": "scripts.test_fn.hello_world"
}


# --------------------------------------------------------------------------------------
# kwargs

BAD_KWARGS = {
    "type": "function",
    "src": "scripts",
    "cmd": "test_fn.hello_world",
    "kwargs": [
        "VALUE1"
    ]
}
