"""
Task called via the `alto apply` CLI command
"""


# Imports
import sys
from alto.agents.base import Agent
from alto.agents.meta import MetaAgent
from alto.agents import (  # noqa: F401
    meta,
    ec2,
)
from alto.tasks.base import BaseTask


# Class definition
class ApplyTask(BaseTask):

    def run(self):
        """
        Create the agent specified in the user's configuration file
        """
        self.check()
        agent_type = self.infra.infra_conf["type"]

        # Replace dashes
        agent_type = agent_type.replace("-", "")

        agent: Agent = MetaAgent.get_agent(agent_type)(
            args=self.args,
            alto_wkdir=self.alto_wkdir,
            agent_name=self.name,
            agent_conf=self.conf,
            infra=self.infra,
            entrypoint=self.entrypoint,
            image=self.image,
            output_mgr=self.output_mgr,
        )
        returncode = agent.apply()
        if returncode != 0:
            sys.exit(1)
