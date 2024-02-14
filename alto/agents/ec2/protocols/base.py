"""
Base protocol, inherited by the SSHProtocol and SSMProtocol classes.
"""

# Imports
import argparse
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

# Alto imports
from alto.constants import EC2_INSTANCE_TYPE
from alto.entrypoints import BaseEntrypoint
from alto.images import BaseImage
from alto.images.docker_image import Docker
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
        artifacts: List[Path],
    ):
        raise NotImplementedError

    def get_workdir_and_artifacts_relative_dir(self,
        image: Optional[BaseImage],
        alto_wkdir: Path,
        artifacts: List[Path]
    ) -> Tuple[str, List[str]]:
        workdir: Optional[str] = None
        artifacts_relative_paths: List[str] = []

        if image is not None and isinstance(image, Docker):
            # First, define the WORKDIR used by the Docker image
            context_path = alto_wkdir / '.docker_context' if image.context == "" else Path(image.context)  # noqa: E501
            with open(Path(context_path) / 'Dockerfile', 'r') as f:
                context_path_lines = f.readlines()
            for line in context_path_lines:
                matches = re.findall(r'^WORKDIR (.+)$', line)
                if len(matches) > 0:
                    workdir = matches[0]
                    assert isinstance(workdir, str)

                    # Remove trailing forward slash, if it exists
                    if workdir[-1] == "/":
                        workdir = workdir[:-1]

            # Next, define the artifact paths relative to the WORKDIR path
            for _df in artifacts:
                if workdir is None:
                    raise ValueError("Trying to download artifacts, but no working directory specified in image definition!")  # noqa: E501

                # Path of download file relative to working directory
                _df_rel = os.path.relpath(_df, alto_wkdir)
                artifacts_relative_paths.append(_df_rel)
        else:
            workdir = str(alto_wkdir)
            artifacts_relative_paths = [str(x) for x in artifacts]

        assert isinstance(workdir, str)
        return workdir, artifacts_relative_paths
