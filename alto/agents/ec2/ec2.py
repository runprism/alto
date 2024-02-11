"""
EC2 agent
"""

###########
# Imports #
###########

# Alto imports
from alto.agents.base import Agent
from alto.agents.ec2.protocols import (  # noqa
    Protocol,
    SSHProtocol,
    SSMProtocol,
)
from alto.constants import (
    INTERNAL_FOLDER,
    DEFAULT_LOGGER_NAME,
)
from alto.mixins.aws_mixins import (
    ec2File,
    ec2Resource,
    State,
)
import alto.ui
from alto.entrypoints import BaseEntrypoint
from alto.infras import BaseInfra
from alto.images import BaseImage
from alto.images.docker_image import Docker
from alto.mixins.aws_mixins import (
    AwsMixin
)
from alto.output import (
    OutputManager,
    Symbol,
)
from alto.ui import StageEnum

# Standard library imports
import argparse
import boto3
import botocore
from enum import Enum
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import urllib.request

# Type hints
from mypy_boto3_ec2.client import EC2Client
from mypy_boto3_ec2.service_resource import EC2ServiceResource


##########
# Logger #
##########

import logging
logger = logging.getLogger(DEFAULT_LOGGER_NAME)


####################
# Class definition #
####################

class IpAddressType(str, Enum):
    V4 = "ipv4"
    V6 = "ipv6"


class Ec2(Agent, AwsMixin):
    instance_name: str
    ec2_client: EC2Client
    ec2_resource: EC2ServiceResource

    # EC2 protocol
    protocol: Protocol

    # All possible EC2 resources
    key_pair: str
    security_group_id: str
    instance_id: str
    public_dns_name: str
    state: State
    iam_role_arn: str

    # All possible EC2 files
    pem_key_path: Path

    def __init__(self,
        args: argparse.Namespace,
        alto_wkdir: Path,
        agent_name: str,
        agent_conf: Dict[str, Any],
        infra: BaseInfra,
        entrypoint: BaseEntrypoint,
        image: Optional[BaseImage],
        output_mgr: OutputManager,
        mode: str = "prod"
    ):
        Agent.__init__(
            self, args, alto_wkdir, agent_name, agent_conf, infra, entrypoint, image, output_mgr, mode  # noqa
        )

        # Create the Protocol
        user_protocol = self.infra.infra_conf["protocol"]
        if user_protocol == "ssh":
            self.protocol = SSHProtocol(
                self.args,
                self.infra.infra_conf,
                agent_conf,
                self.output_mgr
            )

            # Set the scripts
            scripts_dir = f"{os.path.dirname(__file__)}/scripts"
            self.protocol.apply_script = f"{scripts_dir}/ec2/apply.sh"
            self.protocol.run_script = f"{scripts_dir}/ec2/run.sh"

            # Use slightly different scripts if the user wants to run a Docker image on
            # their EC2 instance.
            if image is not None and isinstance(image, Docker):
                self.protocol.apply_script = f"{scripts_dir}/docker/ec2/apply.sh"
                self.protocol.run_script = f"{scripts_dir}/docker/ec2/run.sh"

        elif user_protocol == "ssm":
            self.protocol = SSMProtocol(
                self.args,
                self.infra.infra_conf,
                agent_conf,
                self.output_mgr
            )

        # Create the client
        self.aws_cli()
        self.ec2_client = boto3.client('ec2')
        self.ec2_resource = boto3.resource('ec2')

        # Instance name
        alto_project_name = self.alto_wkdir.name.replace("_", "-")
        self.instance_name = f"{alto_project_name}-{self.agent_name}"

        # Create an empty `ec2.json` file if it doesn't exist
        empty_data: Dict[str, Dict[str, Any]] = {
            self.instance_name: {
                "resources": {},
                "files": {}
            }
        }
        if not Path(INTERNAL_FOLDER / 'ec2.json').is_file():
            with open(Path(INTERNAL_FOLDER / 'ec2.json'), 'w') as f:
                json.dump(empty_data, f)
                data = empty_data

        # If it does, then check if `instance_name` is contained in the JSON. If it
        # isn't, then add it in.
        else:
            with open(Path(INTERNAL_FOLDER / 'ec2.json'), 'r') as f:
                data = json.loads(f.read())
            f.close()
            if self.instance_name not in data.keys():
                data.update(empty_data)
                self.write_json(data)

    def aws_cli(self) -> int:
        """
        Confirms that the user has AWS credentials and can use the boto3 API
        args:
            None
        returns:
            0 if user has configured AWS CLI
        raises:
            pipe.exceptions.RuntimeException() if user has not configured AWS CLI
        """
        s3 = boto3.resource('s3')
        try:
            s3.buckets.all()
            return 0
        except botocore.exceptions.NoCredentialsError:
            msg_list = [
                "AWS credentials not found. Consult Boto3 documentation:",
                "https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html"    # noqa: E501
            ]
            raise ValueError('\n'.join(msg_list))

    def write_json(self, data: Dict[str, Dict[str, Any]]):
        """
        Write `data` to ~/.alto/ec2.json

        args:
            data: data to write to JSON
        """
        with open(Path(INTERNAL_FOLDER) / 'ec2.json', 'w') as f:
            json.dump(data, f)

    def update_json(self, data: Dict[str, Dict[str, Any]]):
        """
        Update ~/.alto/ec2.json

        args:
            ...
        """
        json_path = Path(INTERNAL_FOLDER) / 'ec2.json'
        if not json_path.is_file():
            self.write_json({self.instance_name: data})
            return data
        else:
            with open(json_path, 'r') as f:
                json_data = json.loads(f.read())
            f.close()

            # If the instance name isn't in the JSON, then add it in
            if self.instance_name not in json_data.keys():
                json_data.update({self.instance_name: data})

            # Update the data
            else:
                for key in ["resources", "files"]:
                    if key in list(data.keys()):
                        json_data[self.instance_name][key].update(data[key])

            # Write the json
            self.write_json(json_data)
            return json_data[self.instance_name]

    def delete_resources_in_json(self) -> Dict[str, str]:
        """
        Delete all resources found in the JSON
        """
        del_resources: Dict[str, str] = {}

        # If the path doesn't exist, then return an empty dictionary
        json_path = Path(INTERNAL_FOLDER) / 'ec2.json'
        if not json_path.is_file():
            return del_resources

        # Otherwise, iterate through the dictionary and delete the resources
        else:
            with open(json_path, 'r') as f:
                json_data = json.loads(f.read())
            f.close()
            json_data = json_data[self.instance_name]
            resources = json_data.get("resources", {})
            files = json_data.get("files", {})

            # Key name
            if ec2Resource.KEY_PAIR.value in resources.keys():
                self.output_mgr.step_starting("Deleting key pair...")

                self.delete_key_pair_and_unlink_path(
                    self.ec2_client,
                    resources[ec2Resource.KEY_PAIR.value],
                    Path(files["pem_key_path"]),
                )
                del_resources[ec2Resource.KEY_PAIR.value] = resources[ec2Resource.KEY_PAIR.value]  # noqa

                self.output_mgr.step_completed(
                    "Deleted key pair!",
                    symbol=Symbol.DELETED
                )

            # Role
            iam_client = boto3.client("iam")
            iam_role_name = f"{self.instance_name}-role"
            if ec2Resource.ROLE_ARN.value in resources.keys():
                self.output_mgr.step_starting("Deleting IAM role...")

                self.detach_and_delete_iam_role(iam_client, iam_role_name)
                del_resources[ec2Resource.ROLE_ARN.value] = resources[ec2Resource.ROLE_ARN.value]  # noqa

                self.output_mgr.step_completed(
                    "Deleted IAM role!",
                    symbol=Symbol.DELETED
                )

            # IAM instance profile
            iam_instance_profile_name = f"{self.instance_name}-profile"
            if ec2Resource.INSTANCE_PROFILE_ARN.value in resources.keys():
                self.output_mgr.step_starting("Deleting IAM instance profile...")

                iam_client.delete_instance_profile(
                    InstanceProfileName=iam_instance_profile_name
                )
                del_resources[ec2Resource.INSTANCE_PROFILE_ARN.value] = resources[ec2Resource.INSTANCE_PROFILE_ARN.value]  # noqa

                self.output_mgr.step_completed(
                    "Deleted IAM instance profile!",
                    symbol=Symbol.DELETED
                )

            # Instance
            if ec2Resource.INSTANCE_ID.value in resources.keys():
                self.output_mgr.step_starting("Deleting EC2 instance...")

                self.ec2_client.terminate_instances(
                    InstanceIds=[resources[ec2Resource.INSTANCE_ID.value]]
                )
                del_resources[ec2Resource.INSTANCE_ID.value] = resources[ec2Resource.INSTANCE_ID.value]  # noqa

                self.output_mgr.step_completed(
                    "Deleted EC2 instance!",
                    symbol=Symbol.DELETED
                )

            # Security group
            if ec2Resource.SECURITY_GROUP_ID.value in resources.keys():
                self.output_mgr.step_starting("Deleting security group...")

                self.resolve_dependency_violation_and_delete_security_group(
                    self.ec2_client, resources[ec2Resource.SECURITY_GROUP_ID.value]
                )
                del_resources[ec2Resource.SECURITY_GROUP_ID.value] = resources[ec2Resource.SECURITY_GROUP_ID.value]  # noqa

                self.output_mgr.step_completed(
                    "Deleted security group!",
                    symbol=Symbol.DELETED
                )

        os.unlink(json_path)
        return del_resources

    def check_ip_address_type(self,
        external_ip: str
    ) -> IpAddressType:
        """
        Determine whether `external_ip` is an IPv4 or IPv6 address

        args:
            external_ip: external IP address
        returns:
            IpAddressType
        """
        flag_is_ipv4 = re.findall(
            r'(^(?:\d{1,3}\.){3}\d{1,3}$)',
            external_ip
        )
        flag_is_ipv6 = re.findall(
            r'^((?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4})$',
            external_ip
        )

        # IP address must be IPv4 or IPv6, but not both
        if flag_is_ipv4 and flag_is_ipv6:
            raise ValueError(
                f"Unrecognized IP address type `{external_ip}`"
            )
        if not (flag_is_ipv4 or flag_is_ipv6):
            raise ValueError(
                f"Unrecognized IP address type `{external_ip}`"
            )

        # Return
        if flag_is_ipv4:
            return IpAddressType('ipv4')
        else:
            return IpAddressType('ipv6')

    def add_ingress_rule(self,
        ec2_client: Any,
        security_group_id: str,
        external_ip: str,
    ) -> Optional[str]:
        """
        Add an ingress rule that allows SSH traffic from `external_ip`

        args:
            ec2_client: Boto3 EC2 client
            security_group_id: security group ID
            external_ip: external IP address from which to allow traffic
        returns:
            None
        """
        ip_address_type = self.check_ip_address_type(external_ip)

        # Add rule
        if ip_address_type == IpAddressType('ipv4'):
            if not self.args.whitelist_all:
                ip_ranges = {'CidrIp': f'{external_ip}/32'}
            else:
                external_ip = "0.0.0.0"
                ip_ranges = {'CidrIp': '0.0.0.0/0'}
            ip_permissions = [
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [ip_ranges]
                },
            ]

        # We've had problems in the past with SSHing into an EC2 instance from IPv6
        # addresses. Therefore, just default to allowing SSH connections from any IP.
        else:
            ip_permissions = [
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'Ipv6Ranges': [{'CidrIpv6': '::/0'}]
                },
            ]

        try:
            _ = ec2_client.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=ip_permissions
            )
            return external_ip

        # If the rule already exists, then we're all gucci
        except botocore.exceptions.ClientError as e:
            if "the specified rule" in str(e) and "already exists" in str(e):
                return None
            raise e

    def check_ingress_ip(self,
        ec2_client: Any,
        security_group_id: str,
    ) -> Optional[str]:
        """
        Confirm that the ingress rule for `security_group_id` allows for SSH traffic
        from the user's IP address.

        args:
            ec2_client: boto3 EC2 client
            security_group_id: security group ID
        returns:
            None if the current IP address is already in the security groups ingress
            rules; otherwise the IP address that was added
        """
        # Get security group
        security_groups = ec2_client.describe_security_groups()["SecurityGroups"]
        curr_sg = None
        for sg in security_groups:
            if sg["GroupId"] == security_group_id:
                curr_sg = sg
        if curr_sg is None:
            raise ValueError(
                f"could not find security group with ID `{security_group_id}`"
            )

        # Get current IP address
        external_ip = urllib.request.urlopen('https://ident.me').read().decode('utf8')
        external_ip_type = self.check_ip_address_type(external_ip)

        # Check if IP is in ingress rules
        ip_allowed = False
        for ingress_permissions in curr_sg["IpPermissions"]:

            # Look at SSH protocols only
            if (
                ingress_permissions["FromPort"] == 22
                and ingress_permissions["IpProtocol"] == "tcp"  # noqa: W503
                and ingress_permissions["ToPort"] == 22  # noqa: W503
            ):
                # Check if SSH traffic from the current IP address is allowed
                if external_ip_type == IpAddressType('ipv4'):
                    ip_search = "0.0.0.0/0" if self.args.whitelist_all else f"{external_ip}/32"  # noqa: E501
                    ip_ranges = ingress_permissions["IpRanges"]
                    for ipr in ip_ranges:
                        if ip_search in ipr["CidrIp"]:
                            ip_allowed = True
                else:
                    ip_search = "::/0"
                    ip_ranges = ingress_permissions["Ipv6Ranges"]
                    for ipr in ip_ranges:
                        if ip_search in ipr["CidrIpv6"]:
                            ip_allowed = True

        # If SSH traffic from the current IP address it not allowed, then authorize it.
        if not ip_allowed:
            return self.add_ingress_rule(
                ec2_client,
                security_group_id,
                external_ip,
            )
        return None

    def get_all_local_mounts(self,
        alto_wkdir: Path,
        agent_conf: Dict[str, Any],
    ) -> List[str]:
        """
        Prior to running our code on the EC2 instance, we first copy our code onto the
        instance using SSH / SCP protocols. Specifically, we copy the current working
        directory and `additional_paths`.

        args:
            alto_wkdir: user's working directory
            agent_conf: agent configuration
        returns:
            list of project paths
        """
        # Additional paths
        additional_paths = []
        if "additional_paths" in agent_conf.keys():
            additional_paths = [
                str(_p) for _p in agent_conf["additional_paths"]
            ]

        # Return all paths
        return [str(alto_wkdir)] + additional_paths

    def apply(self, overrides={}):
        """
        Create the EC2 instance image
        """
        # Build the image, if necessary
        if self.image is not None:
            self.image.build(
                self.agent_conf,
                self.entrypoint,
                jinja_template_overrides={},
                build_kwargs={"platform": "linux/amd64"},
            )

        # Infra
        instance_type = self.parse_infra_key(self.infra.infra_conf, "instance_type")
        ami_image = self.parse_infra_key(self.infra.infra_conf, "ami_image")

        # Grab the current resources
        ec2_json_path = Path(INTERNAL_FOLDER / 'ec2.json')
        with open(ec2_json_path, 'r') as f:
            data = json.loads(f.read())
        current_data = data[self.instance_name]

        # Create resources. Wrap in a try-except block so that we can catch errors.
        self.output_mgr.step_starting("[dodger_blue2]Building resources...[/dodger_blue2]")  # noqa
        try:
            new_data = self.protocol.create_resources(
                current_data=current_data,
                ec2_client=self.ec2_client,
                instance_name=self.instance_name,
                instance_type=instance_type,
                ami_image=ami_image,
            )
            self.update_json(new_data)
            self.output_mgr.step_completed("Built resources!", is_substep=False)

        # If we fail at creating resources, then delete the resources that were created
        except Exception as e:
            self.output_mgr.step_failed()
            self.update_json(self.protocol.resource_data)
            self.delete_resources_in_json()
            raise e

        # If the user is using an image, then ignore the Python version
        python_version = self.parse_infra_key(self.infra.infra_conf, "python_version")
        if self.image is not None:
            if python_version != "":
                self.output_mgr.log_output(
                    agent_img_name=self.instance_name,
                    stage=StageEnum.AGENT_BUILD,
                    level="info",
                    msg="Ignoring Python version in favor of newly built image"
                )
                python_version = ""

        # requirements.txt path
        requirements_txt_path = Path(
            self.parse_requirements(self.alto_wkdir, self.agent_conf)
        )
        if str(requirements_txt_path) == ".":
            requirements_txt_str = ""
        else:
            requirements_txt_str = str(requirements_txt_path)

        # Post-build commands
        post_build_commands = self.infra.infra_conf["post_build_cmds"]

        # Environment dictionary
        env_dict = self.parse_environment_variables(self.agent_conf)

        # Paths to copy
        all_local_mounts = self.get_all_local_mounts(
            self.alto_wkdir,
            self.agent_conf,
        )

        # The `create_instance` command is blocking — it won't finish until the instance
        # is up and running.
        self.output_mgr.step_starting("[dodger_blue2]Building agent...[/dodger_blue2]")  # noqa
        try:
            returncode = self.protocol.setup_instance(
                current_data=new_data,
                ec2_client=self.ec2_client,
                image=self.image,
                instance_name=self.instance_name,
                ec2_user="ec2-user",
                requirements_txt_str=requirements_txt_str,
                local_mounts=all_local_mounts,
                env_vars=env_dict,
                python_version=python_version,
                post_build_commands=post_build_commands,

            )
            if returncode != 0:
                self.output_mgr.step_failed()
                self.delete_resources_in_json()
            else:
                self.output_mgr.step_completed("Built agent!", is_substep=False)
                self.output_mgr.stop_live()
            return returncode

        # If we encounter any sort of error, update the JSON and delete the resouces
        except Exception as e:
            self.output_mgr.step_failed()
            self.delete_resources_in_json()
            raise e

    def run(self, overrides={}):
        """
        Run the project using the EC2 agent
        """
        # Grab the current resources
        ec2_json_path = Path(INTERNAL_FOLDER / 'ec2.json')
        with open(ec2_json_path, 'r') as f:
            data = json.loads(f.read())
        current_data = data[self.instance_name]

        # Download files
        download_files = self.agent_conf["download_files"]
        download_files_cmd: List[str] = []
        for df in download_files:
            download_files_cmd.append(df)

        # Return code
        self.output_mgr.step_starting("[dodger_blue2]Running entrypoint...[/dodger_blue2]")  # noqa
        try:
            returncode = self.protocol.run_entrypoint_on_instance(
                current_data=current_data,
                ec2_client=self.ec2_client,
                alto_wkdir=self.alto_wkdir,
                image=self.image,
                instance_name=self.instance_name,
                entrypoint=self.entrypoint,
                download_files=download_files_cmd,
            )
            if returncode != 0:
                self.output_mgr.step_failed()
            else:
                self.output_mgr.step_completed("Entrypoint completed!")
            return returncode

        # If there is any exception, return 1.
        except Exception:
            self.output_mgr.step_failed()
            raise

    def delete(self, overrides={}):
        """
        Delete all resources associated with agent. This includes:
            - Key pair
            - Security group
            - Instance

        In addition, remove the PEM key from our local files
        """
        # Delete the image, if it exists
        if self.image is not None:
            self.image.delete()

        # Logging styling
        self.output_mgr.step_starting("[dodger_blue2]Deleting resources...[/dodger_blue2]")  # noqa

        # Grab the current resources
        ec2_json_path = Path(INTERNAL_FOLDER / 'ec2.json')
        with open(ec2_json_path, 'r') as f:
            data = json.loads(f.read())
        current_data = data[self.instance_name]
        current_resources = current_data.get("resources", {})
        current_files = current_data.get("files", {})

        # Key pair
        key_pair_attr = current_resources.get(ec2Resource.KEY_PAIR.value, None)
        if key_pair_attr is None:
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_DELETE,
                level="info",
                msg="Key pair not found! If this is a mistake, then you may need to reset your resource data"  # noqa: E501
            )
        else:
            pem_key_path_attr = current_files[ec2File.PEM_KEY_PATH.value]
            self.output_mgr.step_starting(
                "Deleting key-pair...",
                is_substep=True
            )
            self.delete_key_pair_and_unlink_path(
                self.ec2_client, key_name=key_pair_attr, pem_key_path=pem_key_path_attr
            )
            log_key_pair = f"{alto.ui.MAGENTA}{key_pair_attr}{alto.ui.RESET}"
            log_key_path = f"{alto.ui.MAGENTA}{str(pem_key_path_attr)}{alto.ui.RESET}"  # noqa: E501
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_DELETE,
                level="info",
                msg=f"Deleting key-pair {log_key_pair} at {log_key_path}",
                renderable_type="Deleted key pair",
                is_step_completion=True,
                is_substep=True,
                symbol=Symbol.DELETED,
            )

        # Role
        iam_client = boto3.client("iam")
        role_arn_attr = current_resources.get(
            ec2Resource.ROLE_ARN.value, None
        )
        if role_arn_attr is None:
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_DELETE,
                level="info",
                msg="IAM role not found! If this is a mistake, then you may need to reset your resource data"  # noqa: E501
            )
        else:
            self.output_mgr.step_starting(
                "Deleting IAM role...",
                is_substep=True
            )
            self.detach_and_delete_iam_role(
                iam_client, iam_role_name=f"{self.instance_name}-role"
            )

            log_role_arn = f"{alto.ui.MAGENTA}{role_arn_attr}{alto.ui.RESET}"  # noqa: E501
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_DELETE,
                level="info",
                msg=f"Deleting IAM role {log_role_arn}",
                renderable_type="Deleted IAM role",
                is_step_completion=True,
                is_substep=True,
                symbol=Symbol.DELETED,
            )

        # IAM instance profile
        instance_profile_arn_attr = current_resources.get(
            ec2Resource.INSTANCE_PROFILE_ARN.value, None
        )
        if instance_profile_arn_attr is None:
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_DELETE,
                level="info",
                msg="IAM instance profile not found! If this is a mistake, then you may need to reset your resource data"  # noqa: E501
            )

        else:
            self.output_mgr.step_starting(
                "Deleting IAM instance profile...",
                is_substep=True
            )
            iam_client.delete_instance_profile(InstanceProfileName=f"{self.instance_name}-profile")  # noqa: E501
            log_instance_profile = f"{alto.ui.MAGENTA}{instance_profile_arn_attr}{alto.ui.RESET}"  # noqa: E501
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_DELETE,
                level="info",
                msg=f"Deleting IAM instance profile {log_instance_profile}",
                renderable_type="Deleted IAM instance profile",
                is_step_completion=True,
                is_substep=True,
                symbol=Symbol.DELETED,
            )

        # Instance
        instance_id_attr = current_resources.get(ec2Resource.INSTANCE_ID.value, None)
        if instance_id_attr is None:
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_DELETE,
                level="info",
                msg="Instance not found! If this is a mistake, then you may need to reset your resource data"  # noqa: E501
            )

        else:
            self.output_mgr.step_starting(
                "Deleting instance...",
                is_substep=True
            )
            log_instance_id = f"{alto.ui.MAGENTA}{instance_id_attr}{alto.ui.RESET}"  # noqa: E501
            self.ec2_client.terminate_instances(
                InstanceIds=[instance_id_attr]
            )
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_DELETE,
                level="info",
                msg=f"Deleting instance {log_instance_id}",
                renderable_type="Deleted instance",
                is_step_completion=True,
                is_substep=True,
                symbol=Symbol.DELETED,
            )

        # Security group
        security_group_id_attr = current_resources.get(
            ec2Resource.SECURITY_GROUP_ID.value, None
        )
        if security_group_id_attr is None:
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_DELETE,
                level="info",
                msg="Security group not found! If this is a mistake, then you may need to reset your resource data"  # noqa: E501
            )

        else:
            self.output_mgr.step_starting(
                "Deleting security group...",
                is_substep=True
            )
            self.resolve_dependency_violation_and_delete_security_group(
                self.ec2_client, security_group_id_attr
            )
            log_security_group_id = f"{alto.ui.MAGENTA}{security_group_id_attr}{alto.ui.RESET}"  # noqa: E501
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_DELETE,
                level="info",
                msg=f"Deleting security group {log_security_group_id}",
                renderable_type="Deleted security group",
                is_step_completion=True,
                is_substep=True,
                symbol=Symbol.DELETED,
            )

        self.output_mgr.step_completed("Deleted resources!")
        self.output_mgr.stop_live()

        # Remove the data from the ec2.json file
        if Path(INTERNAL_FOLDER / 'ec2.json').is_file():
            with open(Path(INTERNAL_FOLDER / 'ec2.json'), 'r') as f:
                json_data = json.loads(f.read())
            if self.instance_name in json_data.keys():
                del json_data[self.instance_name]

            # Write the data out again
            self.write_json(json_data)

        # Return
        return 0
