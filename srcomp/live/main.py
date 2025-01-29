#!/usr/bin/env python3
"""Main module for the srcomp-live script."""
from __future__ import annotations

import argparse
import logging
from bisect import bisect_left
from datetime import datetime
from time import sleep

import requests

from .osc import OSCClient
from .utils import Action, load_actions, load_config, validate_actions

LOGGER = logging.getLogger(__name__)


def get_game_time(api_base: str) -> tuple[float, int] | tuple[None, None]:
    """
    Get the current game time from the competition API.

    None is returned if a match is not currently running.
    Game time is returned in seconds relative to the start of the match.
    """
    r = requests.get(api_base + '/current')

    try:
        data = r.json()
        start_time = data['matches'][0]['times']['game']['start']
        current_time = data['time']
        match_num = data['matches'][0]['num']
    except (ValueError, IndexError, KeyError):
        return None, None

    game_time = (
        datetime.fromisoformat(current_time) - datetime.fromisoformat(start_time)
    ).total_seconds()

    clock_diff = (
        datetime.now() - datetime.fromisoformat(current_time)
    ).total_seconds() * 1000

    LOGGER.debug(
        "Received game time %.3f for match %i, clock diff: %.2f ms",
        game_time,
        match_num,
        clock_diff,
    )
    return game_time, match_num


def run(api_base: str, actions: list[Action], osc_client: OSCClient) -> None:
    """Run cues for each match."""
    # TODO: Implement error handling
    while True:
        # TODO: Implement abort actions
        # TODO: extract magic numbers to arguments
        game_time, match_num = get_game_time(api_base)

        if game_time is None:
            # No match is currently running
            sleep(2)
            continue

        next_action = bisect_left(actions, game_time)
        if next_action > len(actions):
            # All actions have been performed
            sleep(2)
            continue

        action = actions[next_action]
        remaining_time = action.time - game_time

        if remaining_time > 10:
            sleep(2)
            continue

        LOGGER.info(
            "Performing action at %.3f (in %.2s secs): %s",
            game_time,
            remaining_time,
            action.description
        )
        sleep(remaining_time)
        assert match_num is not None

        # Handle multiple actions occurring at the same time
        active_time = action.time
        for action in actions[next_action:]:
            if action.time != active_time:
                break
            osc_client.send_message(action.message, match_num)


def main() -> None:
    """Main function for the srcomp-live script."""
    args = parse_args()
    logging.basicConfig(level=(logging.DEBUG if args.debug else logging.INFO))

    config = load_config(args.config)

    osc_client = OSCClient(config['devices'])
    actions = load_actions(config)
    abort_actions = load_actions(config, abort_actions=True)

    # Validate that all actions have a valid device
    osc_clients = list(osc_client.clients.keys())
    validate_actions(osc_clients, actions)
    validate_actions(osc_clients, abort_actions)

    run(args.api_base, actions, osc_client)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Auto-match script")
    parser.add_argument(
        "--api-base",
        default="http://compbox.srobo/comp-api",
        help="Base URL for the competition API",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to the configuration file",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging"
    )
    # TODO implement test mode and test match mode

    return parser.parse_args()


if __name__ == "__main__":
    main()
