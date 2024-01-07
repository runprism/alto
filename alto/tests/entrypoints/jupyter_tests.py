"""
Tess configuration for the Jupyter child class
"""

# --------------------------------------------------------------------------------------
# normal

NORMAL = {
    "type": "jupyter",
    "kernel": "python3",
    "src": "scripts",
    "cmd": "alto_nb.ipynb"
}


# --------------------------------------------------------------------------------------
# no kernel / params

NO_KERNEL = {
    "type": "jupyter",
    "src": "scripts",
    "cmd": "alto_nb.ipynb"
}


# --------------------------------------------------------------------------------------
# cmd

BAD_COMMAND_FORMAT = {
    "type": "jupyter",
    "kernel": "python3",
    "src": "scripts",
    "cmd": "papermill alto_nb.ipynb alto_exec_nb.ipynb"
}
