"""A JSON decoder that ignores comments in the JSON input."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, NamedTuple, Union


class JSONWithCommentsDecoder(json.JSONDecoder):
    """
    A JSON decoder that ignores comments in the JSON input.

    Comments are lines starting with '//'.
    """

    def __init__(self, **kw) -> None:  # type: ignore[no-untyped-def]
        super().__init__(**kw)

    def decode(self, s: str) -> Any:  # type: ignore[override]
        """Decode a JSON string with comments."""
        s = '\n'.join(
            line if not line.lstrip().startswith('//') else ''
            for line in s.split('\n')
        )
        return super().decode(s)


def load_config(filename: str) -> dict[str, Any]:
    """
    Load a JSON configuration file with comments.

    Comments are lines starting with '//'.
    """
    with open(filename) as f:
        config: dict = json.load(f, cls=JSONWithCommentsDecoder)

    # Ensure top-level keys are present
    config.setdefault('devices', [])
    config.setdefault('actions', [])
    config.setdefault('abort_actions', [])

    return config


OSC_TYPES = Union[str, float, int, bool]


class OSCMessage(NamedTuple):
    """
    An OSC message to be sent to a device.

    target: The name of the device to send the message to.
    message: The OSC message to send.
    args: The arguments to send with the message.
    """

    target: str
    message: str
    args: list[OSC_TYPES] | OSC_TYPES


@dataclass
class Action:
    """
    An action to be performed at a specific game time.

    time: The game time at which to perform the action.
    device: The name of the device to send the message to.
    message: The OSC message to send.
    args: The arguments to send with the message.
    description: An optional description of the action.
    """

    time: float
    message: OSCMessage
    description: str = ""

    def __lt__(self, value: object) -> bool:
        if isinstance(value, float):
            return self.time < value
        elif isinstance(value, Action):
            return self.time < value.time
        return NotImplemented


def load_actions(config: dict[str, Any], abort_actions: bool = False) -> list[Action]:
    """Load the actions from the config."""
    actions: list[Action] = []
    action_key = 'abort_actions' if abort_actions else 'actions'

    for action in config[action_key]:
        # Time is not used for abort actions
        action_time = 0 if abort_actions else float(action['time'])
        # TODO: Implement templating for non-string arguments

        actions.append(Action(
            time=action_time,
            message=OSCMessage(
                target=action['device'],
                message=action['message'],
                args=action['args'],
            ),
            description=action.get('description', ""),
        ))

    actions.sort()
    return actions


def validate_actions(devices: list[str], actions: list[Action]) -> None:
    """Validate that all actions have a valid device."""
    for action in actions:
        if action.message.target not in devices:
            raise ValueError(f"Unknown device {action.message.target!r} in action {action}")
