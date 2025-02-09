# srcomp-live

A bridge between the SRComp REST API and OSC controlled devices.
OSC is a de-facto standard for theatrical automation.
Being able to directly interface these to SR's automation software allows for using industry standard tools such as Qlab, MagicQ & OBS.

## Installation

srcomp-live can be installed directly from PyPi with:
```bash
pip install srcomp-live
```

If you (wrongly) believe that YAML is a better configuration format, support for YAML files can be included by running:
```bash
pip install srcomp-live[yaml]
```

This will provide the `srcomp-live` command that is used to interact with the package.

## Configuration

Here is an example configuration file that sets a theoretical lighting controller to red 10 seconds before the start of a match and white if the match ends unexpectedly.

```json
{
    "api_url": "http://compbox.srobo/comp-api/current",
    "devices": {
        "lighting": "192.168.0.2:8000"
    },
    "actions": [
        {
            "time": -10,
            "device": "lighting",
            "message": "/set_color/{match_num}",
            "args": ["#FF0000"],
            "description": "Set the color of the lighting to red"
        }
    ],
    "abort_actions": [
        {
            "device": "lighting",
            "message": "/set_color",
            "args": ["#FFFFFF"],
            "description": "Set the color of the lighting to white"
        }
    ]
}
```

The configuration contains a number of sections.

The actions section contains a list of the actions that will be executed within the match.
The keys available in each action are listed below.

| Key | Description |
| --- | --- |
| time | The relative number of seconds after the start time of the match to execute this action |
| device | The name of the device configured in the `devices` section to send this action to |
| message | The OSC message to send |
| args | A list of one or more arguments to send along with the OSC message |
| description | A description to include in the log message when executing the action |

The `abort_actions` section has the same set of keys as the `actions` section, except for the `time` key.
These actions are all executed if the system detects a match unexpectedly end or the time within a match decrease.
This can be used to stop sound effects and set lighting to an out of match state when match is delayed.

