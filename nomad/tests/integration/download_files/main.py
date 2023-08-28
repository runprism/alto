"""
Example function for test case.
"""

# Imports
import argparse
from pathlib import Path


# Functions
def write_txt_file(output_name: str):
    """
    Write a file to S3. This allows us to test whether our code actually works.
    """
    txt_data = "Hello world from our `{output_name}` test case!".format(
        output_name=output_name
    )
    with open(Path(__file__).parent / 'download_files.txt', 'w') as f:
        f.write(txt_data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-name", type=str, required=True)
    args = parser.parse_args()
    output_name = args.output_name
    write_txt_file(output_name)
    print("Done!")
