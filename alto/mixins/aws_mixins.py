"""
Generic AWS functions
"""

import boto3
from enum import Enum
import time
from typing import Any, Dict, Optional


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


class sshResource(str, Enum):
    KEY_PAIR = "key_pair"
    SECURITY_GROUP_ID = "security_group_id"
    INSTANCE_ID = "instance_id"
    PUBLIC_DNS_NAME = "public_dns_name"
    STATE = "state"


class sshFile(str, Enum):
    PEM_KEY_PATH = "pem_key_path"


class AwsMixin:

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
