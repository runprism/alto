"""
Protocols for accessing virtual machines. Currently, only needed for EC2 instances.
"""

# Imports
import boto3
from enum import Enum
from botocore.exceptions import ClientError
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple

# Alto imports
from alto.constants import EC2_INSTANCE_TYPE
from alto.mixins.aws_mixins import (
    State,
    ec2Resource,
)
from alto.agents.ec2.protocols.base import Protocol
from alto.entrypoints import BaseEntrypoint
from alto.images import BaseImage
from alto.images.docker_image import Docker
import alto.ui

# Type hints
from mypy_boto3_ec2.client import EC2Client


# Classes
class CommandStatus(str, Enum):
    SUCCESS = 'Success'
    CANCELLED = 'Cancelled'
    FAILED = 'Failed'
    TIMEDOUT = 'TimedOut'


class SSMProtocol(Protocol):

    def create_cloudwatch_log_group_and_stream(self,
        logs_client: Any,
        log_group_name: str,
        log_stream_name: Optional[str] = None,
    ):
        # Check if the log group already exists. If it doesn't don't do anything
        try:
            logs_client.create_log_group(
                logGroupName=log_group_name
            )
        except Exception as e:
            if "already exists" not in str(e):
                raise e

        # For the log stream — if it already exists, then delete and re-create. Each log
        # stream should be associated with it's own `alto` run.
        if log_stream_name is not None:
            try:
                logs_client.create_log_stream(
                    logGroupName=log_group_name,
                    logStreamName=log_stream_name,
                )
            except Exception as e:
                if "already exists" not in str(e):
                    raise e

        return log_group_name, log_stream_name

    def attach_policies_to_role(self,
        iam_client: Any,
        policy_names: List[str],
        iam_role_name: str,
    ) -> None:
        """
        Attach `policy_name` to `iam_role_name`. We use this to make sure our EC2
        instance can connect to SSM.
        args:
            iam_client: IAM client
            policy names: list of policy names to attach
            iam_role_name: IAM role to which to attach policies
        returns:
            None
        """
        for _policy in policy_names:
            policy_arn = f"arn:aws:iam::aws:policy/{_policy}"
            iam_client.attach_role_policy(
                RoleName=iam_role_name,
                PolicyArn=policy_arn
            )
        return None

    def create_instance_profile(self,
        iam_client: Any,
        iam_role_name: str,
        iam_instance_profile_name: str,
        instance_name: str,
    ) -> Tuple[str, str]:
        """
        Create instance profile. We use this to make sure our EC2 instance can connect
        to SSM.

        args:
            iam_client: IAM client
            iam_role_name: IAM role to create
            iam_instance_profile_name: IAM instance profile to create
            instance_name: instance name
        returns:
            IAM instance profile ARN
        """
        # Create IAM Role for SSM
        role_policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        try:
            role_response = iam_client.create_role(
                RoleName=iam_role_name,
                AssumeRolePolicyDocument=json.dumps(role_policy_document)
            )
            role_arn: str = str(role_response["Role"]["Arn"])
        except Exception as e:
            if "already exists" in str(e):
                roles = iam_client.list_roles()
                for _r in roles["Roles"]:
                    if _r["RoleName"] == iam_role_name:
                        role_arn = _r["Arn"]
            else:
                raise e

        # Update resource data
        self.resource_data = {
            "resources": {ec2Resource.ROLE_ARN.value: role_arn},
        }

        # Log
        role_arn_log = f"{alto.ui.MAGENTA}{role_arn}{alto.ui.RESET}"
        iam_role_name_log = f"{alto.ui.MAGENTA}{iam_role_name}{alto.ui.RESET}"
        self.output_mgr.log_output(
            agent_img_name=instance_name,
            stage=alto.ui.StageEnum.AGENT_BUILD,
            level="info",
            msg=f"Created IAM Role {iam_role_name_log} with ARN {role_arn_log}",
        )

        # Attach SSM policies to the role
        self.attach_policies_to_role(
            iam_client,
            [
                "AmazonSSMFullAccess",
                "AmazonSSMManagedEC2InstanceDefaultPolicy",
                "AmazonS3FullAccess",
            ],
            iam_role_name
        )

        # Attach IAM Role to EC2 instance
        add_role: bool = True
        try:
            iam_ip_resp = iam_client.create_instance_profile(
                InstanceProfileName=iam_instance_profile_name
            )["InstanceProfile"]

        # If the profile already exists, then grab it
        except Exception as e:
            if "already exists" in str(e):
                instance_profiles = iam_client.list_instance_profiles()
                for _ip in instance_profiles["InstanceProfiles"]:
                    if _ip["InstanceProfileName"] == iam_instance_profile_name:
                        iam_ip_resp = _ip

                        # See if we need to add the role
                        for _role in _ip["Roles"]:
                            if _role["RoleName"] == iam_role_name:
                                add_role = False
            else:
                raise e

        # Add role to instance profile if it isn't already attached
        if add_role:
            iam_client.add_role_to_instance_profile(
                InstanceProfileName=iam_instance_profile_name,
                RoleName=iam_role_name
            )

        # Log
        instance_profile_name_log = f"{alto.ui.MAGENTA}{iam_instance_profile_name}{alto.ui.RESET}"  # noqa: E501
        self.output_mgr.log_output(
            agent_img_name=instance_name,
            stage=alto.ui.StageEnum.AGENT_BUILD,
            level="info",
            msg=f"Attached IAM role {iam_role_name_log} to instance profile {instance_profile_name_log}"  # noqa: E501
        )

        # Update the resource data
        self.resource_data["resources"].update(
            {ec2Resource.INSTANCE_PROFILE_ARN.value: iam_ip_resp["Arn"]},
        )
        return role_arn, str(iam_ip_resp["Arn"])

    def create_resources(self,
        current_data: Dict[str, Any],
        ec2_client: EC2Client,
        instance_name: str,
        instance_type: EC2_INSTANCE_TYPE,
        ami_image: str,
    ):
        current_resources = current_data.get("resources", {})

        # Create instance profile
        iam_role_name = f"{instance_name}-role"
        iam_instance_profile_name = f"{instance_name}-profile"
        self.output_mgr.step_starting(
            "Creating IAM instance profile",
            is_substep=True
        )
        if current_resources.get(ec2Resource.INSTANCE_PROFILE_ARN.value, None) is None:
            iam_client = boto3.client("iam")
            _, instance_profile_arn = self.create_instance_profile(
                iam_client,
                iam_role_name,
                iam_instance_profile_name,
                instance_name
            )
            self.output_mgr.step_completed(
                "Created IAM instance profile!",
                is_substep=True
            )
        else:
            role_arn = current_resources[ec2Resource.ROLE_ARN.value]
            instance_profile_arn = current_resources[ec2Resource.INSTANCE_PROFILE_ARN.value]  # noqa: E501
            log_instance_profile_name = f"{alto.ui.MAGENTA}{iam_instance_profile_name}{alto.ui.RESET}"  # noqa: E501
            log_instance_profile_arn = f"{alto.ui.MAGENTA}{instance_profile_arn}{alto.ui.RESET}"  # noqa: E501
            self.output_mgr.log_output(
                agent_img_name=instance_name,
                stage=alto.ui.StageEnum.AGENT_BUILD,
                level="info",
                msg=f"Using existing IAM instance profile {log_instance_profile_name} with ARN {log_instance_profile_arn}",  # noqa
                renderable_type="Using existing IAM instance profile",
                is_step_completion=True,
                is_substep=True
            )
            self.resource_data = {
                "resources": {
                    ec2Resource.ROLE_ARN.value: role_arn,
                    ec2Resource.INSTANCE_PROFILE_ARN.value: instance_profile_arn
                },
            }

        # Instance
        self.output_mgr.step_starting(
            "Creating EC2 instance",
            is_substep=True
        )
        log_instance_id_template = f"{alto.ui.MAGENTA}{{instance_id}}{alto.ui.RESET}"  # noqa: E501
        if current_resources.get(ec2Resource.INSTANCE_ID.value, None) is None:
            resp = ec2_client.run_instances(
                InstanceType=instance_type,
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
            )
            instance = resp["Instances"][0]
            instance_id = instance["InstanceId"]

            # Associate instance profile to client
            while True:
                try:
                    ec2_client.associate_iam_instance_profile(
                        IamInstanceProfile={'Arn': instance_profile_arn},
                        InstanceId=instance_id,
                    )
                    break
                except ClientError as err:
                    if err.response['Error']['Code'] == 'InvalidParameterValue':
                        self.output_mgr.log_output(
                            agent_img_name=instance_name,
                            stage=alto.ui.StageEnum.AGENT_BUILD,
                            level="info",
                            msg="The EC2 client did not find the profile yet...wait 5 seconds and then try again",  # noqa: E501
                        )
                        time.sleep(5)

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
            instance_id = current_resources[ec2Resource.INSTANCE_ID.value]
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
        instance_data = self.check_instance_data(instance_id)
        if instance_data is None:
            raise ValueError(
                f"Failed to create instance `{instance_id}`"
            )

        # If the instance exists and is running, then just return
        if len(instance_data.keys()) > 0 and instance_data["state"] in [State.PENDING, State.RUNNING]:  # noqa: E501
            while instance_data["state"] == State.PENDING:

                # Log
                log_pending_status = f"{alto.ui.YELLOW}pending{alto.ui.RESET}"  # noqa: E501
                self.output_mgr.log_output(
                    agent_img_name=instance_name,
                    stage=alto.ui.StageEnum.AGENT_BUILD,
                    level="info",
                    msg=f"Instance {log_instance_id_template.format(instance_id=instance_id)} is {log_pending_status}... checking again in 5 seconds"  # noqa: E501
                )
                instance_data = self.check_instance_data(instance_id)
                if instance_data is None:
                    raise ValueError(
                        f"Failed to create instance `{instance_id}`"
                    )

        # If the state exiss but has stopped, then restart it
        elif len(instance_data.keys()) > 0 and instance_data["state"] in [State.STOPPED, State.STOPPING]:  # noqa: E501
            self.restart_instance(
                ec2_client,
                instance_data["state"],
                instance_data["instance_id"]
            )

        self.resource_data["resources"].update(
            {
                ec2Resource.INSTANCE_ID.value: instance_id,
                ec2Resource.PUBLIC_DNS_NAME.value: instance_data["public_dns_name"],
                ec2Resource.STATE.value: instance_data["state"]
            }
        )

        return self.resource_data

    def upload_file_or_directory_to_s3(self,
        local_file_dir: Path,
        bucket_name: str,
        instance_name: str,
    ) -> Tuple[List[str], List[str]]:
        """
        Upload files and/or directories to S3. We need to do this in order to copy our
        files onto our SSM-managed EC2 instance.

        args:
            local_file_dir: local file or directory to copy
            bucket_name: bucket in which to upload the file
            instance_name: instance name
        returns:
            None
        """
        s3_paths: List[str] = []
        full_paths: List[str] = []

        # Create the S3 bucket if it doesn't exist
        s3_client = boto3.client("s3")
        resp = s3_client.list_buckets()
        bucket_exists = False
        for _bucket in resp["Buckets"]:
            if _bucket["Name"] == bucket_name:
                bucket_exists = True
        if not bucket_exists:
            s3_client.create_bucket(Bucket=bucket_name)

        # Now, copy the local file onto S3
        if Path(local_file_dir).is_file():
            _dir, _fname = os.path.split(Path(local_file_dir))

            # Truncated path (i.e., S3 path for this file) and full path (i.e., path
            # this file will have in our instance)
            s3_path = f"{instance_name}/{_fname}"
            full_path = f"{_dir[1:]}/{_fname}"

            # Upload files and keep track of paths
            s3_client.upload_file(
                str(local_file_dir),
                bucket_name,
                s3_path
            )
            s3_paths.append(s3_path)
            full_paths.append(full_path)
        else:
            for root, _, files in os.walk(Path(local_file_dir)):
                for _file in files:
                    # Truncated path (i.e., S3 path for this file) and full path (i.e.,
                    # path this file will have in our instance)
                    dirname = Path(f"{root}/{_file}").parent.name
                    s3_path = f"{instance_name}/{dirname}/{_file}"
                    full_path = f"{root[1:]}/{_file}"

                    s3_client.upload_file(
                        os.path.join(root, _file),
                        bucket_name,
                        s3_path
                    )
                    s3_paths.append(s3_path)
                    full_paths.append(full_path)

        return s3_paths, full_paths

    def _process_log_msg(self,
        msg: str
    ) -> str:
        """
        Do some light processing of logs
        """
        if "download: s3://" in msg:
            return "Mounted " + msg.split(" to ")[-1]
        return msg

    def stream_logs(self,
        instance_name: str,
        stage: alto.ui.StageEnum,
        logs_client: Any,
        log_group_name: str,
        log_stream_name: str
    ) -> None:
        """
        Stream the logs from the AWS CloudWatch log group / log stream

        args:
            instance_name: name of EC2 instance for which we are streaming logs
            stage: Agent stage
            logs_client: CloudWatch Logs client
            log_group_name: log group name
            log_stream_name: log stream name containing log events
        returns:
            None
        """

        # Get the initial event
        while True:
            try:
                log_events_resp = logs_client.get_log_events(
                    logGroupName=log_group_name,
                    logStreamName=log_stream_name,
                )

                # Log the current event
                for ev in log_events_resp["events"]:
                    msg = ev["message"]
                    for line in re.split(r'[\n\r]', msg):
                        self.output_mgr.log_output(
                            agent_img_name=instance_name,
                            stage=stage,
                            level="info",
                            msg=self._process_log_msg(line),
                            renderable_type=f"[dodger_blue2]{msg}[/dodger_blue2]" if stage == alto.ui.StageEnum.AGENT_RUN else None,  # noqa
                            is_step_completion=False,
                        )
                break
            except Exception as e:
                if "ResourceNotFoundException" in str(e):
                    self.output_mgr.log_output(
                        agent_img_name=instance_name,
                        stage=stage,
                        level="info",
                        msg="Log stream doesn't exist yet...wait 5 seconds and try again"  # noqa: E501
                    )
                    time.sleep(5)
                else:
                    raise e

        # Keep retrieving and processing new log events
        while 'nextForwardToken' in log_events_resp:
            curr_token = log_events_resp["nextForwardToken"]
            log_events_resp = logs_client.get_log_events(
                logGroupName=log_group_name,
                logStreamName=log_stream_name,
                nextToken=curr_token
            )
            next_token = log_events_resp["nextForwardToken"]
            if curr_token == next_token:
                break
            for ev in log_events_resp["events"]:
                msg = ev["message"]
                for line in re.split(r'[\n\r]', msg):
                    self.output_mgr.log_output(
                        agent_img_name=instance_name,
                        stage=stage,
                        level="info",
                        msg=self._process_log_msg(line),
                        renderable_type=f"[dodger_blue2]{msg}[/dodger_blue2]" if stage == alto.ui.StageEnum.AGENT_RUN else None,  # noqa
                        is_step_completion=False,
                    )

            # Add a delay to avoid rate limiting
            time.sleep(1)
        return None

    def send_command_and_stream_logs(self,
        ssm_client: Any,
        stage: alto.ui.StageEnum,
        cmd: List[str],
        instance_name: str,
        instance_id: str,
    ) -> CommandStatus:
        # Initialize our status variable
        status = None

        # Create a new log group for the command
        logs_client = boto3.client("logs")
        self.create_cloudwatch_log_group_and_stream(
            logs_client,
            log_group_name=instance_name
        )

        # Because of the race condition, retry sending the command until it's
        # successfully sent.
        while True:
            try:
                resp = ssm_client.send_command(
                    InstanceIds=[instance_id],
                    DocumentName="AWS-RunShellScript",
                    Parameters={'commands': cmd},
                    CloudWatchOutputConfig={
                        'CloudWatchLogGroupName': instance_name,
                        'CloudWatchOutputEnabled': True
                    },
                )
                command_id = resp["Command"]["CommandId"]
                status = resp["Command"]["Status"]

                log_command_id = f"{alto.ui.MAGENTA}{command_id}{alto.ui.RESET}"
                self.output_mgr.log_output(
                    agent_img_name=instance_name,
                    stage=stage,
                    level="info",
                    msg=f"Sent command with ID {log_command_id} to SSM client"
                )

                # Construct the log stream name
                stdout_stream = f"{command_id}/{instance_id}/aws-runShellScript/stdout"
                stderr_stream = f"{command_id}/{instance_id}/aws-runShellScript/stdout"

                # Wait two seconds to make sure the command was sent
                time.sleep(2)

                # If the command has already succeeded / failed, stream the logs
                self.stream_logs(
                    instance_name,
                    stage,
                    logs_client,
                    instance_name,
                    stdout_stream,
                )

                # Otherwise, stream the logs continuously
                while status not in [s.value for s in CommandStatus]:
                    status = ssm_client.get_command_invocation(
                        CommandId=command_id,
                        InstanceId=instance_id,
                    )["Status"]

                # If the status failed, then stream the stderr stream
                if status == CommandStatus.FAILED.value:
                    self.stream_logs(
                        instance_name,
                        stage,
                        logs_client,
                        instance_name,
                        stderr_stream
                    )

                break

            except Exception as e:
                if "InvalidInstanceId" in str(e):
                    self.output_mgr.log_output(
                        agent_img_name=instance_name,
                        stage=stage,
                        level="info",
                        msg="SSM client did not receive command...wait 5 seconds and try again"  # noqa: E501
                    )
                    time.sleep(5)
                else:
                    raise

        if status is None:
            return CommandStatus.FAILED
        else:
            return CommandStatus[status.upper()]

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
            current_data: current EC2 resources from ~/.alto/ec2.json
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
            return code for agent's command
        """
        # Project name and directory
        project_dir = local_mounts[0]
        project_name = Path(project_dir).name
        bucket = "alto-ssm-mounts"

        # SSM client
        ssm_client = boto3.client('ssm')
        instance_id = current_data["resources"].get(
            ec2Resource.INSTANCE_ID.value,
            None
        )

        # All command components
        docker_cmds: List[str] = []
        virtual_environments_cmds: List[str] = []
        requirements_txt_cmds: List[str] = []
        cp_cmds: List[str] = []
        env_var_cmds: List[str] = []

        # If we're using an image, all of our agent's data (e.g., requirements,
        # dependencies, mounts, etc.) will stored on the image.
        if image is not None and isinstance(image, Docker):
            docker_cmds = [
                f"docker --version &> /dev/null",                             # noqa: F541, E501
                f"exit_code=$?",                                              # noqa: F541, E501
                f"if [ ! $exit_code -eq 0 ]; then",                           # noqa: F541, E501
                f'    echo "Docker is not installed. Installing Docker..."',  # noqa: F541, E501
                f"    sudo yum update -y",                                    # noqa: F541, E501
                f"    sudo yum install -y docker",                            # noqa: F541, E501
                f"    sudo service docker start",                             # noqa: F541, E501
                f"    sudo usermod -a -G docker {ec2_user}",                  # noqa: F541, E501
                f'    echo "Docker has been installed."',                     # noqa: F541, E501
                f"else",                                                      # noqa: F541, E501
                f'    echo "Docker is already installed."',                   # noqa: F541, E501
                f"fi",                                                        # noqa: F541, E501
            ]

            # Log into to Docker and pull the image
            registry, username, password = image.registry.get_login_info()
            repository = registry.replace("https://", "")
            image_name = f"{image.image_name}:{image.image_version}"
            docker_cmds.extend([
                f"docker login --username {username} --password {password} {registry}",  # noqa
                f"docker pull {repository}/{image_name}"
            ])

        # Otherwise, we need to build commands for virtual environments, dependencies,
        # and mounts.
        else:
            # Skip Python version, for now...
            python_cli = "3"

            # Create virtual environment
            virtual_environments_cmds = [
                f"if [ -d /home/ssm-user/.venv/{project_name} ]; then",                 # noqa: F541, E501
                f"    source /home/ssm-user/.venv/{project_name}/bin/activate",         # noqa: F541, E501
                f"else",                                                                # noqa: F541, E501
                f"    cd ~",                                                            # noqa: F541, E501
                f"    python{python_cli} -m venv /home/ssm-user/.venv/{project_name}",  # noqa: F541, E501
                f"    source /home/ssm-user/.venv/{project_name}/bin/activate",         # noqa: F541, E501
                f"    pip install --upgrade pip",                                       # noqa: F541, E501
                f"fi"                                                                   # noqa: F541, E501
            ]

            # Copy the requirements.txt file. Most often, this will be in the user's
            # project directory.
            requirements_txt_cmds = []
            if requirements_txt_str != "":
                _reqs_s3, _ = self.upload_file_or_directory_to_s3(
                    Path(requirements_txt_str),
                    bucket,
                    instance_name
                )
                reqs_s3_path = _reqs_s3[0]
                requirements_txt_cmds.append(
                    f"aws s3 cp s3://{bucket}/{reqs_s3_path} /home/ssm-user/requirements.txt"    # noqa: E501
                )
                requirements_txt_cmds.append("cd /home/ssm-user")
                requirements_txt_cmds.append("pip install -r requirements.txt")

            # Construct copy commandsusing local mounts — we need to move this to S3 so
            # that we can copy these files into our SSM-managed EC2 instance.
            s3_paths: List[str] = []
            full_paths: List[str] = []
            for _lm in local_mounts:
                _s3, _full = self.upload_file_or_directory_to_s3(
                    Path(_lm),
                    bucket,
                    instance_name
                )
                s3_paths.extend(_s3)
                full_paths.extend(_full)
            for _s3p, _fullp in zip(s3_paths, full_paths):
                cp_cmds.append(
                    f"aws s3 cp s3://{bucket}/{_s3p} /home/ssm-user/{_fullp}"
                )

            # Environment variable -- we'll need to do this *every* time we run a
            # command in SSM, since these keys are forgotten after each session. Maybe
            # in the future we can use the parameter store?
            for key, value in env_vars.items():
                cmds = [
                    f"export {key}={value}",
                    f'echo "Updated environment variable {key}={value}"'
                ]
                env_var_cmds.extend(cmds)

        # All commands
        all_cmds = docker_cmds + virtual_environments_cmds + requirements_txt_cmds + cp_cmds + post_build_commands + env_var_cmds  # noqa: E501

        # Because of the race condition, retry sending the command until it's
        # successfully sent.
        status = self.send_command_and_stream_logs(
            ssm_client,
            alto.ui.StageEnum.AGENT_BUILD,
            all_cmds,
            instance_name,
            instance_id
        )
        if status != CommandStatus.SUCCESS:
            return 1

        return 0

    def run_entrypoint_on_instance(self,
        current_data: Dict[str, Any],
        ec2_client: EC2Client,
        alto_wkdir: Path,
        image: Optional[BaseImage],
        instance_name: str,
        entrypoint: BaseEntrypoint,
        download_files: List[str],
    ):
        # Instance ID
        instance_id = current_data["resources"].get(
            ec2Resource.INSTANCE_ID.value, None
        )

        # Logging styling
        if instance_id is None:
            self.output_mgr.log_output(  # type: ignore
                agent_img_name=instance_name,
                stage=alto.ui.StageEnum.AGENT_RUN,
                level="error",
                msg="Agent data not found! Use `alto apply` to create your agent",
            )
            return 1

        # Command components
        docker_cmds: List[str] = []
        env_var_cmds: List[str] = []
        entrypoint_cmd: List[str] = []

        if image is not None and isinstance(image, Docker):
            registry, _, _ = image.registry.get_login_info()
            repository = registry.replace("https://", "")
            image_name = f"{image.image_name}:{image.image_version}"
            docker_cmds.extend([
                f'CONTAINERID=$(docker run -d {repository}/{image_name})',  # noqa: F541, E501
                f'if [ -n "$CONTAINERID" ]; then',                          # noqa: F541, E501
                f'    echo "Streaming logs for container $CONTAINERID"',    # noqa: F541, E501
                f'    docker logs -f $CONTAINERID',                         # noqa: F541, E501
                f'else',                                                    # noqa: F541, E501
                f'    echo "Failed to start the container."',               # noqa: F541, E501
                f'fi'                                                       # noqa: F541, E501
            ])
        else:
            # We need to re-define our environment variables prior to running our
            # command
            env_vars: Dict[str, str] = {}
            if "env" in self.agent_conf.keys():
                env_vars = self.agent_conf["env"]
            for key, value in env_vars.items():
                env_var_cmds.append(f"export {key}={value}")

            # Full command
            entrypoint_cmd = [entrypoint.build_command()]

        # Download files
        # ignore for now...

        all_cmds = docker_cmds + env_var_cmds + entrypoint_cmd
        ssm_client = boto3.client("ssm")
        status = self.send_command_and_stream_logs(
            ssm_client,
            alto.ui.StageEnum.AGENT_RUN,
            all_cmds,
            instance_name,
            instance_id
        )
        if status != CommandStatus.SUCCESS:
            return 1

        return 0
