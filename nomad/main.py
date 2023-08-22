"""
Entrypoint into Nomad
"""


# Importa
import argparse
import rich_click as click
from nomad.tasks import (
    apply as apply_task,
    run as run_task,
    build as build_task,
    delete as delete_task,
)
from pathlib import Path
import os


# Use markup
click.rich_click.USE_RICH_MARKUP = True


# Construct command
@click.group
def cli():
    pass


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
def apply(file: str, name: str, log_level: str):
    args = argparse.Namespace()
    args.file = file
    args.name = name
    args.wkdir = Path(os.path.abspath(file)).parent
    args.log_level = log_level

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
def run(
    file: str,
    name: str,
    log_level: str,
    no_delete_failure: bool,
    no_delete_success: bool
):
    args = argparse.Namespace()
    args.file = file
    args.name = name
    args.wkdir = Path(os.path.abspath(file)).parent
    args.log_level = log_level
    args.no_delete_failure = no_delete_failure
    args.no_delete_success = no_delete_success

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
def build(
    file: str,
    name: str,
    log_level: str,
    no_delete_failure: bool,
    no_delete_success: bool,
):
    args = argparse.Namespace()
    args.file = file
    args.name = name
    args.wkdir = Path(os.path.abspath(file)).parent
    args.log_level = log_level
    args.no_delete_failure = no_delete_failure
    args.no_delete_success = no_delete_success

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
