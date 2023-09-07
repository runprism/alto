"""
Example function for test case.
"""

# Imports
import argparse
import os
import boto3


# Functions
def write_txt_file(
    python_version: str,
    platform: str,
    output_name: str
):
    """
    Write a file to S3. This allows us to test whether our code actually works.
    """
    session = boto3.Session(
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
    )
    s3 = session.resource('s3')
    s3_object = s3.Object('nomad-dev-tests', f'tests/{output_name}.txt')
    txt_data = "Hello world from our `{platform}.{python_version}.{output_name}` test case!".format(  # noqa
        platform=platform,
        python_version=python_version,
        output_name=output_name
    ).encode()
    s3_object.put(Body=txt_data)


if __name__ == "__main__":
    # Parser
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-version", type=str, required=True)
    parser.add_argument("--platform", type=str, required=True)
    parser.add_argument("--output-name", type=str, required=True)

    # Parse args
    args = parser.parse_args()
    python_version = args.python_version
    platform = args.platform
    output_name = args.output_name

    # Write file
    write_txt_file(python_version, platform, output_name)
    print("Done!")
