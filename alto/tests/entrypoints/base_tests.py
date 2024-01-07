"""
Test configurations for the BaseEntrypoint class
"""

# Normal
NORMAL = {
    "type": "script",
    "src": "scripts",
    "cmd": "python test_fn.py",
}


# --------------------------------------------------------------------------------------
# type

UNSUPPORTED_TYPE = {
    "type": "unsupported_type_here",
    "cmd": "python <script_name>.py"
}


BAD_TYPE = {
    "type": ["jupyter", "python"],
    "cmd": "python <script_name>.py"
}


NO_TYPE = {
    "cmd": "python <script_name>.py"
}


# --------------------------------------------------------------------------------------
# cmd

BAD_COMMAND = {
    "type": "script",
    "cmd": ["python <script_name>.py"]
}


NO_COMMAND = {
    "type": "script",
}


# --------------------------------------------------------------------------------------
# src

BAD_SOURCE_TYPE = {
    "type": "script",
    "src": ["scripts"],
    "cmd": "python <script_name>.py"
}


BAD_SRC_DIR_NO_EXIST = {
    "type": "script",
    "src": "dir_does_not_exist",
    "cmd": "python <script_name>.py",
}
