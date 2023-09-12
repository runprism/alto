"""
Tess configuration for the Jupyter child class
"""

# --------------------------------------------------------------------------------------
# normal

NORMAL = {
    "type": "jupyter",
    "kernel": "python3",
    "src": "scripts",
    "cmd": "nomad_nb.ipynb"
}


# --------------------------------------------------------------------------------------
# no kernel / params

NO_KERNEL = {
    "type": "jupyter",
    "src": "scripts",
    "cmd": "nomad_nb.ipynb"
}


# --------------------------------------------------------------------------------------
# cmd

BAD_COMMAND_FORMAT = {
    "type": "jupyter",
    "kernel": "python3",
    "src": "scripts",
    "cmd": "papermill nomad_nb.ipynb nomad_exec_nb.ipynb"
}
