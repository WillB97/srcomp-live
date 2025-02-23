#!/usr/bin/env python3
"""Main module for the srcomp-live script."""
from __future__ import annotations

import argparse
import logging
from bisect import bisect_left
from time import sleep
from typing import NamedTuple

from .osc import OSCClient
from .test_server import run_server
from .time_fetch import GAME_TIME_CALLABLE, available_game_time_fn
from .utils import Action, MatchVerifier, load_actions, load_config, validate_actions

LOGGER = logging.getLogger(__name__)


class RunnerConf(NamedTuple):
    """Active config for the runner."""

    api_url: str
    osc_client: OSCClient
    actions: list[Action]
    abort_actions: list[Action]
    game_time_fn: GAME_TIME_CALLABLE
    sleep_increment: float = 2
    lock_in_time: float = 10


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
    while True:
        try:
            game_time, match_num = config.game_time_fn(config.api_url)
        except ValueError as e:
            LOGGER.warning(e)
            game_time, match_num = None, None

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
    """
    Simulate running a set of matches right now.

    Runs the test server in a background thread to provide match data.
    """
    run_server()

    test_config = config._replace(api_url="http://127.0.0.1:8008/")

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
        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s",
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
        game_time_fn=available_game_time_fn[config['api_type']],
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
    parser = argparse.ArgumentParser(description="Trigger OSC cues based on match time")
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
