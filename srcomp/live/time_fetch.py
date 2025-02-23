"""
Functions for fetching the current game time from supported APIs.

All functions must follow GAME_TIME_CALLABLE type signature.
As such, they must accept a single string argument (the API URL) and return a tuple.
The function must return a tuple containing the game time in seconds and the match number.
If a match is not currently running, both elements should be None.
"""
import logging
from datetime import datetime
from typing import Callable, Union

import requests

LOGGER = logging.getLogger(__name__)


GAME_TIME_RTN = Union[tuple[float, int], tuple[None, None]]
GAME_TIME_CALLABLE = Callable[[str], GAME_TIME_RTN]


# Helper functions
def raw_request_json(api_url: str) -> dict:
    """
    Make a request to the competition API and return the JSON response.

    :param api_url: The URL of the API endpoint to request.
    :return: The JSON response from the API.
    :raises ValueError: If the request fails.
    """
    try:
        r = requests.get(api_url, timeout=2)
        r.raise_for_status()
    except requests.exceptions.Timeout:
        raise ValueError("API request timed out")
    except requests.exceptions.HTTPError as e:
        raise ValueError(f"API request failed: {e}")
    except requests.exceptions.RequestException:
        raise ValueError("Failed to connect to API")

    try:
        data: dict = r.json()
    except requests.exceptions.JSONDecodeError:
        raise ValueError(f"Failed to decode JSON: {r.text!r}")

    return data


def load_timestamp(timestamp: str) -> datetime:
    """
    Load a timestamp string into a datetime object.

    :param timestamp: The timestamp string to load.
    :return: The datetime object.
    :raises ValueError: If the timestamp cannot be parsed.
    """
    try:
        time_obj = datetime.fromisoformat(timestamp)
    except (ValueError, TypeError):
        raise ValueError(f"Failed to decode timestamp: {timestamp}")
    return time_obj


# API functions
def get_srcomp_game_time(api_url: str) -> GAME_TIME_RTN:
    """
    Get the current game time from the SRComp API.

    Game time is returned in seconds relative to the start of the match.

    :param api_url: The URL of the API endpoint to request.
    :return: A tuple containing the game time and match number.
             Each element is None if a match is not running.
    :raises ValueError: If the request fails or the response is invalid.
    """
    data = raw_request_json(api_url)

    try:
        start_time = data['matches'][0]['times']['game']['start']
        current_time = data['time']
        match_num = data['matches'][0]['num']
    except (ValueError, IndexError, KeyError):
        LOGGER.debug("Not in a match")
        return None, None

    curr_time = load_timestamp(current_time)
    now = datetime.now(tz=curr_time.tzinfo)
    match_time = load_timestamp(start_time)

    game_time = (curr_time - match_time).total_seconds()
    clock_diff = (now - curr_time).total_seconds() * 1000

    LOGGER.debug(
        "Received game time %.3f for match %i, clock diff: %.2f ms",
        game_time,
        match_num,
        clock_diff,
    )
    return game_time, match_num


available_game_time_fn = {
    'srcomp': get_srcomp_game_time,
}
