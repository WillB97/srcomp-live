"""A JSON decoder that ignores comments in the JSON input."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, NamedTuple, Union

LOGGER = logging.getLogger(__name__)


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
    try:
        import yaml
        yaml_available = True
    except ImportError:
        yaml_available = False

    with open(filename) as f:
        # Support loading YAML files if PyYAML is available
        config: dict
        if yaml_available and (filename.endswith('.yaml') or filename.endswith('.yml')):
            config = yaml.load(f, yaml.Loader)
        else:
            config = json.load(f, cls=JSONWithCommentsDecoder)

    # Ensure top-level keys are present
    assert 'api_url' in config, "'api_url' must be specified in the config file"
    config.setdefault('devices', [])
    config.setdefault('actions', [])
    config.setdefault('abort_actions', [])
    config.setdefault('match_slot_lengths', {})

    return config


OSC_TYPES = Union[str, float, int, bool]


class ArgTemplate(NamedTuple):
    """A placeholder to allow templating the match number into numeric arguments."""

    template: str
    type: str

    @classmethod
    def setup(cls, template: str) -> ArgTemplate:
        """
        Convert the packed template string into a separate template and type.

        The packed form is "{<var:type>}" where var is the name of the variable
        to be templated.

        :raises ValueError: If the input string is invalid.
        """
        # Check this input is in the proper form
        if not (template.startswith('{<') and template.endswith('>}')):
            raise ValueError("Invalid template format")

        # remove template brackets
        template_name, typename = template[2:-2].split(':', 1)

        # validate type is one we support
        if typename not in ('int', 'float'):
            raise ValueError("Unsupported type")
        return cls("{" + template_name + "}", typename)

    def format(self, *args: Any, **kwargs: Any) -> float | int:
        """Apply values to the template and return the formatted value."""
        formatted_str = self.template.format(*args, **kwargs)
        if self.type == 'int':
            return int(formatted_str)
        elif self.type == 'float':
            return float(formatted_str)
        else:
            raise NotImplementedError


class OSCMessage(NamedTuple):
    """
    An OSC message to be sent to a device.

    target: The name of the device to send the message to.
    message: The OSC message to send.
    args: The arguments to send with the message.
    """

    target: str
    message: str
    args: list[OSC_TYPES | ArgTemplate] | OSC_TYPES | ArgTemplate


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


@dataclass
class MatchVerifier:
    """Collection of tools to verify that matches are advancing as expected."""

    final_action_time: float

    in_match: bool = False
    # These values are only valid while in_match is true
    current_match: int = 0
    last_time: float = 0.0

    def validate_timing(self, game_time: float | None, match_num: int | None) -> bool:
        """Validate the timing of the match."""
        result = True
        if game_time is None or match_num is None:
            # Not in a match
            if self.in_match:
                # The match has unexpectedly ended
                LOGGER.warning("Match finished unexpectedly.")
                result = False
            self.in_match = False
            return result

        if game_time > self.final_action_time:
            self.in_match = False
            return True

        if not self.in_match:
            # Just entered a match
            self.in_match = True
            self.current_match = match_num
            self.last_time = game_time
            return True

        if self.current_match != match_num:
            # We've changed match without completing the last one
            LOGGER.warning("Match number changed mid-match")
            result = False
            self.in_match = False
        elif game_time < self.last_time:
            # We've reset within the same match
            LOGGER.warning("Match time decreased changed mid-match")
            result = False
            self.in_match = False

        return result


def load_actions(config: dict[str, Any], abort_actions: bool = False) -> list[Action]:
    """Load the actions from the config."""
    actions: list[Action] = []
    action_key = 'abort_actions' if abort_actions else 'actions'

    for action in config[action_key]:
        # Time is not used for abort actions
        action_time = 0 if abort_actions else float(action['time'])

        args = action['args']

        # Handle templating for non-string arguments
        for index, arg in enumerate(args):
            if isinstance(arg, str) and arg.startswith('{<'):
                try:
                    args[index] = ArgTemplate.setup(arg)
                except ValueError:
                    action_name = f"{len(actions)}"
                    if 'description' in action:
                        action_name += f" {action['description']}"
                    raise ValueError(
                        f"Argument {index} of action {action_name}"
                    )

        actions.append(Action(
            time=action_time,
            message=OSCMessage(
                target=action['device'],
                message=action['message'],
                args=args,
            ),
            description=action.get('description', ""),
        ))

    actions.sort()
    return actions


def validate_actions(
    devices: list[str],
    actions: list[Action],
    match_timings: dict[str, int],
) -> None:
    """Validate that all actions have a valid device."""
    match_earliest = - match_timings.get('pre', 30)
    match_latest = match_timings.get('match', 150) + match_timings.get('post', 90)

    for action in actions:
        if action.message.target not in devices:
            raise ValueError(f"Unknown device {action.message.target!r} in action {action}")
        if action.time < match_earliest:
            raise ValueError(f"Action {action} is scheduled too early, this cue cannot be run")
        if action.time > match_latest:
            raise ValueError(f"Action {action} is scheduled too late, this cue cannot be run")
        if (action.time - match_earliest) < 2:
            LOGGER.warning(
                f"Action {action} is scheduled very close to the start of the match slot, "
                "this cue may not be run"
            )
