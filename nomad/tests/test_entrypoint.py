"""
Test cases for Entrypoint class
"""

# Imports
import pytest
from pathlib import Path


# Internal imports
from nomad.entrypoints import (  # noqa
    MetaEntrypoint,
    BaseEntrypoint,
    Script as ScriptEntrypoint,
    Function as FunctionEntrypoint,
    Project as ProjectEntrypoint,
    Jupyter as JupyterEntrypoint,
)
from nomad.tests.entrypoints import (  # noqa
    base_tests,
    function_tests,
    jupyter_tests,
)


# Constants
ENTRYPOINT_WKDIR = Path(__file__).parent / 'entrypoints'


# Test functions
def test_base_normal_entrypoint():
    """
    A normal entrypoint loads as expected
    """
    conf = base_tests.NORMAL

    # We check the entrypoint configuration when creating the instances itself.
    entrypoint = MetaEntrypoint.get_entrypoint(name=conf["type"])(
        entrypoint_conf=conf,
        nomad_wkdir=ENTRYPOINT_WKDIR
    )
    assert isinstance(entrypoint, ScriptEntrypoint)


def test_bad_types():
    """
    An unsupported entrypoint `type`, an incorrect entrypoint `type` type, and a missing
    `type` key all throw an error.
    """
    # Unsupported type
    conf = base_tests.UNSUPPORTED_TYPE
    with pytest.raises(ValueError) as cm:
        _ = BaseEntrypoint(entrypoint_conf=conf, nomad_wkdir=ENTRYPOINT_WKDIR)
    expected_msg = "Unsupported value `unsupported_type_here` for key `type`"
    assert str(cm.value) == expected_msg

    # Bad type
    conf = base_tests.BAD_TYPE
    with pytest.raises(ValueError) as cm:
        _ = BaseEntrypoint(entrypoint_conf=conf, nomad_wkdir=ENTRYPOINT_WKDIR)
    expected_msg = "`type` is not the correct type...should be a <class 'str'>"
    assert str(cm.value) == expected_msg

    # Missing type
    conf = base_tests.NO_TYPE
    with pytest.raises(ValueError) as cm:
        _ = BaseEntrypoint(entrypoint_conf=conf, nomad_wkdir=ENTRYPOINT_WKDIR)
    expected_msg = "`type` not found in `entrypoint`'s configuration!"
    assert str(cm.value) == expected_msg


def test_bad_cmds():
    """
    An incorrect `cmd` type and a missing `cmd` throw an error
    """
    # Bad type
    conf = base_tests.BAD_COMMAND
    with pytest.raises(ValueError) as cm:
        _ = BaseEntrypoint(entrypoint_conf=conf, nomad_wkdir=ENTRYPOINT_WKDIR)
    expected_msg = "`cmd` is not the correct type...should be a <class 'str'>"
    assert str(cm.value) == expected_msg

    # Missing type
    conf = base_tests.NO_COMMAND
    with pytest.raises(ValueError) as cm:
        _ = BaseEntrypoint(entrypoint_conf=conf, nomad_wkdir=ENTRYPOINT_WKDIR)
    expected_msg = "`cmd` not found in `entrypoint`'s configuration!"
    assert str(cm.value) == expected_msg


def test_bad_src():
    """
    An incorrect `src` type and a `src` directory that doesn't exist throw an error
    """
    # Bad type
    conf = base_tests.BAD_SOURCE_TYPE
    with pytest.raises(ValueError) as cm:
        _ = BaseEntrypoint(entrypoint_conf=conf, nomad_wkdir=ENTRYPOINT_WKDIR)
    expected_msg = "`src` is not the correct type...should be a <class 'str'>"
    assert str(cm.value) == expected_msg

    # Missing type
    conf = base_tests.BAD_SRC_DIR_NO_EXIST
    with pytest.raises(ValueError) as cm:
        _ = BaseEntrypoint(entrypoint_conf=conf, nomad_wkdir=ENTRYPOINT_WKDIR)
    expected_msg = "could not parse `src` for entrypoint"
    assert str(cm.value) == expected_msg


def test_function_bad_cmd():
    """
    An poorly formatted `cmd` argument for a function entrypoint throws an error
    """
    conf = function_tests.BAD_COMMAND_FORMAT
    with pytest.raises(ValueError) as cm:
        _ = FunctionEntrypoint(entrypoint_conf=conf, nomad_wkdir=ENTRYPOINT_WKDIR)
    expected_msg = "`cmd` value not properly formatted...should be <module_name>.<function_name>"  # noqa: E501
    assert str(cm.value) == expected_msg


def test_function_bad_kwargs():
    """
    A bad `kwargs` type throws an error
    """
    conf = function_tests.BAD_KWARGS
    with pytest.raises(ValueError) as cm:
        _ = FunctionEntrypoint(entrypoint_conf=conf, nomad_wkdir=ENTRYPOINT_WKDIR)
    expected_msg = "`kwargs` is not the correct type...should be a <class 'dict'>"
    assert str(cm.value) == expected_msg


def test_jupyter_normal_entrypoint():
    """
    A normal Jupyter entrypoint loads as expected
    """
    conf = jupyter_tests.NORMAL

    # We check the entrypoint configuration when creating the instances itself.
    entrypoint = MetaEntrypoint.get_entrypoint(name=conf["type"])(
        entrypoint_conf=conf,
        nomad_wkdir=ENTRYPOINT_WKDIR
    )
    assert isinstance(entrypoint, JupyterEntrypoint)

    # Check entrypoint attributes
    assert entrypoint.src == "scripts"
    assert entrypoint.cmd == "nomad_nb.ipynb"
    assert entrypoint.kernel == "python3"
    assert entrypoint.notebook_path == "nomad_nb.ipynb"
    assert entrypoint.output_path == "nomad_nb_exec.ipynb"


def test_jupyter_no_kernel():
    """
    A Jupyter entrypoint without a kernel loads normally. The kernel defaults to
    `python3`
    """
    conf = jupyter_tests.NO_KERNEL

    # We check the entrypoint configuration when creating the instances itself.
    entrypoint = MetaEntrypoint.get_entrypoint(name=conf["type"])(
        entrypoint_conf=conf,
        nomad_wkdir=ENTRYPOINT_WKDIR
    )
    assert isinstance(entrypoint, JupyterEntrypoint)

    # Check entrypoint attributes
    assert entrypoint.src == "scripts"
    assert entrypoint.cmd == "nomad_nb.ipynb"
    assert entrypoint.notebook_path == "nomad_nb.ipynb"
    assert entrypoint.output_path == "nomad_nb_exec.ipynb"

    # Kernel
    assert hasattr(entrypoint, "kernel")
    assert entrypoint.kernel == "python3"

    # Params
    assert hasattr(entrypoint, "params")
    assert entrypoint.params == {}


def test_jupyter_bad_command():
    """
    A Jupyter entrypoint with a bad command (in this case, no papermill) throws an error
    """
    conf = jupyter_tests.BAD_COMMAND_FORMAT
    with pytest.raises(ValueError) as cm:
        _ = JupyterEntrypoint(entrypoint_conf=conf, nomad_wkdir=ENTRYPOINT_WKDIR)
    expected_msg = "`cmd` value not properly formatted...should be `<notebook_path>`"
    assert str(cm.value) == expected_msg
