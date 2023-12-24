"""
Task called via the `nomad build` CLI command
"""

# Imports
import sys
from nomad.agents.base import Agent
from nomad.agents.meta import MetaAgent
from nomad.agents import (  # noqa: F401
    meta,
    ec2,
)
from nomad.tasks.base import BaseTask


class BuildTask(BaseTask):

    def run(self):
        """
        Create the agent specified in the user's configuration file, then run the user's
        project on the newly created agent.
        """
        self.check()
        agent_type = self.infra.infra_conf["type"]

        # Replace dashes
        agent_type = agent_type.replace("-", "")

        agent: Agent = MetaAgent.get_agent(agent_type)(
            args=self.args,
            nomad_wkdir=self.nomad_wkdir,
            agent_name=self.name,
            agent_conf=self.conf,
            infra=self.infra,
            entrypoint=self.entrypoint,
            image=self.image,
        )

        # Apply. Note that if this fails, this automatically deletes the resources.
        agent.apply()

        # Run
        run_returncode = agent.run()
        if run_returncode != 0:
            # If the user wants to preserve the cloud resources, then exist
            if self.args.no_delete_failure:
                sys.exit(1)

            # Otherwise, delete the resources
            else:
                agent.delete()
                sys.exit(1)

        # Otherwise, the project ran successfully
        if self.args.no_delete_success:
            sys.exit(0)
        else:
            agent.delete()
            sys.exit(0)
