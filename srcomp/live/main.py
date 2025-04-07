#!/usr/bin/env python3
"""Main module for the srcomp-live script."""
from __future__ import annotations

import argparse
import logging
import queue
import threading
import time
from bisect import bisect_left
from time import sleep
from typing import NamedTuple, Optional

from .osc import OSCClient
from .test_server import run_server
from .time_fetch import available_game_time_fn
from .utils import Action, MatchVerifier, load_actions, load_config, validate_actions

LOGGER = logging.getLogger(__name__)


class RunnerConf(NamedTuple):
    """Active config for the runner."""

    api_url: str
    osc_client: OSCClient
    actions: list[Action]
    abort_actions: list[Action]
    api_type: str = "srcomp"
    sleep_increment: float = 2
    lock_in_time: float = 10
    queue: Optional[queue.Queue] = None


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
    game_time_fn = available_game_time_fn[config.api_type]
    while True:
        try:
            game_time, match_num = game_time_fn.get_game_time(config.api_url)
        except ValueError as e:
            LOGGER.warning(e)

            if not game_time_fn.abort_on_api_fail:
                # Don't process this just go to the next iteration
                sleep(config.sleep_increment)
                continue
            else:
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
        if config.queue is not None:
            config.queue.put_nowait(remaining_time + time.time())
        sleep(remaining_time)
        assert match_num is not None

        # Handle multiple actions occurring at the same time
        active_time = action.time
        for action in config.actions[next_action:]:
            if action.time != active_time:
                break
            LOGGER.info("Performing action at %.1f: %s", action.time, action.description)
            config.osc_client.send_message(action.message, match_num)

        if config.actions.index(action) == len(config.actions) - 1:
            # All actions have been performed
            match_verifier.in_match = False


def test_match(config: RunnerConf, match_timings: dict[str, int]) -> None:
    """
    Simulate running a set of matches right now.

    Runs the test server in a background thread to provide match data.
    """
    run_server(api_type=config.api_type, match_timings=match_timings)

    test_config = config._replace(api_url="http://127.0.0.1:8008/")

    try:
        run(test_config)
    except KeyboardInterrupt:
        LOGGER.info("Exiting")


def test_abort(config: RunnerConf) -> None:
    """Run all actions listed under the "abort_actions" key of the config and exit."""
    run_abort(config.abort_actions, config.osc_client)


def countdown_thread(countdown_queue: queue.Queue) -> None:
    """Run the countdown in a separate thread."""
    while True:
        end_time = countdown_queue.get()

        display_countdown(end_time)
        countdown_queue.task_done()


def display_countdown(end_time: float, interval: float = 0.1) -> None:
    """Display a countdown timer in the terminal."""
    remaining = end_time - time.time()
    if remaining < interval:
        return

    while (remaining := end_time - time.time()) > interval:
        print(f"Running in {remaining:4.1f}s", end='\r')
        sleep(interval)

    print(f"Running {' ' * 10}")


def main() -> None:
    """Main function for the srcomp-live script."""
    args = parse_args()
    log_format = "[%(asctime)s] %(name)s %(levelname)s: %(message)s"
    logging.basicConfig(
        format=log_format,
        level=(logging.DEBUG if args.debug else logging.INFO)
    )
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file, mode='a')
        file_handler.setFormatter(logging.Formatter(log_format))

        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)

    config = load_config(args.config)

    osc_client = OSCClient(config['devices'])
    actions = load_actions(config)
    abort_actions = load_actions(config, abort_actions=True)

    # Validate that all actions have a valid device
    osc_clients = list(osc_client.clients.keys())
    validate_actions(osc_clients, actions, config['match_slot_lengths'])
    validate_actions(osc_clients, abort_actions, {})

    assert config['api_type'] in available_game_time_fn, "Unsupported API type"

    runner_config = RunnerConf(
        config['api_url'],
        osc_client,
        actions,
        abort_actions,
        api_type=config['api_type'],
        queue=queue.Queue(),
    )

    thread = threading.Thread(
        target=countdown_thread,
        args=(runner_config.queue,),
        daemon=True
    )
    thread.start()

    if args.test_abort:
        test_abort(runner_config)
    elif args.test_mode:
        test_match(runner_config, config['match_slot_lengths'])
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
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to the log file."
    )

    return parser.parse_args()


if __name__ == "__main__":
    main()
