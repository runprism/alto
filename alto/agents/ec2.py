"""
Docker Agent.
"""


###########
# Imports #
###########

# Alto imports
from alto.agents.base import Agent
from alto.agents.protocols import (
    Protocol,
    SSHProtocol,
    SSMProtocol,
)
from alto.constants import (
    INTERNAL_FOLDER,
    DEFAULT_LOGGER_NAME
)
from alto.mixins.aws_mixins import (
    sshFile,
    sshResource,
    State,
)
import alto.ui
from alto.entrypoints import BaseEntrypoint
from alto.infras import BaseInfra
from alto.command import AgentCommand
from alto.images import BaseImage
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
import time
from typing import Any, Dict, List, Optional
import subprocess
import urllib.request


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


class Ec2(Agent):
    # These MUST include all SSH and SSM resources, see the AWS mixins
    key_pair: Optional[str]
    security_group_id: Optional[str]
    instance_id: Optional[str]
    public_dns_name: Optional[str]
    state: Optional[State]

    pem_key_path: Optional[Path]

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

        # Bash dir
        scripts_dir = f"{os.path.dirname(__file__)}/scripts"
        self.AGENT_APPLY_SCRIPT = f"{scripts_dir}/ec2/apply.sh"
        self.AGENT_RUN_SCRIPT = f"{scripts_dir}/ec2/run.sh"

        # Use slightly different scripts if the user wants to run a Docker image on
        # their EC2 instance.
        if image is not None and image.image_conf["type"] == "docker":
            self.AGENT_APPLY_SCRIPT = f"{scripts_dir}/docker/ec2/apply.sh"
            self.AGENT_RUN_SCRIPT = f"{scripts_dir}/docker/ec2/run.sh"

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

        # Set resource / file attributes
        data = data[self.instance_name]
        for x in sshResource:
            if x.value in data["resources"].keys():
                self.__setattr__(x.value, data["resources"][x.value])
            else:
                self.__setattr__(x.value, None)
        for y in sshFile:
            if y.value in data["files"].keys():
                self.__setattr__(y.value, Path(data["files"][y.value]))
            else:
                self.__setattr__(y.value, None)

    def set_scripts_paths(self,
        apply_script: Optional[Path] = None,
        run_script: Optional[Path] = None,
    ) -> None:
        if apply_script is not None:
            self.AGENT_APPLY_SCRIPT = str(apply_script)
        if run_script is not None:
            self.AGENT_RUN_SCRIPT = str(run_script)

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
            if sshResource.KEY_PAIR.value in resources.keys():
                self.output_mgr.step_starting("Deleting key pair...")
                pem_key_path = files["pem_key_path"]
                self.ec2_client.delete_key_pair(
                    KeyName=resources[sshResource.KEY_PAIR.value]
                )
                os.unlink(str(pem_key_path))
                del_resources[sshResource.KEY_PAIR.value] = resources[sshResource.KEY_PAIR.value]  # noqa
                self.output_mgr.step_completed(
                    "Deleted key pair!",
                    symbol=Symbol.DELETED
                )

            # Instance
            if sshResource.INSTANCE_ID.value in resources.keys():
                self.output_mgr.step_starting("Deleting EC2 instance...")
                self.ec2_client.terminate_instances(
                    InstanceIds=[resources[sshResource.INSTANCE_ID.value]]
                )
                del_resources[sshResource.INSTANCE_ID.value] = resources[sshResource.INSTANCE_ID.value]  # noqa
                self.output_mgr.step_completed(
                    "Deleted EC2 instance!",
                    symbol=Symbol.DELETED
                )

            # Security group
            if sshResource.SECURITY_GROUP_ID.value in resources.keys():
                self.output_mgr.step_starting("Deleting security group...")
                while True:
                    try:
                        self.ec2_client.delete_security_group(
                            GroupId=resources[sshResource.SECURITY_GROUP_ID.value]
                        )
                        break
                    except botocore.exceptions.ClientError as e:
                        if "DependencyViolation" in str(e):
                            time.sleep(5)
                        else:
                            raise e

                del_resources[sshResource.SECURITY_GROUP_ID.value] = resources[sshResource.SECURITY_GROUP_ID.value]  # noqa
                self.output_mgr.step_completed(
                    "Deleted security group!",
                    symbol=Symbol.DELETED
                )

        os.unlink(json_path)
        return del_resources

    def check_resources(self,
        ec2_client: Any,
        instance_name: str,
        instance_id: Optional[str]
    ):
        """
        In order for our agent to work properly, we need three resources:
            - A key-pair
            - A security group
            - An EC2 instance

        All three of these resources should share the same name: `instance_name`. Note
        that multiple EC2 instances can share the same name. That's why we also need
        `instance_id`.

        args:
            ec2_client: Boto3 EC2 client
            instance_name: name of resources
            instance_id: EC2 instance ID
        returns:
            dictionary of resources
        """
        resources: Dict[str, Optional[Dict[str, str]]] = {}

        # Key pair
        resources[sshResource.KEY_PAIR.value] = None
        keypairs = ec2_client.describe_key_pairs()
        for kp in keypairs["KeyPairs"]:
            if kp["KeyName"] == instance_name:
                resources[sshResource.KEY_PAIR.value] = kp

        # Security groups
        resources[sshResource.SECURITY_GROUP_ID.value] = None
        security_groups = ec2_client.describe_security_groups()
        for sg in security_groups["SecurityGroups"]:
            if sg["GroupName"] == instance_name:
                resources[sshResource.SECURITY_GROUP_ID.value] = sg

        # Instance
        resources[sshResource.INSTANCE_ID.value] = None
        response = ec2_client.describe_instances()
        reservations = response["Reservations"]
        if len(reservations) > 0 and instance_id is not None:
            for res in reservations:
                instances = res["Instances"]
                for inst in instances:
                    if inst["InstanceId"] == instance_id:

                        # Check if key-name and security group for instance matches
                        flag_instance_sg_match = False
                        flag_instance_kp_match = False
                        for sg in inst["SecurityGroups"]:
                            if sg["GroupName"] == instance_name:
                                flag_instance_sg_match = True
                        if inst["KeyName"] == instance_name:
                            flag_instance_kp_match = True

                        # Raise appropriate errors
                        if not flag_instance_sg_match:
                            raise ValueError(
                                f"instance {instance_id} does not have security group `{instance_name}`"  # noqa: E501
                            )

                        if not flag_instance_kp_match:
                            raise ValueError(
                                f"instance {instance_id} does not have key pair `{instance_name}`"  # noqa: E501
                            )

                        # Otherwise, set to True. mypy doesn't recognize that
                        # `instance_id` is non-null if we reach this point in the code.
                        resources[sshResource.INSTANCE_ID.value] = instance_id  # type: ignore # noqa

        # Return the resources
        return resources

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

    def create_instance(self,
        ec2_client: Any,
        ec2_resource: Any,
        instance_id: Optional[str],
        instance_name: str,
        instance_type: str,
        ami_image: str,
    ):
        """
        Create EC2 instance

        args:
            ec2_client: Boto3 AWS EC2 client
            ec2_resource: Boto3 AWS EC2 resource
            instance_id: EC2 instance ID
            instance_name: name of EC2 instance
            instance_type: EC2 instance types
        returns:
            EC2 response
        """
        protocol: Protocol
        if self.infra.infra_conf["protocol"] == "ssh":
            protocol = SSHProtocol(
                self.args,
                self.infra.infra_conf,
                self.output_mgr,
            )
        else:
            protocol = SSMProtocol(  # type: ignore
                self.args,
                self.infra.infra_conf,
                self.output_mgr,
            )

        # Wrap the whole thing in a single try-except block
        try:
            # Our `ec2.json` file should always exist, because it's created upon the
            # agent's instantiation.
            ec2_json_path = Path(INTERNAL_FOLDER / 'ec2.json')
            with open(ec2_json_path, 'r') as f:
                data = json.loads(f.read())
            f.close()
            current_data = data[instance_name]

            # Create the instance using the appropriate protocol
            new_data = protocol.create_instance(
                current_data=current_data,
                ec2_client=ec2_client,
                ec2_resource=ec2_resource,
                instance_id=instance_id,
                instance_name=instance_name,
                instance_type=instance_type,
                ami_image=ami_image,
            )
            self.update_json(new_data)

            # Update class attributes
            setattr(self, sshResource.INSTANCE_ID.value, new_data["resources"][sshResource.INSTANCE_ID.value])  # noqa: E501
            setattr(self, sshResource.PUBLIC_DNS_NAME.value, new_data["resources"][sshResource.PUBLIC_DNS_NAME.value])  # noqa: E501
            setattr(self, sshResource.SECURITY_GROUP_ID.value, new_data["resources"][sshResource.SECURITY_GROUP_ID.value])  # noqa: E501
            setattr(self, sshResource.KEY_PAIR.value, new_data["resources"][sshResource.KEY_PAIR.value])  # noqa: E501
            setattr(self, sshResource.STATE.value, new_data["resources"][sshResource.STATE.value])  # noqa: E501
            setattr(self, sshFile.PEM_KEY_PATH.value, new_data["files"][sshFile.PEM_KEY_PATH.value])  # noqa: E501

            # Return the data
            return new_data

        # If an error occurs, delete whatever resources may have been created
        except Exception as e:
            # Update the JSON with the resources that were created, then delete
            self.update_json(protocol.resource_data)
            deleted_resources = self.delete_resources_in_json()

            # Log the deleted resources
            for rs_name, rs_id in deleted_resources.items():
                self.output_mgr.log_output(
                    agent_img_name=self.instance_name,
                    stage=StageEnum.AGENT_DELETE,
                    level="info",
                    msg=f"Deleting {rs_name} `{rs_id}`"
                )

            # Close the live
            self.output_mgr.step_failed()

            raise e

    def get_all_local_paths(self,
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

    def _log_output(self,
        output,
        stage: StageEnum
    ):
        if output:
            if isinstance(output, str):
                if not re.findall(r"^[\-]+$", output.rstrip()):
                    self.output_mgr.log_output(
                        agent_img_name=self.instance_name,
                        stage=stage,
                        level="info",
                        msg=output.rstrip(),
                        renderable_type=f"[dodger_blue2]{output.rstrip()}[/dodger_blue2]" if stage == StageEnum.AGENT_RUN else None,  # noqa
                        is_step_completion=False,
                    )
            else:
                if not re.findall(r"^[\-]+$", output.decode().rstrip()):
                    self.output_mgr.log_output(
                        agent_img_name=self.instance_name,
                        stage=stage,
                        level="info",
                        msg=output.decode().rstrip(),
                        renderable_type=f"[dodger_blue2]{output.decode().rstrip()}[/dodger_blue2]" if stage == StageEnum.AGENT_RUN else None,  # noqa
                        is_step_completion=False,
                    )

    def stream_logs(self,
        cmd: List[str],
        stage: StageEnum,
    ):
        """
        Stream Bash script logs. We use bash scripts to run our `apply` and `run`
        commands.

        args:
            cmd: subprocess command
            stage: build stage
            color: color to use in log styling
            which: one of `build` or `run`
        returns:
            subprocess return code
        """
        # Open a subprocess and stream the logs
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        while True:
            output = process.stdout
            if output is not None:
                output = output.readline()  # type: ignore

            # Stream the logs
            if process.poll() is not None:
                break
            self._log_output(output, stage)

        return process.stdout, process.stderr, process.returncode

    def set_apply_command_attributes(self):
        """
        Set the acceptable apply command parameters
        """
        if not hasattr(self, "apply_command"):
            raise ValueError("object does not have `apply_command` attribute!")

        # If we're running a Docker image on our EC2 instance, then update the arguments
        if self.image is not None and self.image.image_conf["type"] == "docker":
            self.apply_command.set_accepted_apply_optargs(['-p', '-u', '-n'])

            # Additional optargs. Note that this function is called AFTER we push our
            # image to our registry, so our registry configuration should have all the
            # information we need.
            registry, username, password = self.image.registry.get_login_info()
            additional_optargs = {
                '-a': username,
                '-z': password,
                '-r': registry,
                '-i': f"{self.image.image_name}:{self.image.image_version}"  # type: ignore  # noqa
            }
            self.apply_command.set_additional_optargs(additional_optargs)

    def set_run_command_attributes(self):
        """
        Set the acceptable run command parameters
        """
        if not hasattr(self, "run_command"):
            raise ValueError("object does not have `run_command` attribute!")

        # If we're running a Docker image on our EC2 instance, then update the arguments
        if self.image is not None and self.image.image_conf["type"] == "docker":
            self.run_command.set_accepted_apply_optargs(['-p', '-u', '-n', '-f', '-d'])

            # Additional optargs. Note that this function is called AFTER we push our
            # image to our registry, so our registry configuration should have all the
            # information we need.
            registry, username, password = self.image.registry.get_login_info()
            additional_optargs = {
                '-a': username,
                '-z': password,
                '-r': registry,
                '-i': f"{self.image.image_name}:{self.image.image_version}"  # type: ignore # noqa
            }
            self.run_command.set_additional_optargs(additional_optargs)

    def _execute_apply_script(self,
        cmd: List[str]
    ):
        # Attributes
        security_group_id_attr = getattr(self, sshResource.SECURITY_GROUP_ID.value)

        # Open a subprocess and stream the logs
        out, err, returncode = self.stream_logs(cmd, StageEnum.AGENT_BUILD)

        # Log anything from stderr that was printed in the project
        for line in err.readlines():
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_BUILD,
                level="info",
                msg=line.rstrip()
            )

        # A return code of 8 indicates that the SSH connection timed out. Try
        # whitelisting the current IP and try again.
        if returncode == 8:
            # For mypy
            if security_group_id_attr is None:
                raise ValueError("`security_group_id` is still None!")
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_BUILD,
                level="info",
                msg="SSH connection timed out...checking security group ingress rules and trying again"  # noqa: E501
            )

            # Add the current IP to the security ingress rules
            added_ip = self.check_ingress_ip(
                self.ec2_client, security_group_id_attr
            )

            # If the current IP address is already whitelisted, then just add
            # 0.0.0.0/0 to the ingress rules.
            if added_ip is None:
                self.args.whitelist_all = True
                self.output_mgr.log_output(
                    agent_img_name=self.instance_name,
                    stage=StageEnum.AGENT_BUILD,
                    level="info",
                    msg="Current IP address already whitelisted...whitelisting 0.0.0.0/0"  # noqa: E501
                )
                self.add_ingress_rule(
                    self.ec2_client,
                    security_group_id_attr,
                    "0.0.0.0",
                )

            # Try again
            out, err, returncode = self.stream_logs(cmd, StageEnum.AGENT_BUILD)

        return out, err, returncode

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
        python_version = self.parse_infra_key(self.infra.infra_conf, "python_version")

        # If the user is using an image, then ignore the Python version
        if self.image is not None:
            if python_version != "":
                self.output_mgr.log_output(
                    agent_img_name=self.instance_name,
                    stage=StageEnum.AGENT_BUILD,
                    level="info",
                    msg="Ignoring Python version in favor of newly built image"
                )

        # requirements.txt path
        requirements_txt_path = Path(
            self.parse_requirements(self.alto_wkdir, self.agent_conf)
        )
        if str(requirements_txt_path) == ".":
            requirements_txt_str = ""
        else:
            requirements_txt_str = str(requirements_txt_path)

        # Post-build commands
        processed_post_build_commands = []
        raw_post_build_commands = self.infra.infra_conf["post_build_cmds"]
        for pbc in raw_post_build_commands:
            processed_post_build_commands.append(f'{pbc}')

        # Environment dictionary
        env_dict = self.parse_environment_variables(self.agent_conf)
        env_cli = ",".join([f"{k}={v}" for k, v in env_dict.items()])

        # Paths to copy
        all_local_paths = self.get_all_local_paths(
            self.alto_wkdir,
            self.agent_conf,
        )
        project_dir = all_local_paths.pop(0)
        all_local_paths_cli = ",".join(all_local_paths)

        # Create the instance. If we're not streaming all logs, then indicate to the
        # user that we're building resources
        instance_id_attr = getattr(self, sshResource.INSTANCE_ID.value)
        self.output_mgr.step_starting("[dodger_blue2]Building resources...[/dodger_blue2]")  # noqa
        data = self.create_instance(
            self.ec2_client,
            self.ec2_resource,
            instance_id_attr,
            self.instance_name,
            instance_type,
            ami_image,
        )
        self.output_mgr.step_completed("Built resources!", is_substep=False)

        # The `create_instance` command is blocking — it won't finish until the instance
        # is up and running.
        try:
            user = "ec2-user"
            public_dns_name = data["resources"]["public_dns_name"]
            pem_key_path = data["files"]["pem_key_path"]

            # Build the shell command
            cmd_optargs = {
                '-r': str(requirements_txt_str),
                '-p': str(pem_key_path),
                '-u': user,
                '-n': public_dns_name,
                '-d': str(project_dir),
                '-c': all_local_paths_cli,
                '-e': env_cli,
                '-v': python_version,
                '-x': processed_post_build_commands
            }
            self.apply_command = AgentCommand(
                executable='/bin/bash',
                script=self.AGENT_APPLY_SCRIPT,
                args=cmd_optargs
            )
            self.set_apply_command_attributes()

            # Set the accepted and additional optargs
            cmd = self.apply_command.process_cmd()

            # Open a subprocess and stream the logs
            self.output_mgr.step_starting("[dodger_blue2]Building agent...[/dodger_blue2]")  # noqa
            _, _, returncode = self._execute_apply_script(cmd)

            # Otherwise, if the return code is non-zero, then an error occurred. Delete
            # all of the resources so that the user can try again.
            if returncode != 0:
                self.output_mgr.step_failed()
                self.delete()
            else:
                self.output_mgr.step_completed("Built agent!", is_substep=False)

            # Return the returncode.
            self.output_mgr.stop_live()
            return returncode

        # If we encounter any sort of error, delete the resources first and then raise
        except Exception as e:
            self.output_mgr.step_failed()
            self.delete()
            raise e

    def run(self, overrides={}):
        """
        Run the project using the EC2 agent
        """
        # Attributes
        instance_id_attr = getattr(self, sshResource.INSTANCE_ID.value)
        security_group_id_attr = getattr(self, sshResource.SECURITY_GROUP_ID.value)
        public_dns_name_attr = getattr(self, sshResource.PUBLIC_DNS_NAME.value)
        pem_key_path_attr = getattr(self, sshFile.PEM_KEY_PATH.value)

        # Full command
        full_cmd = self.entrypoint.build_command()

        # Download files
        download_files = self.agent_conf["download_files"]
        download_files_cmd = []
        for df in download_files:
            download_files_cmd.append(df)

        # Logging styling
        if self.instance_name is None or instance_id_attr is None:
            self.output_mgr.log_output(  # type: ignore
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_RUN,
                level="error",
                msg="Agent data not found! Use `alto apply` to create your agent",
            )
            return

        # Check the ingress rules
        if security_group_id_attr is not None:
            self.check_ingress_ip(self.ec2_client, security_group_id_attr)

        # For mypy
        if not isinstance(public_dns_name_attr, str):
            raise ValueError("incompatible public DNS name!")

        # The agent data should exist...Build the shell command
        self.output_mgr.step_starting("[dodger_blue2]Running entrypoint...[/dodger_blue2]")  # noqa
        self.run_command = AgentCommand(
            executable='/bin/bash',
            script=self.AGENT_RUN_SCRIPT,
            args={
                '-p': str(pem_key_path_attr),
                '-u': 'ec2-user',
                '-n': public_dns_name_attr,
                '-d': str(self.alto_wkdir),
                '-c': full_cmd,
                '-f': download_files_cmd
            }
        )
        self.set_run_command_attributes()

        # Process the command and execute
        cmd = self.run_command.process_cmd()
        out, _, returncode = self.stream_logs(cmd, StageEnum.AGENT_RUN)

        # Log anything from stdout that was printed in the project
        for line in out.readlines():
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_RUN,
                level="info",
                msg=line.rstrip(),
            )

        # Return the returncode.
        if returncode != 0:
            self.output_mgr.step_failed()
        else:
            self.output_mgr.step_completed("Entrypoint completed!")
        return returncode

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

        # Key pair
        key_pair_attr = getattr(self, sshResource.KEY_PAIR.value)
        if key_pair_attr is None:
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=StageEnum.AGENT_DELETE,
                level="info",
                msg="Key pair not found! If this is a mistake, then you may need to reset your resource data"  # noqa: E501
            )

        else:
            pem_key_path_attr = getattr(self, sshFile.PEM_KEY_PATH.value)
            self.output_mgr.step_starting(
                "Deleting key-pair...",
                is_substep=True
            )
            log_key_pair = f"{alto.ui.MAGENTA}{key_pair_attr}{alto.ui.RESET}"
            log_key_path = f"{alto.ui.MAGENTA}{str(pem_key_path_attr)}{alto.ui.RESET}"  # noqa: E501
            self.ec2_client.delete_key_pair(
                KeyName=key_pair_attr
            )
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
            try:
                os.unlink(str(pem_key_path_attr))

            # If this file never existed, then pass
            except FileNotFoundError:
                self.output_mgr.log_output(
                    agent_img_name=self.instance_name,
                    stage=StageEnum.AGENT_DELETE,
                    level="info",
                    msg=f"Key-pair {log_key_pair} at {log_key_path} doesn't exist!",
                )

        # Instance
        instance_id_attr = getattr(self, sshResource.INSTANCE_ID)
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
            _ = self.ec2_client.terminate_instances(
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
        security_group_id_attr = getattr(self, sshResource.SECURITY_GROUP_ID.value)
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
            log_security_group_id = f"{alto.ui.MAGENTA}{security_group_id_attr}{alto.ui.RESET}"  # noqa: E501
            while True:
                try:
                    self.ec2_client.delete_security_group(
                        GroupId=security_group_id_attr
                    )
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
                    break
                except botocore.exceptions.ClientError as e:
                    if "DependencyViolation" in str(e):
                        self.output_mgr.log_output(
                            agent_img_name=self.instance_name,
                            stage=StageEnum.AGENT_DELETE,
                            level="info",
                            msg=f"Encountered `DependencyViolation` when deleting security group {log_security_group_id}...waiting 5 seconds and trying again"  # noqa: E501
                        )
                        time.sleep(5)
                    else:
                        raise e

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
