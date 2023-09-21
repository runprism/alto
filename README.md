<p align="center">
  <img src="https://github.com/runprism/nomad/raw/main/.github/nomad.png" alt="Nomad logo" height="200"/>
</p>

<div align="center">

[![CI Linux](https://github.com/runprism/nomad/actions/workflows/ci-linux.yml/badge.svg?branch=setup)](https://github.com/runprism/nomad/actions/workflows/ci-linux.yml)
[![CI MacOS](https://github.com/runprism/nomad/actions/workflows/ci-macos.yml/badge.svg?branch=setup)](https://github.com/runprism/nomad/actions/workflows/ci-macos.yml)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)


</div>

# Welcome to Nomad!
Nomad is the easiest way to run any code on the cloud! Nomad is designed to be used with Prism projects, but it can be used to any arbitrary code (e.g., functions, scripts, Jupyter notebooks, or entire projects)!


## Getting Started

Nomad can be installed via ```pip```. Nomad requires Python >= 3.8.

```
pip install --upgrade pip
pip install nomad-dev
```

Then, initialize a configuration file with the `nomad init` CLI command. This command will automatically prompt you for all the information needed to configure your cloud environment.
```
$ nomad init

What type of cloud environment do you want to use [ec2]? ec2
What would you like the name of your configuration file to be (default: nomad.yml)?

<HH:MM:SS> | INFO | Building configuration file...
<HH:MM:SS> | INFO | Done!
```

To run your project on your cloud environment, use the `nomad build` command. Under the hood, this command:
1. Builds the cloud environment according to instructions contained in the configuration file, and
2. Executes your project on the cloud.
```
$ nomad build -f nomad.yml
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

Alternatively, you could use the `nomad apply` command to first build the cloud environment and then use `nomad run` to actually run the code.

Check out our [documentation](https://docs.trynomad.dev/) to see the full list of CLI command and their usage!

## Cloud environments
Nomad currently supports the following cloud environments (which we call "Agents"):
- **ec2**

## Product Roadmap

We're always looking to improve our product. Here's what we're working on at the moment:

- **Additional Agents**: GCP Virtual Machines, EMR clusters, Databricks clusters, and more!
- **Managed service**: Managed platform to easily view, manage, and schedule your different cloud deployments

Let us know if you'd like to see another feature!