<p align="center">
  <img src="https://github.com/runprism/alto/blob/main/.github/alto.png" alt="Alto logo" style="width: 65%"/>
</p>

<div align="center">

[![Tests](https://github.com/runprism/alto/actions/workflows/tests.yml/badge.svg)](https://github.com/runprism/alto/actions/workflows/tests.yml)
[![PyPI version](https://img.shields.io/pypi/v/alto-dev)](https://pypi.org/project/alto-dev/)
![Python version](https://img.shields.io/badge/python-3.8%20%7C%203.9%20%7C%203.10%20%7C%203.11-blue)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
[![Checked with flake8](https://img.shields.io/badge/flake8-checked-blueviolet)](https://flake8.pycqa.org/en/latest/)


</div>

# Welcome to Alto!
Alto is the easiest way to run any code on the cloud! Alto is designed to be used with Prism projects, but it can be used to any arbitrary code (e.g., functions, scripts, Jupyter notebooks, or entire projects)!


## Getting Started

Alto can be installed via ```pip```. Alto requires Python >= 3.8.

```
pip install --upgrade pip
pip install alto-dev
```

Then, initialize a configuration file with the `alto init` CLI command. This command will automatically prompt you for all the information needed to configure your cloud environment.
```
$ alto init

What type of cloud environment do you want to use [ec2]? ec2
What would you like the name of your configuration file to be (default: alto.yml)?

<HH:MM:SS> | INFO | Building configuration file...
<HH:MM:SS> | INFO | Done!
```

To run your project on your cloud environment, use the `alto build` command. Under the hood, this command:
1. Builds the cloud environment according to instructions contained in the configuration file, and
2. Executes your project on the cloud.
```
$ alto build -f alto.yml
<HH:MM:SS> | INFO  | my_cloud_agent[build]  | Created key pair my_cloud_agent
<HH:MM:SS> | INFO  | my_cloud_agent[build]  | Created security group with ID sg-XXXXXXXXXXXXXXXXX in VPC vpc-XXXXXXXXXXXXXXXXX
<HH:MM:SS> | INFO  | my_cloud_agent[build]  | Created EC2 instance with ID i-XXXXXXXXXXXXXXXXX
<HH:MM:SS> | INFO  | my_cloud_agent[build]  | Instance i-XXXXXXXXXXXXXXXXX is pending... checking again in 5 seconds
<HH:MM:SS> | INFO  | my_cloud_agent[build]  | Instance i-XXXXXXXXXXXXXXXXX is pending... checking again in 5 seconds
<HH:MM:SS> | INFO  | my_cloud_agent[build]  | Instance i-XXXXXXXXXXXXXXXXX is pending... checking again in 5 seconds
<HH:MM:SS> | INFO  | my_cloud_agent[build]  | Instance i-XXXXXXXXXXXXXXXXX is pending... checking again in 5 seconds
...
...
<HH:MM:SS> | INFO  | my_cloud_agent[run]    | Done!
<HH:MM:SS> | INFO  | my_cloud_agent[delete] | Deleting key-pair my_cloud_agent at /../../../my_cloud_agent.pem
<HH:MM:SS> | INFO  | my_cloud_agent[delete] | Deleting instance i-XXXXXXXXXXXXXXXXX
<HH:MM:SS> | INFO  | my_cloud_agent[delete] | Deleting security group sg-XXXXXXXXXXXXXXXXX
```

Alternatively, you could use the `alto apply` command to first build the cloud environment and then use `alto run` to actually run the code.

Check out our [documentation](https://docs.tryalto.dev/) to see the full list of CLI command and their usage!

## Cloud environments
Alto currently supports the following cloud environments (which we call "Agents"):
- **ec2**

## Product Roadmap

We're always looking to improve our product. Here's what we're working on at the moment:

- **Additional Agents**: GCP Virtual Machines, EMR clusters, Databricks clusters, and more!
- **Managed service**: Managed platform to easily view, manage, and schedule your different cloud deployments

Let us know if you'd like to see another feature!