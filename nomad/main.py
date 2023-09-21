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
    SUPPORTED_AGENTS,
    SUPPORTED_ENTRYPOINTS,
)
import nomad.ui


# Use markup
# click.rich_click.USE_RICH_MARKUP = True
click.rich_click.USE_MARKDOWN = True


# Construct command
@click.group
def cli():
    """Run your code on any cloud environment (e.g., EC2 instances, EMR clusters,
    etc.)"""
    pass


@cli.command()
@click.option(
    "--type",
    type=click.Choice(SUPPORTED_AGENTS),
    help="""Type of cloud environment to use""",
    required=False
)
@click.option(
    "--file", "-f",
    type=str,
    help=f"""Name of new Nomad configuration file. _{nomad.ui.GRAY}[default: nomad.yml]{nomad.ui.RESET}_""",  # noqa
    required=False,
)
@click.option(
    "--entrypoint", "-f",
    type=click.Choice(SUPPORTED_ENTRYPOINTS),
    help=f"""Entrypoint type. _{nomad.ui.GRAY}[default: script]{nomad.ui.RESET}_""",  # noqa
    required=False,
)
@click.option(
    '--log-level', '-l',
    type=click.Choice(['info', 'warn', 'error', 'debug']),
    default="info",
    help=f"""Set the log level. _{nomad.ui.GRAY}[default: info]{nomad.ui.RESET}_""",
    required=False,
)
def init(
    type: Optional[str],
    file: Optional[str],
    entrypoint: Optional[str],
    log_level: str
):
    """Create a configuration YAML

    Examples:
    - nomad init --type ec2 --entrypoint script
    - nomad init --type ec2 --file ec2.yml
    """
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
    if entrypoint is None:
        entrypoint = click.prompt(
            f"What is your code's entrypoint? {nomad.ui.GRAY}[default: script]{nomad.ui.RESET}?",  # noqa: E501
            default="script",
            show_default=False
        )
        if entrypoint not in SUPPORTED_ENTRYPOINTS:
            raise ValueError(f"unsupported entrypoint `{entrypoint}`")

    if (type is None or file is None or entrypoint is None):
        click.echo(" ")
    args = argparse.Namespace()
    args.type = type
    args.file = file
    args.entrypoint = entrypoint
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
    help=f"""Set the log level. _{nomad.ui.GRAY}[default: info]{nomad.ui.RESET}_""",
    required=False
)
@click.option(
    '--whitelist-all',
    is_flag=True,
    default=False,
    help=f"""Whitelist all IP addresses. If `False`, then only whitelist your current IP address. _{nomad.ui.GRAY}[default: False]{nomad.ui.RESET}_""",  # noqa
    required=False,
)
def apply(file: str, name: str, log_level: str, whitelist_all: bool):
    """Build your agent using a configuration YAML.

    <br>Examples:
    - nomad apply -f ./ec2.yml
    - nomad apply -f ./ec2.yml --whitelist-all
    """
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
    help=f"""Set the log level. _{nomad.ui.GRAY}[default: info]{nomad.ui.RESET}_""",
    required=False
)
@click.option(
    '--no-delete-failure',
    is_flag=True,
    default=False,
    help=f"""Preserve the cloud resources after a failed run. _{nomad.ui.GRAY}[default: False]{nomad.ui.RESET}_""",  # noqa
    required=False
)
@click.option(
    '--no-delete-success',
    is_flag=True,
    default=False,
    help=f"""Preserve the cloud resources after a successful run. _{nomad.ui.GRAY}[default: False]{nomad.ui.RESET}_""",  # noqa
    required=False
)
@click.option(
    '--whitelist-all',
    is_flag=True,
    default=False,
    help=f"""Whitelist all IP addresses. If `False`, then only whitelist your current IP address. _{nomad.ui.GRAY}[default: False]{nomad.ui.RESET}_""",  # noqa
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
    """Run your project using an agent.

    <br>Examples:
    - nomad run -f ./ec2.yml --no-delete-failure
    - nomad run -f ./ec2.yml --no-delete-success --whitelist-all
    """
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
    help=f"""Set the log level. _{nomad.ui.GRAY}[default: info]{nomad.ui.RESET}_""",
    required=False
)
@click.option(
    '--no-delete-failure',
    is_flag=True,
    default=False,
    help=f"""Preserve the cloud resources after a failed build. _{nomad.ui.GRAY}[default: False]{nomad.ui.RESET}_""",  # noqa
)
@click.option(
    '--no-delete-success',
    is_flag=True,
    default=False,
    help=f"""Preserve the cloud resources after a successful build. _{nomad.ui.GRAY}[default: False]{nomad.ui.RESET}_""",  # noqa
    required=False
)
@click.option(
    '--whitelist-all',
    is_flag=True,
    default=False,
    help=f"""Whitelist all IP addresses. If `False`, then only whitelist your current IP address. _{nomad.ui.GRAY}[default: False]{nomad.ui.RESET}_""",  # noqa
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
    """Build your agent using a configuration YAML and then run your project on the
    newly created agent.

    <br>Examples:
    - nomad build -f ./ec2.yml --no-delete-failure
    - nomad build -f ./ec2.yml --no-delete-success --whitelist-all
    """
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
    help=f"""Set the log level. _{nomad.ui.GRAY}[default: info]{nomad.ui.RESET}_""",
    required=False
)
def delete(file: str, name: str, log_level: str):
    """Delete your agent.

    <br>Examples:
    - nomad delete -f ./ec2.yml
    """
    args = argparse.Namespace()
    args.file = file
    args.name = name
    args.wkdir = Path(os.path.abspath(file)).parent
    args.log_level = log_level

    # Delete task
    task = delete_task.DeleteTask(args)
    return task.run()
