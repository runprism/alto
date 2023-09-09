"""
Entrypoint into Nomad
"""


# Importa
import argparse
import rich_click as click
from pathlib import Path
import os
from typing import Optional

# Internal imports
from nomad.tasks import (
    apply as apply_task,
    run as run_task,
    build as build_task,
    delete as delete_task,
    init as init_task,
)
from nomad.constants import (
    SUPPORTED_AGENTS
)
import nomad.ui


# Use markup
click.rich_click.USE_RICH_MARKUP = True


# Construct command
@click.group
def cli():
    pass


@cli.command()
@click.option(
    "--type",
    help="""Type of cloud environment to use""",
    required=False
)
@click.option(
    "--file", "-f",
    type=str,
    help="""Name of new Nomad configuration file. [dim]\[default: nomad.yml][/]""",  # noqa
    required=False,
)
@click.option(
    '--log-level', '-l',
    type=click.Choice(['info', 'warn', 'error', 'debug']),
    default="info",
    help="""Set the log level. [dim]\[default: info][/]""",  # noqa
    required=False
)
def init(type: Optional[str], file: Optional[str], log_level: str):
    env_options = "|".join([
        f"{nomad.ui.BRIGHT_YELLOW}{e}{nomad.ui.RESET}" for e in SUPPORTED_AGENTS
    ])
    if type is None:
        click.echo(" ")
        type = click.prompt(f"What type of cloud environment do you want to use [{env_options}]?")  # noqa: E501
        if type not in SUPPORTED_AGENTS:
            raise ValueError(f"unsupported type `{type}`")
    if file is None:
        file = click.prompt(
            f"What would you like the name of your configuration file to be {nomad.ui.GRAY}[default: nomad.yml]{nomad.ui.RESET}?",  # noqa: E501
            default="nomad.yml",
            show_default=False
        )
        click.echo(" ")

    args = argparse.Namespace()
    args.type = type
    args.file = file
    args.wkdir = Path(os.path.abspath(file)).parent
    args.log_level = log_level

    # Apply task
    task = init_task.InitTask(args)
    return task.run()


@cli.command()
@click.option(
    "--file", "-f",
    type=str,
    help="""Nomad configuration file.""",
    required=True
)
@click.option(
    "--name",
    help="""Name of agent within Nomad configuration file.""",
    required=False
)
@click.option(
    '--log-level', '-l',
    type=click.Choice(['info', 'warn', 'error', 'debug']),
    default="info",
    help="""Set the log level. [dim]\[default: info][/]""",  # noqa
    required=False
)
@click.option(
    '--whitelist-all',
    is_flag=True,
    default=False,
    help="""Whitelist all IP addresses. If `False`, then only whitelist your current IP address. [dim]\[default: False][/]""",  # noqa
    required=False,
)
def apply(file: str, name: str, log_level: str, whitelist_all: bool):
    args = argparse.Namespace()
    args.file = file
    args.name = name
    args.wkdir = Path(os.path.abspath(file)).parent
    args.log_level = log_level
    args.whitelist_all = whitelist_all

    # Apply task
    task = apply_task.ApplyTask(args)
    return task.run()


@cli.command()
@click.option(
    "--file", "-f",
    type=str,
    help="""Nomad configuration file.""",
    required=True
)
@click.option(
    "--name",
    help="""Name of agent within Nomad configuration file.""",
    required=False
)
@click.option(
    '--log-level', '-l',
    type=click.Choice(['info', 'warn', 'error', 'debug']),
    default="info",
    help="""Set the log level. [dim]\[default: info][/]""",  # noqa
    required=False
)
@click.option(
    '--no-delete-failure',
    is_flag=True,
    default=False,
    help="""Preserve the cloud resources after a failed run. [dim]\[default: False][/]""",  # noqa
    required=False
)
@click.option(
    '--no-delete-success',
    is_flag=True,
    default=False,
    help="""Preserve the cloud resources after a successful run. [dim]\[default: False][/]""",  # noqa
    required=False
)
@click.option(
    '--whitelist-all',
    is_flag=True,
    default=False,
    help="""Whitelist all IP addresses. If `False`, then only whitelist your current IP address. [dim]\[default: False][/]""",  # noqa
    required=False,
)
def run(
    file: str,
    name: str,
    log_level: str,
    no_delete_failure: bool,
    no_delete_success: bool,
    whitelist_all: bool,
):
    args = argparse.Namespace()
    args.file = file
    args.name = name
    args.wkdir = Path(os.path.abspath(file)).parent
    args.log_level = log_level
    args.no_delete_failure = no_delete_failure
    args.no_delete_success = no_delete_success
    args.whitelist_all = whitelist_all

    # Run task
    task = run_task.RunTask(args)
    return task.run()


@cli.command()
@click.option(
    "--file", "-f",
    type=str,
    help="""Nomad configuration file.""",
    required=True
)
@click.option(
    "--name",
    help="""Name of agent within Nomad configuration file.""",
    required=False
)
@click.option(
    '--log-level', '-l',
    type=click.Choice(['info', 'warn', 'error', 'debug']),
    default="info",
    help="""Set the log level. [dim]\[default: info][/]""",  # noqa
    required=False
)
@click.option(
    '--no-delete-failure',
    is_flag=True,
    default=False,
    help="""Preserve the cloud resources after a failed build. [dim]\[default: False][/]""",  # noqa
)
@click.option(
    '--no-delete-success',
    is_flag=True,
    default=False,
    help="""Preserve the cloud resources after a successful build. [dim]\[default: False][/]""",  # noqa
    required=False
)
@click.option(
    '--whitelist-all',
    is_flag=True,
    default=False,
    help="""Whitelist all IP addresses. If `False`, then only whitelist your current IP address. [dim]\[default: False][/]""",  # noqa
    required=False,
)
def build(
    file: str,
    name: str,
    log_level: str,
    no_delete_failure: bool,
    no_delete_success: bool,
    whitelist_all: bool,
):
    args = argparse.Namespace()
    args.file = file
    args.name = name
    args.wkdir = Path(os.path.abspath(file)).parent
    args.log_level = log_level
    args.no_delete_failure = no_delete_failure
    args.no_delete_success = no_delete_success
    args.whitelist_all = whitelist_all

    # Build task
    task = build_task.BuildTask(args)
    return task.run()


@cli.command()
@click.option(
    "--file", "-f",
    type=str,
    help="""Nomad configuration file.""",
    required=True
)
@click.option(
    "--name",
    help="""Name of agent within Nomad configuration file.""",
    required=False
)
@click.option(
    '--log-level', '-l',
    type=click.Choice(['info', 'warn', 'error', 'debug']),
    default="info",
    help="""Set the log level. [dim]\[default: info][/]""",  # noqa
    required=False
)
def delete(file: str, name: str, log_level: str):
    args = argparse.Namespace()
    args.file = file
    args.name = name
    args.wkdir = Path(os.path.abspath(file)).parent
    args.log_level = log_level

    # Delete task
    task = delete_task.DeleteTask(args)
    return task.run()
