"""
Integration tests (i.e., full runs on micro EC2 instances).
"""

# Imports
import boto3
import subprocess
from typing import List, Optional
from pathlib import Path
import os

from alto.constants import PYTHON_VERSION, PLATFORM


# Tests
def cli_runner(args: List[str]):
    """
    Invoke the CLI arguments using a subprocess process. This helps us debug our tests.
    """
    proc = subprocess.Popen(
        ["alto"] + args,
        stdin=subprocess.PIPE,
    )
    proc.wait()
    return proc


def key_pair_exists(key_pair_name: str):
    """
    Check if key_pair with `key_pair_name` exists.
    """
    ec2_client = boto3.client("ec2")
    kps = ec2_client.describe_key_pairs()["KeyPairs"]
    for kp in kps:
        if kp["KeyName"] == key_pair_name:
            return True
    return False


def security_group_exists(security_group_name: str):
    ec2_client = boto3.client("ec2")
    sgs = ec2_client.describe_security_groups()["SecurityGroups"]
    for sg in sgs:
        if sg["GroupName"] == security_group_name:
            return True
    return False


def running_instance_exists(instance_name: str):
    """
    Check if instance with `instance_name` exists. Technically, multiple instances with
    the same name can exist. But we use this just for our own tests, so whatever...
    """
    ec2_client = boto3.client("ec2")
    reservations = ec2_client.describe_instances()["Reservations"]
    for res in reservations:
        for inst in res["Instances"]:
            tags = inst["Tags"]
            for _t in tags:
                if _t["Key"] == "Name":
                    if _t["Value"] == instance_name and inst["State"]["Name"] == "running":  # noqa: E501
                        return True
    return False


def _resources_exist(resource_name: str):
    return {
        "key_pair": key_pair_exists(resource_name),
        "security_group": security_group_exists(resource_name),
        "instance": running_instance_exists(resource_name)
    }


def s3_file_exists(s3_uri: str) -> Optional[str]:
    """
    Check if file exists in s3. If it does, return file contents as a string
    """
    s3_uri_split = s3_uri.replace("s3://", "").split("/")
    bucket, key = s3_uri_split[0], "/".join(s3_uri_split[1:])

    # Load the object
    s3_client = boto3.client("s3")
    try:
        s3_response = s3_client.get_object(
            Bucket=bucket,
            Key=key,
        )
        s3_object_body = s3_response.get('Body')

        # Read the data in bytes format and convert it to string
        content_str = s3_object_body.read().decode()

        # Print the file contents as a string
        return content_str

    # S3 Bucket does not exist
    except s3_client.exceptions.NoSuchBucket:
        print('The S3 bucket does not exist.')
        return None

    # Object does not exist in the S3 Bucket
    except s3_client.exceptions.NoSuchKey:
        print('The S3 objects does not exist in the S3 bucket.')
        return None


def delete_s3_file(s3_uri: str) -> None:
    """
    Delete file in S3, if it exists
    """
    # If the object doesn't exist, just return
    s3_contents = s3_file_exists(s3_uri)
    if s3_contents is None:
        return

    # Otherwise, delete the object
    s3_uri_split = s3_uri.replace("s3://", "").split("/")
    bucket, key = s3_uri_split[0], "/".join(s3_uri_split[1:])
    s3_client = boto3.client("s3")
    s3_client.delete_object(
        Bucket=bucket,
        Key=key
    )
    return


def ecr_repository_exists(repository_name):
    """
    Check if `repository_name` exists in ECR
    """
    try:
        ecr_client = boto3.client('ecr')
        ecr_client.describe_repositories(repositoryNames=[repository_name])
        return True

    # ECR repository does not exist
    except ecr_client.exceptions.RepositoryNotFoundException:
        return False

    # Some other error
    except Exception as e:
        print(f"An error occurred: {e}")
        return False


def delete_ecr_repository(repository_name):
    """
    Delete `repository_name` if it exists in ECR
    """
    try:
        ecr_client = boto3.client('ecr')
        ecr_client.delete_repository(repositoryName=repository_name, force=True)
        return True

    # Repository doesn't exist
    except ecr_client.exceptions.RepositoryNotFoundException:
        return False

    # Some other error
    except Exception as e:
        print(f"An error occurred: {e}")
        return False


def _apply_integration_test(
    test_path: Path,
    conf_fname: str = "alto.yml",
    docker: bool = False,
):
    os.chdir(test_path)
    proc = cli_runner(["apply", "-f", conf_fname])

    # Check if EC2 resources exist
    resource_name = f"{test_path.name.replace('_', '-')}-my_cloud_agent-{PYTHON_VERSION}"  # noqa: E501
    resources = _resources_exist(resource_name)
    assert resources["key_pair"]
    assert resources["security_group"]
    assert resources["instance"]
    assert proc.returncode == 0

    # Check if the repository exists
    if docker:
        assert ecr_repository_exists(resource_name)


def _run_integration_test(
    fname_name: str,
    run_args: List[str],
):
    # Delete file in S3, if it exists
    output_key = f"{PLATFORM}_{PYTHON_VERSION}_{fname_name}".replace(".", "")
    file_s3_uri = f"s3://alto-dev-tests/tests/{output_key}.txt"
    delete_s3_file(file_s3_uri)

    # Run
    proc = cli_runner(run_args)
    assert proc.returncode == 0
    test_output = s3_file_exists(file_s3_uri)
    expected_output = f"Hello world from our `{PLATFORM}.{PYTHON_VERSION}.{fname_name}` test case!"  # noqa: E501
    assert test_output == expected_output
    delete_s3_file(file_s3_uri)


def _build_integration_test(
    test_path: Path,
    fname_name: str,
    conf_fname: str = "alto.yml",
    image: bool = False
):
    os.chdir(test_path)

    # Delete file in S3, if it exists
    output_key = f"{PLATFORM}_{PYTHON_VERSION}_{fname_name}".replace(".", "")
    file_s3_uri = f"s3://alto-dev-tests/tests/{output_key}.txt"
    delete_s3_file(file_s3_uri)

    # Invoke the `build` command
    proc = cli_runner(["build", "-f", conf_fname, "--no-delete-success", "--no-delete-failure"])  # noqa: E501

    # Check if EC2 resources exist
    resource_name = f"{test_path.name}-my_cloud_agent-{PYTHON_VERSION}"
    resources = _resources_exist(resource_name)
    assert resources["key_pair"]
    assert resources["security_group"]
    assert resources["instance"]
    assert proc.returncode == 0

    # Check output
    test_output = s3_file_exists(file_s3_uri)
    expected_output = f"Hello world from our `{PLATFORM}.{PYTHON_VERSION}.{fname_name}` test case!"  # noqa: E501
    assert test_output == expected_output

    # Check if the Docker image exists
    if image:
        ecr_repository_exists(f"{test_path.name}-my_cloud_agent-{PYTHON_VERSION}")
