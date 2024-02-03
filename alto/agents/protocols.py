"""
Protocols for accessing virtual machines. Currently, only needed for EC2 instances.
"""

# Imports
import argparse
import botocore
import os
from pathlib import Path
import re
import stat
import time
from typing import Any, Dict, Optional
import urllib

# Alto imports
from alto.constants import INTERNAL_FOLDER
from alto.mixins.aws_mixins import (
    AwsMixin,
    State,
    IpAddressType,
    sshResource,
    sshFile,
)
from alto.output import (
    OutputManager,
)
import alto.ui


# Classes
class Protocol(AwsMixin):
    args: argparse.Namespace
    infra_conf: Dict[str, Any]
    output_mgr: OutputManager
    resource_data: Dict[str, Any] = {}

    def __init__(
        self,
        args: argparse.Namespace,
        infra_conf: Dict[str, Any],
        output_mgr: OutputManager
    ):
        self.args = args
        self.infra_conf = infra_conf
        self.output_mgr = output_mgr

    def create_instance(self,
        current_data: Dict[str, Any],
        ec2_client: Any,
        ec2_resource: Any,
        instance_id: Optional[str],
        instance_name: str,
        instance_type: str,
        ami_image: str,
    ):
        raise NotImplementedError


class SSHProtocol(Protocol):

    def create_key_pair(self,
        ec2_client: Any,
        key_name: str,
        directory: Path = Path(os.path.expanduser("~/.alto"))
    ) -> Optional[Path]:
        """
        Create a PEM key pair. This PEM key is required to SSH / copy files into our EC2
        instance / EMR cluster. We will call this function before the user first creates
        their instance.

        args:
            client: Boto3 EC2 client key_name: name of the new key pair directory:
            directory in which to place the keypair; default is ~/.aws/
        returns:
            path to newly created PEM key
        raises:
            UnauthorizedOperation if the user does not have the required permissions to
            create a key pair
        """
        response = ec2_client.create_key_pair(
            KeyName=key_name,
            KeyType="rsa",
            KeyFormat="pem"
        )
        if not Path(directory).is_dir():
            Path(directory).mkdir(parents=True)

        # Write the key to a local file
        try:
            with open(Path(directory / f"{key_name}.pem"), 'w') as f:
                f.write(response["KeyMaterial"])

        # If the path already exists and cannot be edited, then raise the exception. But
        # first, delete the newly created key pair.
        except Exception as e:
            ec2_client.delete_key_pair(
                KeyName=key_name
            )
            raise e

        # If, for whatever reason, the file doesn't exist, throw an error
        if not Path(directory / f"{key_name}.pem").is_file():
            raise ValueError("Could not find newly created PEM key!")

        # Change the permissions
        os.chmod(Path(directory / f"{key_name}.pem"), stat.S_IREAD)

        # We'll need to persist the location of the PEM key across runs. For example,
        # let's say a user calls `agent apply` and creates the key-pair and EC2
        # instance. When they call `agent run`, we will need to use the PEM key created
        # by `agent apply` to execute the operation. For now, return the path. We'll
        # save out a JSON with this path in the agent class.
        return Path(directory / f"{key_name}.pem")

    def create_new_security_group(self,
        ec2_client: Any,
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

    def create_instance(self,
        current_data: Dict[str, Any],
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
        current_resources = current_data.get("resources", {})
        current_files = current_data.get("files", {})

        # Wrap the whole thing in a single try-except block
        try:

            def _create_exception(resource):
                return ValueError('\n'.join([
                    f"{resource} exists, but ~/.alto/ec2.json file not found! This only happens if:",  # noqa: E501
                    f"    1. You manually created the {resource}",
                    "    2. You deleted ~/.alto/ec2.json",
                    f"Delete the {resource} from EC2 and try again!"
                ]))

            # Create PEM key pair
            self.output_mgr.step_starting(
                "Creating key pair",
                is_substep=True
            )
            if current_resources.get(sshResource.KEY_PAIR.value, None) is None:
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

                # If the key-pair exists, then the location of the PEM key path should
                # be contained in ~/.alto/ec2.json. If it isn't, then either:
                #   1. The user manually created the key pair
                #   2. The user deleted ~/.alto/ec2.json
                if not Path(INTERNAL_FOLDER / 'ec2.json').is_file():
                    raise _create_exception(sshResource.KEY_PAIR.value)
                pem_key_path = current_files[sshFile.PEM_KEY_PATH.value]

                # Log
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
                "resources": {sshResource.KEY_PAIR.value: instance_name},
                "files": {sshFile.PEM_KEY_PATH.value: str(pem_key_path)}
            }

            # Security group
            self.output_mgr.step_starting(
                "Creating security group",
                is_substep=True
            )
            if current_resources.get(sshResource.SECURITY_GROUP_ID.value, None) is None:
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
                if not Path(INTERNAL_FOLDER / 'ec2.json').is_file():
                    raise _create_exception(sshResource.SECURITY_GROUP_ID.value)

                # Log
                security_group_id = current_resources[sshResource.SECURITY_GROUP_ID.value]  # noqa
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
                {sshResource.SECURITY_GROUP_ID.value: security_group_id},
            )

            # Log instance ID template
            log_instance_id_template = f"{alto.ui.MAGENTA}{{instance_id}}{alto.ui.RESET}"  # noqa: E501

            # Instance
            self.output_mgr.step_starting(
                "Creating EC2 instance",
                is_substep=True
            )
            if current_resources.get(sshResource.INSTANCE_ID.value, None) is None:
                instance = ec2_resource.create_instances(
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
                instance_id = instance[0].id

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
                if not Path(INTERNAL_FOLDER / 'ec2.json').is_file():
                    raise _create_exception(sshResource.INSTANCE_ID.value)
                instance_id = current_resources[sshResource.INSTANCE_ID.value]

                # Log
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
                    "instance_id": instance_id,  # type: ignore
                    "public_dns_name": resp["public_dns_name"],
                    "state": resp["state"]
                }
            )

            # Return the data
            return self.resource_data

        # Raise whatever exception arises. In the agent, we parse through the resources
        # that were created and delete them.
        except Exception as e:
            raise e


class SSMProtocol(Protocol):
    pass
