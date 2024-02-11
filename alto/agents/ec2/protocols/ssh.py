"""
Protocols for accessing virtual machines. Currently, only needed for EC2 instances.
"""

# Imports
import botocore
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional
import urllib
import subprocess

# Alto imports
from alto.agents.ec2.protocols.base import Protocol
from alto.command import AgentCommand
from alto.entrypoints import BaseEntrypoint
from alto.images import BaseImage
from alto.mixins.aws_mixins import (
    State,
    IpAddressType,
    ec2Resource,
    ec2File,
)
import alto.ui

# Type hints
from mypy_boto3_ec2.client import EC2Client


# Classes
class SSHProtocol(Protocol):
    apply_command: AgentCommand
    run_command: AgentCommand

    def create_new_security_group(self,
        ec2_client: EC2Client,
        instance_name: str,
    ):
        """
        Create a new security group for our EC2 instance. This security group allows
        traffic from the user's IP only.

        args:
            ec2_client: Boto3 EC2 client
            instance_id: instance ID
        returns:
            newly created security group ID
        """

        # Default VPC
        response = ec2_client.describe_vpcs()
        vpc_id = response.get('Vpcs', [{}])[0].get('VpcId', '')

        # Create the security group
        response = ec2_client.create_security_group(
            GroupName=instance_name,
            Description=f'VPC for {instance_name} EC2 agent',
            VpcId=vpc_id
        )
        security_group_id = response['GroupId']

        # Add an ingress rule
        try:
            external_ip = urllib.request.urlopen('https://ident.me').read().decode('utf8')  # type: ignore # noqa: E501
            self.add_ingress_rule(
                ec2_client,
                security_group_id,
                external_ip
            )
            return security_group_id, vpc_id

        # If we encounter an error, first delete the newly created security group. Then
        # raise the exception.
        except Exception as e:

            # The security group shouldn't be attached to an instance at this point, so
            # we are safe to just delete it.
            ec2_client.delete_security_group(
                GroupId=security_group_id
            )
            raise e

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
        ec2_client: EC2Client,
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
        ec2_client: EC2Client,
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
        external_ip = urllib.request.urlopen('https://ident.me').read().decode('utf8')  # type: ignore # noqa: E501
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

    def create_resources(self,
        current_data: Dict[str, Any],
        ec2_client: EC2Client,
        instance_name: str,
        instance_type: str,
        ami_image: str,
    ):
        """
        Create EC2 resources

        args:
            current_data: current EC2 resources/files data
            ec2_client: Boto3 AWS EC2 client
            ec2_resource: Boto3 AWS EC2 resource
            instance_id: EC2 instance ID
            instance_name: EC2 instance name
            instance_type: EC2 instance types
            ami_image: AMI image to use in instance
        returns:
            EC2 response
        """
        current_resources = current_data.get("resources", {})
        current_files = current_data.get("files", {})

        # Wrap the whole thing in a single try-except block
        try:
            # Create PEM key pair
            self.output_mgr.step_starting(
                "Creating key pair",
                is_substep=True
            )
            if current_resources.get(ec2Resource.KEY_PAIR.value, None) is None:
                pem_key_path = self.create_key_pair(
                    ec2_client,
                    key_name=instance_name,
                )
                log_instance_name = f"{alto.ui.MAGENTA}{instance_name}{alto.ui.RESET}"  # noqa: E501
                self.output_mgr.log_output(
                    agent_img_name=instance_name,
                    stage=alto.ui.StageEnum.AGENT_BUILD,
                    level="info",
                    msg=f"Created key pair {log_instance_name}",
                    renderable_type="Created key-pair",
                    is_step_completion=True,
                    is_substep=True
                )
            else:
                pem_key_path = current_files[ec2File.PEM_KEY_PATH.value]
                log_instance_name = f"{alto.ui.MAGENTA}{instance_name}{alto.ui.RESET}"  # noqa: E501
                log_instance_path = f"{alto.ui.MAGENTA}{str(pem_key_path)}{alto.ui.RESET}"  # noqa: E501
                self.output_mgr.log_output(
                    agent_img_name=instance_name,
                    stage=alto.ui.StageEnum.AGENT_BUILD,
                    level="info",
                    msg=f"Using existing key-pair {log_instance_name} at {log_instance_path}",  # noqa
                    renderable_type="Using existing key-pair",
                    is_step_completion=True,
                    is_substep=True
                )

            # Data to write to JSON
            self.resource_data = {
                "resources": {ec2Resource.KEY_PAIR.value: instance_name},
                "files": {ec2File.PEM_KEY_PATH.value: str(pem_key_path)}
            }

            # Security group
            self.output_mgr.step_starting(
                "Creating security group",
                is_substep=True
            )
            if current_resources.get(ec2Resource.SECURITY_GROUP_ID.value, None) is None:
                security_group_id, vpc_id = self.create_new_security_group(
                    ec2_client,
                    instance_name
                )

                # Log
                log_security_group_id = f"{alto.ui.MAGENTA}{security_group_id}{alto.ui.RESET}"  # noqa: E501
                log_vpc_id = f"{alto.ui.MAGENTA}{vpc_id}{alto.ui.RESET}"  # noqa: E501
                self.output_mgr.log_output(
                    agent_img_name=instance_name,
                    stage=alto.ui.StageEnum.AGENT_BUILD,
                    level="info",
                    msg=f"Created security group with ID {log_security_group_id} in VPC {log_vpc_id}",  # noqa: E501
                    renderable_type="Created security group",
                    is_step_completion=True,
                    is_substep=True
                )
            else:
                security_group_id = current_resources[ec2Resource.SECURITY_GROUP_ID.value]  # noqa
                self.check_ingress_ip(ec2_client, security_group_id)
                log_security_group_id = f"{alto.ui.MAGENTA}{security_group_id}{alto.ui.RESET}"  # noqa: E501
                self.output_mgr.log_output(
                    agent_img_name=instance_name,
                    stage=alto.ui.StageEnum.AGENT_BUILD,
                    level="info",
                    msg=f"Using existing security group {log_security_group_id}",  # noqa: E501
                    renderable_type="Using existing security group",
                    is_step_completion=True,
                    is_substep=True
                )

            # Data to write to JSON
            self.resource_data["resources"].update(
                {ec2Resource.SECURITY_GROUP_ID.value: security_group_id},
            )

            # Log instance ID template
            log_instance_id_template = f"{alto.ui.MAGENTA}{{instance_id}}{alto.ui.RESET}"  # noqa: E501

            # Instance
            self.output_mgr.step_starting(
                "Creating EC2 instance",
                is_substep=True
            )
            if current_resources.get(ec2Resource.INSTANCE_ID.value, None) is None:
                resp = ec2_client.run_instances(
                    InstanceType=instance_type,
                    KeyName=instance_name,
                    MinCount=1,
                    MaxCount=1,
                    ImageId=ami_image,
                    TagSpecifications=[
                        {
                            'ResourceType': 'instance',
                            'Tags': [
                                {
                                    'Key': 'Name',
                                    'Value': instance_name
                                },
                            ]
                        },
                    ],
                    SecurityGroupIds=[
                        security_group_id
                    ]
                )
                instance = resp["Instances"][0]
                instance_id = instance["InstanceId"]

                # Log
                self.output_mgr.log_output(
                    agent_img_name=instance_name,
                    stage=alto.ui.StageEnum.AGENT_BUILD,
                    level="info",
                    msg=f"Created EC2 instance with ID {log_instance_id_template.format(instance_id=instance_id)}",  # noqa: E501
                    renderable_type="Created EC2 instance",
                    is_step_completion=True,
                    is_substep=True
                )
                time.sleep(1)
            else:
                self.output_mgr.log_output(
                    agent_img_name=instance_name,
                    stage=alto.ui.StageEnum.AGENT_BUILD,
                    level="info",
                    msg=f"Using existing EC2 instance with ID {log_instance_id_template.format(instance_id=instance_id)}",  # noqa: E501
                    renderable_type="Using existing EC2 instance",
                    is_step_completion=True,
                    is_substep=True
                )

            # Instance data
            resp = self.check_instance_data(instance_id)

            # If the instance exists but its key-name is not `instance_name` (this
            # really should never happen unless the user manually creates an EC2
            # instance that has the same name), then raise an error
            if len(resp.keys()) > 0 and resp["key_name"] != instance_name:
                raise ValueError(
                    f"unrecognized key `{resp['key_name']}`...the agent requires key `{instance_name}.pem`"  # noqa: E501
                )

            # If the instance exists and is running, then just return
            elif len(resp.keys()) > 0 and resp["state"] in [State.PENDING, State.RUNNING]:  # noqa: E501
                while resp["state"] == State.PENDING:

                    # Log
                    log_pending_status = f"{alto.ui.YELLOW}pending{alto.ui.RESET}"  # noqa: E501
                    self.output_mgr.log_output(
                        agent_img_name=instance_name,
                        stage=alto.ui.StageEnum.AGENT_BUILD,
                        level="info",
                        msg=f"Instance {log_instance_id_template.format(instance_id=instance_id)} is {log_pending_status}... checking again in 5 seconds"  # noqa: E501
                    )
                    resp = self.check_instance_data(instance_id)
                    time.sleep(5)

            # If the state exiss but has stopped, then restart it
            elif len(resp.keys()) > 0 and resp["state"] in [State.STOPPED, State.STOPPING]:  # noqa: E501
                self.restart_instance(
                    ec2_client,
                    resp["state"],
                    resp["instance_id"]
                )

            # Write data
            self.resource_data["resources"].update(
                {
                    ec2Resource.INSTANCE_ID.value: instance_id,
                    ec2Resource.PUBLIC_DNS_NAME.value: resp["public_dns_name"],
                    ec2Resource.STATE.value: resp["state"]
                }
            )

            # Return the data
            return self.resource_data

        # Raise whatever exception arises. In the agent, we parse through the resources
        # that were created and delete them.
        except Exception as e:
            raise e

    def _log_output(self,
        output,
        instance_name: str,
        stage: alto.ui.StageEnum
    ):
        if output:
            if isinstance(output, str):
                if not re.findall(r"^[\-]+$", output.rstrip()):
                    self.output_mgr.log_output(
                        agent_img_name=instance_name,
                        stage=stage,
                        level="info",
                        msg=output.rstrip(),
                        renderable_type=f"[dodger_blue2]{output.rstrip()}[/dodger_blue2]" if stage == alto.ui.StageEnum.AGENT_RUN else None,  # noqa
                        is_step_completion=False,
                    )
            else:
                if not re.findall(r"^[\-]+$", output.decode().rstrip()):
                    self.output_mgr.log_output(
                        agent_img_name=instance_name,
                        stage=stage,
                        level="info",
                        msg=output.decode().rstrip(),
                        renderable_type=f"[dodger_blue2]{output.decode().rstrip()}[/dodger_blue2]" if stage == alto.ui.StageEnum.AGENT_RUN else None,  # noqa
                        is_step_completion=False,
                    )

    def stream_logs(self,
        cmd: List[str],
        instance_name: str,
        stage: alto.ui.StageEnum,
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
            self._log_output(output, instance_name, stage)

        return process.stdout, process.stderr, process.returncode

    def set_apply_command_attributes(self, image: BaseImage):
        """
        Set the acceptable apply command parameters
        """
        # If we're running a Docker image on our EC2 instance, then update the arguments
        if image is not None and image.image_conf["type"] == "docker":
            self.apply_command.set_accepted_apply_optargs(['-p', '-u', '-n'])

            # Additional optargs. Note that this function is called AFTER we push our
            # image to our registry, so our registry configuration should have all the
            # information we need.
            registry, username, password = image.registry.get_login_info()
            additional_optargs = {
                '-a': username,
                '-z': password,
                '-r': registry,
                '-i': f"{image.image_name}:{image.image_version}"  # type: ignore  # noqa
            }
            self.apply_command.set_additional_optargs(additional_optargs)

    def set_run_command_attributes(self, image: BaseImage):
        """
        Set the acceptable run command parameters
        """
        if not hasattr(self, "run_command"):
            raise ValueError("object does not have `run_command` attribute!")

        # If we're running a Docker image on our EC2 instance, then update the arguments
        if image is not None and image.image_conf["type"] == "docker":
            self.run_command.set_accepted_apply_optargs(['-p', '-u', '-n', '-f', '-d'])

            # Additional optargs. Note that this function is called AFTER we push our
            # image to our registry, so our registry configuration should have all the
            # information we need.
            registry, username, password = image.registry.get_login_info()
            additional_optargs = {
                '-a': username,
                '-z': password,
                '-r': registry,
                '-i': f"{image.image_name}:{image.image_version}"  # type: ignore # noqa
            }
            self.run_command.set_additional_optargs(additional_optargs)

    def _execute_apply_script(self,
        cmd: List[str],
        instance_name: str,
        ec2_client: EC2Client,
        security_group_id: str,
    ):
        # Open a subprocess and stream the logs
        out, err, returncode = self.stream_logs(
            cmd, instance_name, alto.ui.StageEnum.AGENT_BUILD
        )

        # Log anything from stderr that was printed in the project
        for line in err.readlines():
            self.output_mgr.log_output(
                agent_img_name=instance_name,
                stage=alto.ui.StageEnum.AGENT_BUILD,
                level="info",
                msg=line.rstrip()
            )

        # A return code of 8 indicates that the SSH connection timed out. Try
        # whitelisting the current IP and try again.
        if returncode == 8:
            self.output_mgr.log_output(
                agent_img_name=instance_name,
                stage=alto.ui.StageEnum.AGENT_BUILD,
                level="info",
                msg="SSH connection timed out...checking security group ingress rules and trying again"  # noqa: E501
            )

            # Add the current IP to the security ingress rules
            added_ip = self.check_ingress_ip(
                ec2_client, security_group_id
            )

            # If the current IP address is already whitelisted, then just add
            # 0.0.0.0/0 to the ingress rules.
            if added_ip is None:
                self.args.whitelist_all = True
                self.output_mgr.log_output(
                    agent_img_name=instance_name,
                    stage=alto.ui.StageEnum.AGENT_BUILD,
                    level="info",
                    msg="Current IP address already whitelisted...whitelisting 0.0.0.0/0"  # noqa: E501
                )
                self.add_ingress_rule(
                    ec2_client,
                    security_group_id,
                    "0.0.0.0",
                )

            # Try again
            out, err, returncode = self.stream_logs(
                cmd, instance_name, alto.ui.StageEnum.AGENT_BUILD
            )
        return out, err, returncode

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
        """
        Set up our instance. We call this command after `create_resources`, so our
        instance should be up and running.

        args:
            current_data: current EC2 data from ~/.alto/ec2.json
            ec2_client: Boto3 EC2 client
            image: image associated with infrastructure
            instance_name: EC2 instance name
            ec2_user: root user Amazon Linux instances
            requirements_txt_str: path to requirements file
            local_mounts: list of files to mount onto instance
            env_vars: dictionary of environment variables
            python_version: Python version to install on Linux instance;
            post_build_commands: list of commands to run in Linux build
        returns:
            return code for agent's apply script
        """
        security_group_id = current_data["resources"][ec2Resource.SECURITY_GROUP_ID.value]  # noqa: E501
        public_dns_name = current_data["resources"][ec2Resource.PUBLIC_DNS_NAME.value]
        pem_key_path = str(current_data["files"][ec2File.PEM_KEY_PATH.value])

        # Project directory and local mounts
        project_dir = local_mounts.pop(0)
        local_mounts_cli = ",".join(local_mounts)

        # Environment CLI
        env_cli = ",".join([f"{k}={v}" for k, v in env_vars.items()])

        # Build the shell command
        cmd_optargs = {
            '-r': str(requirements_txt_str),
            '-p': str(pem_key_path),
            '-u': ec2_user,
            '-n': public_dns_name,
            '-d': str(project_dir),
            '-c': local_mounts_cli,
            '-e': env_cli,
            '-v': python_version,
            '-x': post_build_commands
        }
        self.apply_command = AgentCommand(
            executable='/bin/bash',
            script=self.apply_script,
            args=cmd_optargs
        )
        self.set_apply_command_attributes(image)

        # Set the accepted and additional optargs
        cmd = self.apply_command.process_cmd()

        # Open a subprocess and stream the logs
        _, _, returncode = self._execute_apply_script(
            cmd, instance_name, ec2_client, security_group_id
        )
        return returncode

    def run_entrypoint_on_instance(self,
        current_data: Dict[str, Any],
        ec2_client: EC2Client,
        alto_wkdir: Path,
        image: Optional[BaseImage],
        instance_name: str,
        entrypoint: BaseEntrypoint,
        download_files: List[str],
    ) -> int:
        """
        Set up our instance. We call this command after `create_resources`, so our
        instance should be up and running.

        args:
            current_resource: current EC2 resources associated with the protocol
            kwargs: arguments needed to set up instance via SSH
        """
        instance_id = current_data["resources"].get(
            ec2Resource.INSTANCE_ID.value, None
        )
        security_group_id = current_data["resources"].get(
            ec2Resource.SECURITY_GROUP_ID.value, None
        )
        public_dns_name = current_data["resources"].get(
            ec2Resource.PUBLIC_DNS_NAME.value, None
        )
        pem_key_path = Path(current_data["files"].get(
            ec2File.PEM_KEY_PATH.value, None
        ))

        # Full command
        full_cmd = entrypoint.build_command()

        # Download files
        download_files_cmd = []
        for df in download_files:
            download_files_cmd.append(df)

        # Logging styling
        if instance_id is None:
            self.output_mgr.log_output(  # type: ignore
                agent_img_name=instance_name,
                stage=alto.ui.StageEnum.AGENT_RUN,
                level="error",
                msg="Agent data not found! Use `alto apply` to create your agent",
            )
            return 1

        # Check the ingress rules
        if security_group_id is not None:
            self.check_ingress_ip(ec2_client, security_group_id)

        # For mypy
        if not isinstance(public_dns_name, str):
            raise ValueError("incompatible public DNS name!")

        # The agent data should exist...Build the shell command
        self.run_command = AgentCommand(
            executable='/bin/bash',
            script=self.run_script,
            args={
                '-p': str(pem_key_path),
                '-u': 'ec2-user',
                '-n': public_dns_name,
                '-d': str(alto_wkdir),
                '-c': full_cmd,
                '-f': download_files_cmd
            }
        )
        self.set_run_command_attributes(image)

        # Process the command and execute
        cmd = self.run_command.process_cmd()
        out, _, returncode = self.stream_logs(
            cmd, instance_name, alto.ui.StageEnum.AGENT_RUN
        )

        # Log anything from stdout that was printed in the project
        for line in out.readlines():
            self.output_mgr.log_output(
                agent_img_name=self.instance_name,
                stage=alto.ui.StageEnum.AGENT_RUN,
                level="info",
                msg=line.rstrip(),
            )
        return returncode
