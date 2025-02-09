"""OSC controller for the srcomp-live module."""
from __future__ import annotations

from typing import Any

from pythonosc.udp_client import SimpleUDPClient

from .utils import OSC_TYPES, ArgTemplate, OSCMessage


def format_args(
    base_args: list[OSC_TYPES | ArgTemplate] | OSC_TYPES | ArgTemplate,
    *args: Any,
    **kwargs: Any,
) -> list[OSC_TYPES] | OSC_TYPES:
    """Template values into every argument."""
    formatted_args: list[OSC_TYPES] | OSC_TYPES
    if isinstance(base_args, list):
        formatted_args = []
        for arg in base_args:
            # Recurse to handle templating every item in the list
            formatted_arg = format_args(arg, *args, **kwargs)
            assert not isinstance(formatted_arg, list), "Nested lists are not permitted"
            formatted_args.append(formatted_arg)
    elif isinstance(base_args, str):
        formatted_args = base_args.format(*args, **kwargs)
    elif isinstance(base_args, ArgTemplate):
        formatted_args = base_args.format(*args, **kwargs)
    else:
        formatted_args = base_args

    return formatted_args


class OSCClient:
    """An OSC client that sends messages to a selected devices."""

    def __init__(self, devices: dict[str, str]) -> None:
        """Initialise the OSC clients."""
        self.clients: dict[str, SimpleUDPClient] = {}

        # Create clients for each device in the config
        for name, uri in devices.items():
            ip, port = uri.rsplit(':', maxsplit=1)
            self.clients[name] = SimpleUDPClient(ip, int(port))

    def send_message(self, message: OSCMessage, match_num: int) -> None:
        """Send an OSC message to the device."""
        client = self.clients[message.target]

        # Template the match number into the message
        address = message.message.format(match_num=match_num)

        # Template the match number into the arguments
        client.send_message(address, format_args(message.args, match_num=match_num))
