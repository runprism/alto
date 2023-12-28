"""
Example function for test case.
"""

# Imports
import os
import boto3


# Functions
def write_txt_file(
    platform: str,
    python_version: str,
    output_name: str = "test_function"
):
    """
    Write a file to S3. This allows us to test whether our code actually works.
    """
    session = boto3.Session(
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
    )
    s3 = session.resource('s3')

    # Output key
    output_key = f"{platform}_{python_version}_{output_name}".replace(".", "")
    s3_object = s3.Object('nomad-dev-tests', f'tests/{output_key}.txt')
    txt_data = "Hello world from our `{platform}.{python_version}.{output_name}` test case!".format(  # noqa
        platform=platform,
        python_version=python_version,
        output_name=output_name,
    ).encode()
    s3_object.put(Body=txt_data)
