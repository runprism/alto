"""
Generic AWS functions
"""

import boto3
import botocore
from enum import Enum
import os
from pathlib import Path
import time
import stat
from typing import Any, Optional, TypedDict

# Type hints
from mypy_boto3_ec2.client import EC2Client
from mypy_boto3_ec2.type_defs import GroupIdentifierTypeDef


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


class ec2Resource(str, Enum):
    # For the SSH protocol
    KEY_PAIR = "key_pair"
    SECURITY_GROUP_ID = "security_group_id"
    INSTANCE_ID = "instance_id"
    PUBLIC_DNS_NAME = "public_dns_name"
    STATE = "state"

    # For the SSM protocol
    ROLE_ARN = "role_arn"
    INSTANCE_PROFILE_ARN = "instance_profile_arn"


class ec2File(str, Enum):
    PEM_KEY_PATH = "pem_key_path"


class InstanceData(TypedDict):
    instance_id: str
    public_dns_name: str
    key_name: Optional[str]
    security_groups: list[GroupIdentifierTypeDef]
    state: State


class AwsMixin:

    def create_key_pair(self,
        ec2_client: EC2Client,
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

    def restart_instance(self,
        ec2_client,
        state: Optional[State],
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
                if results is None:
                    raise ValueError(
                        "`start_stopped_instance` called on a nonexistent instance!"  # noqa: E501
                    )
                state = results["state"]
                time.sleep(1)
            return state

        # If the instance is stopping / stopped, then restart it and wait until the
        # state is `running`.
        elif state in [State.STOPPED, State.STOPPING]:
            ec2_client.start_instances(InstanceIds=instance_id)
            while state != State.RUNNING:
                results = self.check_instance_data(instance_id)
                if results is None:
                    raise ValueError(
                        "`start_stopped_instance` called on a nonexistent instance!"  # noqa: E501
                    )
                time.sleep(1)
                state = results["state"]
            return state

        # If nothing's been returned, then the instance should already be running
        return state

    def check_instance_data(self,
        instance_id: Optional[str]
    ) -> Optional[InstanceData]:
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
        results: Optional[InstanceData] = None

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
                        results = {
                            "instance_id": instance_id,
                            "public_dns_name": inst["PublicDnsName"],
                            "key_name": inst.get("KeyName", None),
                            "security_groups": inst["SecurityGroups"],
                            "state": State(inst["State"]["Name"]),
                        }

        # Return
        return results

    def delete_key_pair_and_unlink_path(self,
        ec2_client: EC2Client,
        key_name: str,
        pem_key_path: Path
    ):
        ec2_client.delete_key_pair(
            KeyName=key_name
        )
        os.unlink(str(pem_key_path))

    def detach_policies_from_role(self,
        iam_client: Any,
        iam_role_name: str
    ):
        attached_policies = iam_client.list_attached_role_policies(
            RoleName=iam_role_name
        )['AttachedPolicies']
        for policy in attached_policies:
            iam_client.detach_role_policy(
                RoleName=iam_role_name,
                PolicyArn=policy['PolicyArn']
            )

    def detach_role_from_instance_profile(self,
        iam_client: Any,
        iam_role_name: str,
    ):
        instance_profiles = iam_client.list_instance_profiles_for_role(
            RoleName=iam_role_name
        )['InstanceProfiles']
        for ip in instance_profiles:
            iam_client.remove_role_from_instance_profile(
                InstanceProfileName=ip['InstanceProfileName'],
                RoleName=iam_role_name
            )

    def detach_and_delete_iam_role(self,
        iam_client: Any,
        iam_role_name: str
    ):
        self.detach_policies_from_role(iam_client, iam_role_name)
        self.detach_role_from_instance_profile(iam_client, iam_role_name)
        iam_client.delete_role(RoleName=iam_role_name)

    def resolve_dependency_violation_and_delete_security_group(self,
        ec2_client: EC2Client,
        security_group_id: str,
    ):
        while True:
            try:
                ec2_client.delete_security_group(
                    GroupId=security_group_id
                )
                break
            except botocore.exceptions.ClientError as e:
                if "DependencyViolation" in str(e):
                    time.sleep(5)
                else:
                    raise e
