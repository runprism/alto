"""
Base protocol, inherited by the SSHProtocol and SSMProtocol classes.
"""

# Imports
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

# Alto imports
from alto.constants import EC2_INSTANCE_TYPE
from alto.entrypoints import BaseEntrypoint
from alto.images import BaseImage
from alto.mixins.aws_mixins import (
    AwsMixin,
)
from alto.output import (
    OutputManager,
)

# Type hints
from mypy_boto3_ec2.client import EC2Client


# Classes
class Protocol(AwsMixin):
    args: argparse.Namespace
    infra_conf: Dict[str, Any]
    output_mgr: OutputManager
    resource_data: Dict[str, Any] = {}
    apply_script: str
    run_script: str

    def __init__(
        self,
        args: argparse.Namespace,
        infra_conf: Dict[str, Any],
        agent_conf: Dict[str, Any],
        output_mgr: OutputManager
    ):
        self.args = args
        self.infra_conf = infra_conf
        self.agent_conf = agent_conf
        self.output_mgr = output_mgr

    def create_resources(self,
        current_data: Dict[str, Any],
        ec2_client: EC2Client,
        instance_name: str,
        instance_type: EC2_INSTANCE_TYPE,
        ami_image: str,
    ):
        raise NotImplementedError

    def setup_instance(self,
        current_data: Dict[str, Any],
        ec2_client: EC2Client,
        image: Optional[BaseImage],
        instance_name: str,
        ec2_user: str,
        requirements_txt_str: str,
        local_mounts: List[str],
        env_vars: Dict[str, str],
        python_version: str,
        post_build_commands: List[str],
    ) -> int:
        raise NotImplementedError

    def run_entrypoint_on_instance(self,
        current_data: Dict[str, Any],
        ec2_client: EC2Client,
        alto_wkdir: Path,
        image: Optional[BaseImage],
        instance_name: str,
        entrypoint: BaseEntrypoint,
        download_files: List[str],
    ):
        raise NotImplementedError
