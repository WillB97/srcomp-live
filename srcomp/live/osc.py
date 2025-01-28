"""OSC controller for the srcomp-live module."""
from __future__ import annotations

from pythonosc.udp_client import SimpleUDPClient

from .utils import OSC_TYPES, OSCMessage


class OSCClient:
    """An OSC client that sends messages to a selected devices."""

    def __init__(self, devices: dict[str, str]) -> None:
        """Initialise the OSC clients."""
        self.clients: dict[str, SimpleUDPClient] = {}

        # Create clients for each device in the config
        for name, uri in devices.items():
            ip, port = uri.split(':')
            self.clients[name] = SimpleUDPClient(ip, int(port))

    def send_message(self, message: OSCMessage, match_num: int) -> None:
        """Send an OSC message to the device."""
        client = self.clients[message.target]

        # Template the match number into the message
        address = message.message.format(match_num=match_num)

        # Template the match number into any string arguments
        args: list[OSC_TYPES] | OSC_TYPES

        if isinstance(message.args, list):
            # TODO: Implement templating for non-string arguments
            args = [
                arg.format(match_num=match_num) if isinstance(arg, str) else arg
                for arg in message.args
            ]
        elif isinstance(message.args, str):
            args = message.args.format(match_num=match_num)
        else:
            # TODO: Implement templating for non-string arguments
            args = message.args

        client.send_message(address, args)
