"""
Example function for test case.
"""

# Imports
import argparse
from pathlib import Path


# Functions
def write_txt_file(
    python_version: str,
    platform: str,
    output_name: str
):
    """
    Write a file to S3. This allows us to test whether our code actually works.
    """
    txt_data = "Hello world from our `{platform}.{python_version}.{output_name}` test case!".format(  # noqa
        python_version=python_version,
        platform=platform,
        output_name=output_name
    )
    output_key = f"{platform}_{python_version}_{output_name}".replace(".", "")
    with open(Path(__file__).parent / f'{output_key}.txt', 'w') as f:
        f.write(txt_data)


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
