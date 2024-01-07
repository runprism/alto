"""
Command class. This allows us to modify commands depending on the specific
infrastructure we are using.
"""

# Imports
from typing import Dict, List, Union
from pathlib import Path


# Class definition
class AgentCommand:

    def __init__(self,
        executable: str,
        script: Union[str, Path],
        args: Dict[str, Union[str, List[str]]]
    ):
        self.executable = executable
        self.script = script
        self.args = args

        # Accepted args
        self.accepted_optargs = [k for k, _ in self.args.items()]
        self.additional_optargs: Dict[str, Union[str, List[str]]] = {}

    def set_accepted_apply_optargs(self, accepted_optargs: List[str]):
        """
        Define accepted optargs for the command
        """
        self.accepted_optargs = accepted_optargs

    def set_additional_optargs(self,
        additional_optargs: Dict[str, Union[str, List[str]]]
    ):
        """
        Define additional optargs
        """
        self.additional_optargs = additional_optargs

    def process_cmd(self) -> List[str]:
        """
        Process the command. That is, remove unaccepted optargs and add any
        additional ones required
        """
        # Remove unused optargs
        processed = []
        for optarg, value in self.args.items():
            if optarg not in self.accepted_optargs:
                continue
            else:
                # If the value is a list, then we need to make sure the optarg is placed
                # before every single value in the list.
                if isinstance(value, list):
                    for v in value:
                        processed.append(optarg)
                        processed.append(v)
                else:
                    processed.append(optarg)
                    processed.append(value)

        # Add additional optargs
        for newoptarg, newoptarg_value in self.additional_optargs.items():
            # Same as above...
            if isinstance(newoptarg_value, list):
                for _v in newoptarg_value:
                    processed.append(newoptarg)
                    processed.append(_v)
            else:
                processed.append(newoptarg)
                processed.append(newoptarg_value)

        # Add the executable and the script
        return [self.executable, str(self.script)] + processed
