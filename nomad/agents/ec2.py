"""
Docker Agent.
"""


###########
# Imports #
###########

# Nomad imports
from nomad.agents.base import Agent
from nomad.constants import (
    INTERNAL_FOLDER,
    DEFAULT_LOGGER_NAME
)
import nomad.ui
from nomad.entrypoints import BaseEntrypoint
from nomad.infras import BaseInfra
from nomad.command import AgentCommand
from nomad.images import BaseImage, Docker as DockerImage
from nomad.divider import Divider

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
import stat


##########
# Logger #
##########

import logging
logger = logging.getLogger(DEFAULT_LOGGER_NAME)

# Dividers
BUILD_DIVIDER = Divider("build")
RUN_DIVIDER = Divider("run")
DELETE_DIVIDER = Divider("delete")


####################
# Class definition #
####################

class State(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    SHUTTING_DOWN = "shutting-down"
    TERMINATED = "terminated"


class IpAddressType(str, Enum):
    V4 = "ipv4"
    V6 = "ipv6"


class Ec2(Agent):

    def __init__(self,
        args: argparse.Namespace,
        nomad_wkdir: Path,
        agent_name: str,
        agent_conf: Dict[str, Any],
        infra: BaseInfra,
        entrypoint: BaseEntrypoint,
        image: Optional[BaseImage],
        mode: str = "prod"
    ):
        Agent.__init__(
            self, args, nomad_wkdir, agent_name, agent_conf, infra, entrypoint, image, mode  # noqa
        )

        # Bash dir
        scripts_dir = f"{os.path.dirname(__file__)}/scripts"
        self.AGENT_APPLY_SCRIPT = f"{scripts_dir}/ec2/apply.sh"
        self.AGENT_RUN_SCRIPT = f"{scripts_dir}/ec2/run.sh"

        # Use slightly different scripts if the user wants to run a Docker image on
        # their EC2 instance.
        if isinstance(image, DockerImage):
            self.AGENT_APPLY_SCRIPT = f"{scripts_dir}/docker/ec2/apply.sh"
            self.AGENT_RUN_SCRIPT = f"{scripts_dir}/docker/ec2/run.sh"

        # Create the client
        self.aws_cli()
        self.ec2_client = boto3.client('ec2')
        self.ec2_resource = boto3.resource('ec2')

        # Instance name
        nomad_project_name = self.nomad_wkdir.name.replace("_", "-")
        self.instance_name = f"{nomad_project_name}-{self.agent_name}"

        # Create an empty `ec2.json` file if it doesn't exist
        if not Path(INTERNAL_FOLDER / 'ec2.json').is_file():
            with open(Path(INTERNAL_FOLDER / 'ec2.json'), 'w') as f:
                f.write("{}")

        # Load the current data
        with open(Path(INTERNAL_FOLDER / 'ec2.json'), 'r') as f:
            data = json.loads(f.read())
        f.close()

        # If the current instance doesn't exist in the data, then all the attributes
        # will be `None`
        if self.instance_name not in data.keys():
            self.instance_id: Optional[str] = None
            self.public_dns_name: Optional[str] = None
            self.security_group_id: Optional[str] = None
            self.key_name: Optional[str] = None
            self.pem_key_path: Optional[Path] = None
            self.state: Optional[str] = None

        else:
            data = data[self.instance_name]

            # If the data exists, then it must be a JSON with two keys: "resources"
            # and "files".
            for attr in [
                "instance_id",
                "public_dns_name",
                "security_group_id",
                "key_name",
                "state"
            ]:
                if attr in data["resources"].keys():
                    self.__setattr__(attr, data["resources"][attr])
                else:
                    self.__setattr__(attr, None)

            # Set PEM key path
            if "pem_key_path" in data["files"].keys():
                self.pem_key_path = Path(data["files"]["pem_key_path"])

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

    def create_key_pair(self,
        ec2_client: Any,
        key_name: str,
        directory: Path = Path(os.path.expanduser("~/.nomad"))
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

    def write_json(self, data: Dict[str, Dict[str, Any]]):
        """
        Write `data` to ~/.nomad/ec2.json

        args:
            data: data to write to JSON
        """
        with open(Path(INTERNAL_FOLDER) / 'ec2.json', 'w') as f:
            json.dump(data, f)

    def update_json(self, data: Dict[str, Dict[str, Any]]):
        """
        Update ~/.nomad/ec2.json

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
        json_path = Path(INTERNAL_FOLDER) / 'ec2.json'
        if not json_path.is_file():
            return del_resources
        else:
            with open(json_path, 'r') as f:
                json_data = json.loads(f.read())
            f.close()
            json_data = json_data[self.instance_name]

            # Resources and files
            resources = json_data["resources"]
            files = json_data["files"]

            # Key name
            if "key_name" in resources.keys():
                pem_key_path = files["pem_key_path"]
                self.ec2_client.delete_key_pair(
                    KeyName=resources["key_name"]
                )
                os.unlink(str(pem_key_path))
                del_resources["PEM key"] = resources["key_name"]

            # Instance
            if "instance_id" in resources.keys():
                self.ec2_client.terminate_instances(
                    InstanceIds=[resources["instance_id"]]
                )
                del_resources["instance"] = resources["instance_id"]

            # Security group
            if "security_group_id" in resources.keys():
                while True:
                    try:
                        self.ec2_client.delete_security_group(
                            GroupId=resources["security_group_id"]
                        )
                        break
                    except botocore.exceptions.ClientError as e:
                        if "DependencyViolation" in str(e):
                            time.sleep(5)
                        else:
                            raise e

                del_resources["security group"] = resources["security_group_id"]

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
        resources["key_pair"] = None
        keypairs = ec2_client.describe_key_pairs()
        for kp in keypairs["KeyPairs"]:
            if kp["KeyName"] == instance_name:
                resources["key_pair"] = kp

        # Security groups
        resources["security_group"] = None
        security_groups = ec2_client.describe_security_groups()
        for sg in security_groups["SecurityGroups"]:
            if sg["GroupName"] == instance_name:
                resources["security_group"] = sg

        # Instance
        resources["instance"] = None
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

                        # Otherwise, set to True
                        resources["instance"] = inst

        # Return the resources
        return resources

    def check_instance_data(self,
        instance_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Check if the instance exists

        args:
            ec2_client: Boto3 EC2 client
            instance_id: instance ID
        returns:
            empty dictionary if instance does not exist. otherwise, a dictionary with
            {
                "instance_id": ...,
                "public_dns_name": ...,
                "key_name": ...,
                "state": ...,
            }
        """
        ec2_client = boto3.client("ec2")
        results: Dict[str, Any] = {}

        # If the instance is None, then return an empty dictionary. This happens if the
        # user is creating their first instance or deleted their previous agent and is
        # re-creating one.
        if instance_id is None:
            return results

        # Describe instances and iterate through them
        response = ec2_client.describe_instances()
        reservations = response["Reservations"]
        if len(reservations) > 0:
            for res in reservations:
                instances = res["Instances"]
                for inst in instances:
                    if inst["InstanceId"] == instance_id:
                        results["instance_id"] = instance_id
                        results["public_dns_name"] = inst["PublicDnsName"]
                        results["key_name"] = inst["KeyName"]
                        results["security_groups"] = inst["SecurityGroups"]
                        results["state"] = State(inst["State"]["Name"])

        # Return
        return results

    def restart_instance(self,
        ec2_client,
        state: State,
        instance_id: str,
    ) -> Optional[State]:
        """
        If the instance name already exists, check if it's running. If it isn't (i.e.,
        it's been stopped), then restart it.

        args:
            ec2_client: Boto3 EC2 client
            state: state of instance
            instance_name: name of instance to restart
            instance_id: ID of instance to restart
        returns:
            State of restarted instance (should only be State.RUNNING)
        """
        if state is None:
            raise ValueError(
                "`start_stopped_instance` called on a nonexistent instance!"  # noqa: E501
            )

        # If the instance is pending, then wait until the state is running
        elif state == State.PENDING:
            while state == State.PENDING:
                results = self.check_instance_data(instance_id)
                state = results["state"]
                time.sleep(1)
            return state

        # If the instance is stopping / stopped, then restart it and wait until the
        # state is `running`.
        elif state in [State.STOPPED, State.STOPPING]:
            ec2_client.start_instances(InstanceIds=instance_id)
            while state != State.RUNNING:
                results = self.check_instance_data(instance_id)
                time.sleep(1)
                state = results["state"]
            return state

        # If nothing's been returned, then the instance should already be running
        return state

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
            external_ip = urllib.request.urlopen('https://ident.me').read().decode('utf8')  # noqa: E501
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
        # Wrap the whole thing in a single try-except block
        try:

            # Data to write
            data = {}

            # Check resources
            resources = self.check_resources(ec2_client, instance_name, instance_id)

            # Log prefix
            log_prefix = f"{nomad.ui.AGENT_EVENT}{instance_name}{nomad.ui.AGENT_WHICH_BUILD}{BUILD_DIVIDER.__str__()}{nomad.ui.RESET}|"  # noqa: E501

            def _create_exception(resource):
                return ValueError('\n'.join([
                    f"{resource} exists, but ~/.nomad/ec2.json file not found! This only happens if:",  # noqa: E501
                    f"    1. You manually created the {resource}",
                    "    2. You deleted ~/.nomad/ec2.json",
                    f"Delete the {resource} from EC2 and try again!"
                ]))

            # Create PEM key pair
            if resources["key_pair"] is None:
                pem_key_path = self.create_key_pair(
                    ec2_client,
                    key_name=instance_name,
                )
                log_instance_name = f"{nomad.ui.MAGENTA}{instance_name}{nomad.ui.RESET}"  # noqa: E501
                logger.info(
                    f"{log_prefix} Created key pair {log_instance_name}"
                )

                # Write the data to the JSON
                data = {
                    "resources": {"key_name": instance_name},
                    "files": {"pem_key_path": str(pem_key_path)}
                }
                self.update_json(data)
            else:

                # If the key-pair exists, then the location of the PEM key path should
                # be contained in ~/.nomad/ec2.json. If it isn't, then either:
                #   1. The user manually created the key pair
                #   2. The user deleted ~/.nomad/ec2.json
                if not Path(INTERNAL_FOLDER / 'ec2.json').is_file():
                    raise _create_exception("key-pair")
                pem_key_path = self.pem_key_path

                # Log
                log_instance_name = f"{nomad.ui.MAGENTA}{instance_name}{nomad.ui.RESET}"  # noqa: E501
                log_instance_path = f"{nomad.ui.MAGENTA}{str(pem_key_path)}{nomad.ui.RESET}"  # noqa: E501
                logger.info(
                    f"{log_prefix} Using existing key-pair {log_instance_name} at {log_instance_path}"  # noqa: E501
                )

            # Security group
            if resources["security_group"] is None:
                security_group_id, vpc_id = self.create_new_security_group(
                    ec2_client,
                    instance_name
                )

                # Log
                log_security_group_id = f"{nomad.ui.MAGENTA}{security_group_id}{nomad.ui.RESET}"  # noqa: E501
                log_vpc_id = f"{nomad.ui.MAGENTA}{vpc_id}{nomad.ui.RESET}"  # noqa: E501
                logger.info(
                    f"{log_prefix} Created security group with ID {log_security_group_id} in VPC {log_vpc_id}"  # noqa: E501
                )

                # Write the data to the JSON
                data = {
                    "resources": {"security_group_id": security_group_id},
                }
                self.update_json(data)
            else:
                if not Path(INTERNAL_FOLDER / 'ec2.json').is_file():
                    raise _create_exception("security group")

                # Log
                security_group_id = self.security_group_id
                self.check_ingress_ip(ec2_client, security_group_id)
                log_security_group_id = f"{nomad.ui.MAGENTA}{security_group_id}{nomad.ui.RESET}"  # noqa: E501
                logger.info(
                    f"{log_prefix} Using existing security group {log_security_group_id}"  # noqa: E501
                )

            # Log instance ID template
            log_instance_id_template = f"{nomad.ui.MAGENTA}{{instance_id}}{nomad.ui.RESET}"  # noqa: E501

            # Instance
            if resources["instance"] is None:
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
                logger.info(
                    f"{log_prefix} Created EC2 instance with ID {log_instance_id_template.format(instance_id=instance_id)}"  # noqa: E501
                )
                time.sleep(1)
            else:
                if not Path(INTERNAL_FOLDER / 'ec2.json').is_file():
                    raise _create_exception("instance")
                instance_id = self.instance_id

                # Log
                logger.info(
                    f"{log_prefix} Using existing EC2 instance with ID {log_instance_id_template.format(instance_id=instance_id)}"  # noqa: E501
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
                    log_pending_status = f"{nomad.ui.YELLOW}pending{nomad.ui.RESET}"  # noqa: E501
                    logger.info(
                        f"{log_prefix} Instance {log_instance_id_template.format(instance_id=instance_id)} is {log_pending_status}... checking again in 5 seconds"  # noqa: E501
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
            data = {
                "resources": {
                    "instance_id": instance_id,  # type: ignore
                    "public_dns_name": resp["public_dns_name"],
                    "state": resp["state"]
                },
            }
            data = self.update_json(data)

            # Update class attributes
            self.instance_id = instance_id
            self.public_dns_name = resp["public_dns_name"]
            self.security_group_id = security_group_id
            self.key_name = instance_name
            self.state = resp["state"]
            self.pem_key_path = pem_key_path

            # Return the data
            return data

        # If an error occurs, delete whatever resources may have been created
        except Exception as e:
            deleted_resources = self.delete_resources_in_json()

            # Log the deleted resources
            log_prefix = f"{nomad.ui.AGENT_EVENT}{self.instance_name}{nomad.ui.RED}{DELETE_DIVIDER.__str__()}{nomad.ui.RESET}|"  # noqa: E501
            for rs_name, rs_id in deleted_resources.items():
                logger.info(
                    f"{log_prefix} Deleting {rs_name} `{rs_id}`"
                )
            raise e

    def get_all_local_paths(self,
        nomad_wkdir: Path,
        agent_conf: Dict[str, Any],
    ) -> List[str]:
        """
        Prior to running our code on the EC2 instance, we first copy our code onto the
        instance using SSH / SCP protocols. Specifically, we copy the current working
        directory and `additional_paths`.

        args:
            nomad_wkdir: user's working directory
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
        return [str(nomad_wkdir)] + additional_paths

    def _log_output(self,
        color: str,
        which: str,
        output: Any,
    ):
        if which == "run":
            divider = RUN_DIVIDER
        elif which == "build":
            divider = BUILD_DIVIDER
        log_prefix = f"{nomad.ui.AGENT_EVENT}{self.instance_name}{color}{divider.__str__()}{nomad.ui.RESET}|"  # noqa
        if output:
            if isinstance(output, str):
                if not re.findall(r"^[\-]+$", output.rstrip()):
                    logger.info(
                        f"{log_prefix} {output.rstrip()}"  # noqa: E501
                    )
            else:
                if not re.findall(r"^[\-]+$", output.decode().rstrip()):
                    logger.info(
                        f"{log_prefix} {output.decode().rstrip()}"  # noqa: E501
                    )

    def stream_logs(self,
        cmd: List[str],
        color: str,
        which: str
    ):
        """
        Stream Bash script logs. We use bash scripts to run our `apply` and `run`
        commands.

        args:
            cmd: subprocess command
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
            shell=False,
            universal_newlines=True,
        )
        while True:
            # For whatever reason, the `prism` command places the log in stderr, not
            # stdout
            if which == "build":
                output = process.stdout.readline()  # type: ignore
                stderr = process.stderr.readline()  # type: ignore
            else:
                output = process.stderr.readline()  # type: ignore
                stderr = None

            # Stream the logs
            if process.poll() is not None:
                break
            self._log_output(color, which, output)
            if stderr:
                self._log_output(color, which, stderr)

        return process.stdout, process.stderr, process.returncode

    def set_apply_command_attributes(self):
        """
        Set the acceptable apply command parameters
        """
        if not hasattr(self, "apply_command"):
            raise ValueError("object does not have `apply_command` attribute!")

        # If we're running a Docker image on our EC2 instance, then update the arguments
        if isinstance(self.image, DockerImage):
            self.apply_command.set_accepted_apply_optargs(['-p', '-u', '-n'])

            # Additional optargs. Note that this function is called AFTER we push our
            # image to our registry, so our registry configuration should have all the
            # information we need.
            registry, username, password = self.image.registry.get_login_info()
            additional_optargs = {
                '-a': username,
                '-z': password,
                '-r': registry,
                '-i': f"{self.image.image_name}:{self.image.image_version}"
            }
            self.apply_command.set_additional_optargs(additional_optargs)

    def set_run_command_attributes(self):
        """
        Set the acceptable run command parameters
        """
        if not hasattr(self, "run_command"):
            raise ValueError("object does not have `run_command` attribute!")

        # If we're running a Docker image on our EC2 instance, then update the arguments
        if isinstance(self.image, DockerImage):
            self.run_command.set_accepted_apply_optargs(['-p', '-u', '-n', '-f', '-d'])

            # Additional optargs. Note that this function is called AFTER we push our
            # image to our registry, so our registry configuration should have all the
            # information we need.
            registry, username, password = self.image.registry.get_login_info()
            additional_optargs = {
                '-a': username,
                '-z': password,
                '-r': registry,
                '-i': f"{self.image.image_name}:{self.image.image_version}"
            }
            self.run_command.set_additional_optargs(additional_optargs)

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

        # Logging prefix
        log_prefix = f"{nomad.ui.AGENT_EVENT}{self.instance_name}{nomad.ui.AGENT_WHICH_BUILD}{BUILD_DIVIDER.__str__()}{nomad.ui.RESET}|"  # noqa: E501

        # Infra
        instance_type = self.parse_infra_key(self.infra.infra_conf, "instance_type")
        ami_image = self.parse_infra_key(self.infra.infra_conf, "ami_image")
        python_version = self.parse_infra_key(self.infra.infra_conf, "python_version")

        # If the user is using an image, then ignore the Python version
        if self.image is not None:
            if python_version != "":
                logger.info(
                    f"{log_prefix} Ignoring Python version in favor of newly built image"  # noqa
                )

        # requirements.txt path
        requirements_txt_path = Path(
            self.parse_requirements(self.nomad_wkdir, self.agent_conf)
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
            self.nomad_wkdir,
            self.agent_conf,
        )
        project_dir = all_local_paths.pop(0)
        all_local_paths_cli = ",".join(all_local_paths)

        # Create the instance
        data = self.create_instance(
            self.ec2_client,
            self.ec2_resource,
            self.instance_id,
            self.instance_name,
            instance_type,
            ami_image,
        )

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
            _, err, returncode = self.stream_logs(
                cmd, nomad.ui.AGENT_WHICH_BUILD, "build"
            )

            # Log anything from stderr that was printed in the project
            for line in err.readlines():
                logger.info(
                    f"{log_prefix} {line.rstrip()}"  # noqa: E501
                )

            # A return code of 8 indicates that the SSH connection timed out. Try
            # whitelisting the current IP and try again.
            if returncode == 8:
                # For mypy
                if self.security_group_id is None:
                    raise ValueError("`security_group_id` is still None!")
                logger.info(
                    f"{log_prefix} SSH connection timed out...checking security group ingress rules and trying again"  # noqa: E501
                )

                # Add the current IP to the security ingress rules
                added_ip = self.check_ingress_ip(
                    self.ec2_client, self.security_group_id
                )

                # If the current IP address is already whitelisted, then just add
                # 0.0.0.0/0 to the ingress rules.
                if added_ip is None:
                    self.args.whitelist_all = True
                    logger.info(
                        f"{log_prefix} Current IP address already whitelisted...whitelisting 0.0.0.0/0"  # noqa: E501
                    )
                    self.add_ingress_rule(
                        self.ec2_client,
                        self.security_group_id,
                        "0.0.0.0",
                    )

                # Try again
                _, err, returncode = self.stream_logs(
                    cmd, nomad.ui.AGENT_WHICH_BUILD, "build"
                )

            # Otherwise, if the return code is non-zero, then an error occurred. Delete
            # all of the resources so that the user can try again.
            if returncode != 0:
                self.delete()

            # Return the returncode. Return a dictionary in order to avoid confusing
            # this output with the output of an event manager.
            return returncode

        # If we encounter any sort of error, delete the resources first and then raise
        except Exception as e:
            self.delete()
            raise e

    def run(self, overrides={}):
        """
        Run the project using the EC2 agent
        """
        # Full command
        full_cmd = self.entrypoint.build_command()

        # Download files
        download_files = self.agent_conf["download_files"]
        download_files_cmd = []
        for df in download_files:
            download_files_cmd.append(df)

        # Logging styling
        if self.instance_name is None or self.instance_id is None:
            logger.info(
                "Agent data not found! Use `nomad apply` to create your agent"
            )
            return

        # Check the ingress rules
        if self.security_group_id is not None:
            self.check_ingress_ip(self.ec2_client, self.security_group_id)

        # For mypy
        if not isinstance(self.public_dns_name, str):
            raise ValueError("incompatible public DNS name!")

        # The agent data should exist...Build the shell command
        self.run_command = AgentCommand(
            executable='/bin/bash',
            script=self.AGENT_RUN_SCRIPT,
            args={
                '-p': str(self.pem_key_path),
                '-u': 'ec2-user',
                '-n': self.public_dns_name,
                '-d': str(self.nomad_wkdir),
                '-c': full_cmd,
                '-f': download_files_cmd
            }
        )
        self.set_run_command_attributes()

        # Process the command and execute
        cmd = self.run_command.process_cmd()
        out, _, returncode = self.stream_logs(cmd, nomad.ui.AGENT_WHICH_RUN, "run")

        # Log prefix
        log_prefix = f"{nomad.ui.AGENT_EVENT}{self.instance_name}{nomad.ui.AGENT_WHICH_RUN}{RUN_DIVIDER.__str__()}{nomad.ui.RESET}|"  # noqa

        # Log anything from stdout that was printed in the project
        for line in out.readlines():
            logger.info(
                f"{log_prefix} {line.rstrip()}"  # noqa: E501
            )

        # Return the returncode.
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
        if self.instance_name is None:
            logger.info(  # type: ignore
                "Agent data not found! Did you manually delete the ~/.nomad/ec2.json file?"  # noqa: E501
            )
            return

        # Logging styling
        log_prefix = f"{nomad.ui.AGENT_EVENT}{self.instance_name}{nomad.ui.RED}{DELETE_DIVIDER.__str__()}{nomad.ui.RESET}|"  # noqa: E501

        # Key pair
        if self.key_name is None:
            logger.info(
                f"{log_prefix} No agent data found!"
            )
        else:
            log_key_pair = f"{nomad.ui.MAGENTA}{self.key_name}{nomad.ui.RESET}"
            log_key_path = f"{nomad.ui.MAGENTA}{str(self.pem_key_path)}{nomad.ui.RESET}"  # noqa: E501
            logger.info(
                f"{log_prefix} Deleting key-pair {log_key_pair} at {log_key_path}"
            )
            self.ec2_client.delete_key_pair(
                KeyName=self.key_name
            )
            try:
                os.unlink(str(self.pem_key_path))

            # If this file never existed, then pass
            except FileNotFoundError:
                logger.info(
                    f"{log_prefix} Key-pair {log_key_pair} at {log_key_path} doesn't exist!"  # noqa: E501
                )

        # Instance
        if self.instance_id is None:
            logger.info(
                f"{log_prefix} No instance found!"
            )
        else:
            log_instance_id = f"{nomad.ui.MAGENTA}{self.instance_id}{nomad.ui.RESET}"  # noqa: E501
            logger.info(
                f"{log_prefix} Deleting instance {log_instance_id}"
            )
            _ = self.ec2_client.terminate_instances(
                InstanceIds=[self.instance_id]
            )

        # Security group
        if self.security_group_id is None:
            logger.info(
                f"{log_prefix} No security group found! If this is a mistake, then you may need to reset your resource data"  # noqa: E501
            )
        else:
            log_security_group_id = f"{nomad.ui.MAGENTA}{self.security_group_id}{nomad.ui.RESET}"  # noqa: E501
            while True:
                try:
                    self.ec2_client.delete_security_group(
                        GroupId=self.security_group_id
                    )
                    logger.info(
                        f"{log_prefix} Deleting security group {log_security_group_id}"  # noqa: E501
                    )
                    break
                except botocore.exceptions.ClientError as e:
                    if "DependencyViolation" in str(e):
                        logger.info(
                            f"{log_prefix} Encountered `DependencyViolation` when deleting security group {log_security_group_id}...waiting 5 seconds and trying again"  # noqa: E501
                        )
                        time.sleep(5)
                    else:
                        raise e

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
