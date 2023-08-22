"""
Example function for test case.
"""

# Imports
import argparse
import os
import boto3


# Functions
def write_txt_file(output_name: str):
    """
    Write a file to S3. This allows us to test whether our code actually works.
    """
    session = boto3.Session(
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
    )
    s3 = session.resource('s3')
    s3_object = s3.Object('nomad-dev-tests', f'tests/{output_name}.txt')
    txt_data = "Hello world from our `{output_name}` test case!".format(output_name=output_name).encode()  # noqa
    s3_object.put(Body=txt_data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-name", type=str, required=True)
    args = parser.parse_args()
    output_name = args.output_name
    write_txt_file(output_name)
    print("Done!")
