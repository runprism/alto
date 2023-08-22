"""
Example function for test case.
"""

# Imports
import os
import boto3


# Functions
def write_txt_file():
    """
    Write a file to S3. This allows us to test whether our code actually works.
    """
    session = boto3.Session(
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
    )
    s3 = session.resource('s3')
    s3_object = s3.Object('nomad-dev-tests', 'tests/test_function.txt')
    txt_data = b"Hello world from our `test_function` test case!"
    s3_object.put(Body=txt_data)
    print("Done!")
