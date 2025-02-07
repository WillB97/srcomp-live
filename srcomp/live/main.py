#!/usr/bin/env python3
"""Main module for the srcomp-live script."""
from __future__ import annotations

import argparse
import logging
from bisect import bisect_left
from datetime import datetime, timezone
from time import sleep
from typing import NamedTuple

import requests

from .osc import OSCClient
from .test_server import run_server
from .utils import Action, MatchVerifier, load_actions, load_config, validate_actions

LOGGER = logging.getLogger(__name__)


class RunnerConf(NamedTuple):
    """Active config for the runner."""

    api_base: str
    osc_client: OSCClient
    actions: list[Action]
    abort_actions: list[Action]
    sleep_increment: float = 2
    lock_in_time: float = 10


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
        datetime.now(tz=timezone.utc) - datetime.fromisoformat(current_time)
    ).total_seconds() * 1000

    LOGGER.debug(
        "Received game time %.3f for match %i, clock diff: %.2f ms",
        game_time,
        match_num,
        clock_diff,
    )
    return game_time, match_num


def run_abort(actions: list[Action], osc_client: OSCClient) -> None:
    """Run the actions that are needed to exit a match early."""
    LOGGER.warning("[UNEXPECTED TIMING] Running abort actions. A delay may have been added.")
    for index, action in enumerate(actions):
        LOGGER.info("Performing action %d: %s", index, action.description)
        osc_client.send_message(action.message, 0)


def run(config: RunnerConf) -> None:
    """Run cues for each match."""
    final_action_time = config.actions[-1].time
    match_verifier = MatchVerifier(final_action_time)
    # TODO: Implement error handling
    while True:
        game_time, match_num = get_game_time(config.api_base)

        if not match_verifier.validate_timing(game_time, match_num):
            run_abort(config.abort_actions, config.osc_client)

        if game_time is None:
            # No match is currently running
            sleep(config.sleep_increment)
            continue

        next_action = bisect_left(config.actions, game_time)
        if next_action >= len(config.actions):
            # All actions have been performed
            sleep(config.sleep_increment)
            continue

        action = config.actions[next_action]
        remaining_time = action.time - game_time

        if remaining_time > config.lock_in_time:
            sleep(config.sleep_increment)
            continue

        LOGGER.info(
            "Scheduling action for %.1f (in %.3f secs): %s",
            action.time,
            remaining_time,
            action.description
        )
        sleep(remaining_time)
        assert match_num is not None

        # Handle multiple actions occurring at the same time
        active_time = action.time
        for action in config.actions[next_action:]:
            if action.time != active_time:
                break
            LOGGER.info("Performing action at %.1f: %s", action.time, action.description)
            config.osc_client.send_message(action.message, match_num)


def test_match(config: RunnerConf) -> None:
    # start test server in background thread
    run_server()

    test_config = config._replace(api_base="http://127.0.0.1:8008/")

    try:
        run(test_config)
    except KeyboardInterrupt:
        LOGGER.info("Exiting")


def test_abort(config: RunnerConf) -> None:
    """Run all actions listed under the "abort_actions" key of the config and exit."""
    run_abort(config.abort_actions, config.osc_client)


def main() -> None:
    """Main function for the srcomp-live script."""
    args = parse_args()
    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s: %(message)s",
        level=(logging.DEBUG if args.debug else logging.INFO)
    )

    config = load_config(args.config)

    osc_client = OSCClient(config['devices'])
    actions = load_actions(config)
    abort_actions = load_actions(config, abort_actions=True)

    # Validate that all actions have a valid device
    osc_clients = list(osc_client.clients.keys())
    validate_actions(osc_clients, actions)
    validate_actions(osc_clients, abort_actions)

    runner_config = RunnerConf(
        config['api_url'],
        osc_client,
        actions,
        abort_actions,
    )

    if args.test_abort:
        test_abort(runner_config)
    elif args.test_mode:
        test_match(runner_config)
    else:
        try:
            run(runner_config)
        except KeyboardInterrupt:
            LOGGER.info("Exiting")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Auto-match script")
    parser.add_argument(
        "config",
        help="Path to the configuration file",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Don't connect to REST API. Simulate running a set of matches right now"
    )
    parser.add_argument(
        "--test-abort",
        action="store_true",
        help="Run all actions listed under the 'abort_actions' key of the config and exit"
    )

    return parser.parse_args()


if __name__ == "__main__":
    main()
