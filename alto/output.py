"""
Alto Console manager for printing beautiful messages in the Terminal. This is *separate*
from our logging infrastructure, which is handled in `alto_logger.py`.
"""

# Imports
import argparse
from enum import Enum
import logging
import sys
from typing import Optional, List

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.spinner import Spinner
from rich.tree import Tree

from alto.constants import DEFAULT_LOGGER_NAME
from alto.ui import StageEnum


class Symbol(str, Enum):
    BUILD_SUCCESS = "[green]✓[/green]"
    SUBSTEP_BUILD_SUCCESS = "🔨"
    DELETED = "[red]✕[/red]"
    SKIPPED = "[light_goldenrod1]≫[/light_goldenrod1]"


class OutputManager:

    console: Console
    verbose: bool
    log_level: str
    logger: logging.Logger

    # Tracking
    current_renders_all: List[Tree]
    current_render: Optional[Tree]
    live: Optional[Live]

    def __init__(
        self,
        args: argparse.Namespace,
        default_logger_name: str = DEFAULT_LOGGER_NAME,
    ):
        self.console = Console(file=sys.stdout, highlight=False)
        self.args = args

        # Verbosity and log level
        self.verbose = self.args.verbose
        self.log_level = self.args.log_level

        # Logger
        self.logger = logging.getLogger(default_logger_name)

        # Tracking stuff
        self.current_renders_all = []
        self.current_render = None
        self.live = None

    def make_live(self, renderable: RenderableType):
        """
        Creates a customized `rich.Live` instance with the given renderable. The
        renderable is placed in a `rich.Group` to allow for dynamic additions later.
        """
        # If another `Live` exists, then shut it down
        if self.live is not None:
            self.stop_live()

        # Start the `Live` object so that the output appears in our console
        self.current_render_group = Group(renderable)
        live = Live(
            renderable=Group(renderable),
            console=self.console,
            transient=True,
            refresh_per_second=4
        )
        self.live = live
        self.live.start()
        return self.live

    def stop_live(self) -> None:
        """
        Stop the current `Live` object and set to `None`
        """
        if self.live is not None:
            self.live.stop()
            self.live = None

    def add_to_current_render(self,
        renderable: RenderableType
    ):
        self.current_render_group.renderables.append(renderable)

    def step_starting(self,
        message: str,
        is_substep: bool = False
    ) -> Optional[Live]:
        """
        Returns element to be rendered when a step is starting.

        args:
            message: message to log
            is_substep: boolean indicating whether step is a sub-step
        """
        # If we're in `verbose` mode, then don't do anything
        if self.verbose:
            return None

        # Otherwise, if we wish to add our step as a subtask, then we must be in a Tree
        elif is_substep:
            if not isinstance(self.current_render, Tree):
                raise ValueError("something went wrong!")
            spinner = Spinner(name="dots", text=message, style="dodger_blue2")
            subtree = Tree(spinner, guide_style="gray50")
            self.current_render.add(subtree)

            # Tracking
            self.current_renders_all.append(subtree)

        # Otherwise, we're starting a fresh Tree
        else:
            spinner = Spinner(name="dots", text=message, style="dodger_blue2")
            tree = Tree(spinner, guide_style="gray50")

            # Tracking
            self.current_renders_all.append(tree)
            self.current_render = tree

            # Make `Live`
            self.make_live(tree)

        return self.live

    def step_completed(self,
        message: RenderableType,
        is_substep: bool = False,
        symbol: Optional[Symbol] = None,
    ) -> None:
        """
        Returns the element to be rendered when a step is completed.

        args:
            message: message to log
            is_substep: boolean indicating whether step is a sub-step
        """
        if symbol is None:
            symbol = Symbol.SUBSTEP_BUILD_SUCCESS if is_substep else Symbol.BUILD_SUCCESS  # noqa
        msg = f"{symbol} {message}"

        # If we're in `verbose` mode, then don't do anything
        if self.verbose:
            return None
        else:
            tree = self.current_renders_all.pop()
            tree.label = msg

        if not is_substep:
            self.console.print(self.current_render)
            self.stop_live()

        return None

    def step_failed(self) -> None:
        """
        Returns the element to be rendered when a step is errored out.

        args:
            message: message to log
            is_substep: boolean indicating whether step is a sub-step
        """
        # If we're in `verbose` mode, then don't do anything
        if self.verbose:
            return None
        else:
            tree: Tree = self.current_renders_all.pop()

            # We know that, in our tree, the labels are always spinners. Mypy doesn't
            # know this, so it throws an error
            lbl: Spinner = tree.label  # type: ignore
            txt = lbl.text.__str__().lower().replace("...", "")
            txt = txt.replace("ec2", "EC2")
            tree.label = f"[red]✕ Failed when {txt}[/red]"  # noqa

            # Skip the remaining tasks
            while len(self.current_renders_all) > 0:
                curr_elt: Tree = self.current_renders_all.pop()
                curr_lbl: Spinner = curr_elt.label  # type: ignore
                curr_txt = curr_lbl.text.__str__()
                curr_elt.label = f"{Symbol.SKIPPED} Skipped {curr_txt.lower().replace('...', '')}"  # noqa

        self.console.print(self.current_render)
        self.stop_live()
        return None

    def log_output(self,
        agent_img_name: str,
        stage: StageEnum,
        level: str,
        msg: str,
        renderable_type: Optional[RenderableType] = None,
        is_step_completion: bool = False,
        is_substep: bool = False,
        symbol: Optional[Symbol] = None,
    ) -> None:
        """
        Log message to stdout

        args:
            agent_img_name: agent / image name to whom the log is associated
            stage: build stage. This controls what's in [...] in the logs
            level: log level
            msg: log message
        returns:
            None
        """
        # Only log if the user inputted `--verbose`. Otherwise, we will rely on other
        # methods in this class to control our output.
        if self.args.verbose:
            if level == "info":
                self.logger.info(
                    f"{agent_img_name}{stage} | {msg}"
                )
            elif level == "warn":
                self.logger.warning(
                    f"{agent_img_name}{stage} | {msg}"
                )
            elif level == "error":
                self.logger.error(
                    f"{agent_img_name}{stage} | {msg}"
                )
            elif level == "debug":
                self.logger.debug(
                    f"{agent_img_name}{stage} | {msg}"
                )
            else:
                raise ValueError(f"unrecognized `level` {level}")

        else:
            if renderable_type is not None:
                if is_step_completion:
                    self.step_completed(renderable_type, is_substep, symbol)
                else:
                    self.console.print(renderable_type)
