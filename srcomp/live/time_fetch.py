"""
Functions for fetching the current game time from supported APIs.

All functions must follow GAME_TIME_CALLABLE type signature.
As such, they must accept a single string argument (the API URL) and return a tuple.
The function must return a tuple containing the game time in seconds and the match number.
If a match is not currently running, both elements should be None.
"""
import logging
import time
from datetime import datetime
from typing import Callable, Tuple, Union

import requests

LOGGER = logging.getLogger(__name__)


GAME_TIME_RTN = Union[Tuple[float, int], Tuple[None, None]]
GAME_TIME_CALLABLE = Callable[[str], GAME_TIME_RTN]


# Helper functions
def raw_request_json(api_url: str) -> Tuple[float, dict]:
    """
    Make a request to the competition API and return the JSON response.

    :param api_url: The URL of the API endpoint to request.
    :return: A tuple containing the latency of the request and the JSON response.
    :raises ValueError: If the request fails.
    """
    try:
        start_time = time.time()
        r = requests.get(api_url, timeout=2)
        end_time = time.time()
        r.raise_for_status()
    except requests.exceptions.Timeout:
        raise ValueError("API request timed out")
    except requests.exceptions.HTTPError as e:
        raise ValueError(f"API request failed: {e}")
    except requests.exceptions.RequestException:
        raise ValueError("Failed to connect to API")

    latency = (end_time - start_time)
    LOGGER.debug("API request took %.3f seconds", latency)

    try:
        data: dict = r.json()
    except requests.exceptions.JSONDecodeError:
        raise ValueError(f"Failed to decode JSON: {r.text!r}")

    return latency / 2, data


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
def get_srcomp_game_time_full(api_url: str, latency_comp: bool) -> GAME_TIME_RTN:
    """
    Get the current game time from the SRComp API, optionally compensating for network latency.

    Game time is returned in seconds relative to the start of the match.

    :param api_url: The URL of the API endpoint to request.
    :param latency_comp: Whether to compensate for network latency.
    :return: A tuple containing the game time and match number.
             Each element is None if a match is not running.
    :raises ValueError: If the request fails or the response is invalid.
    """
    latency, data = raw_request_json(api_url)

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
    if latency_comp:
        # Offset game time by the single-direction latency
        game_time -= latency

    clock_diff = (now - curr_time).total_seconds() * 1000

    LOGGER.debug(
        "Received game time %.3f for match %i, clock diff: %.2f ms",
        game_time,
        match_num,
        clock_diff,
    )
    return game_time, match_num


def get_srcomp_game_time(api_url: str) -> GAME_TIME_RTN:
    """
    Get the current game time from the SRComp API.

    Game time is returned in seconds relative to the start of the match.

    :param api_url: The URL of the API endpoint to request.
    :return: A tuple containing the game time and match number.
             Each element is None if a match is not running.
    :raises ValueError: If the request fails or the response is invalid.
    """
    return get_srcomp_game_time_full(api_url, latency_comp=False)


def get_srcomp_game_time_compensated(api_url: str) -> GAME_TIME_RTN:
    """
    Get the current game time from the SRComp API, compensating for network latency.

    Game time is returned in seconds relative to the start of the match.

    :param api_url: The URL of the API endpoint to request.
    :return: A tuple containing the game time and match number.
             Each element is None if a match is not running.
    :raises ValueError: If the request fails or the response is invalid.
    """
    return get_srcomp_game_time_full(api_url, latency_comp=True)


def get_livecomp_game_time_full(api_url: str, latency_comp: bool) -> GAME_TIME_RTN:
    """
    Get the current game time from Livecomp API, optionally compensating for network latency.

    Game time is returned in seconds relative to the start of the match.

    :param api_url: The URL of the API endpoint to request.
    :param latency_comp: Whether to compensate for network latency.
    :return: A tuple containing the game time and match number.
             Each element is None if a match is not running.
    :raises ValueError: If the request fails or the response is invalid.
    """
    latency, data = raw_request_json(api_url)

    try:
        start_time = data['nextMatch']['startsAt']
        current_time = data['nextMatch']['now']
        match_num = data['nextMatch']['matchNumber']
    except (ValueError, IndexError, KeyError):
        LOGGER.debug("Not in a match")
        return None, None

    curr_time = load_timestamp(current_time)
    now = datetime.now(tz=curr_time.tzinfo)
    match_time = load_timestamp(start_time)

    game_time = (curr_time - match_time).total_seconds()
    if latency_comp:
        # Offset game time by the single-direction latency
        game_time -= latency

    clock_diff = (now - curr_time).total_seconds() * 1000

    LOGGER.debug(
        "Received game time %.3f for match %i, clock diff: %.2f ms",
        game_time,
        match_num,
        clock_diff,
    )
    return game_time, match_num


def get_livecomp_game_time(api_url: str) -> GAME_TIME_RTN:
    """
    Get the current game time from the Livecomp API.

    Game time is returned in seconds relative to the start of the match.

    :param api_url: The URL of the API endpoint to request.
    :return: A tuple containing the game time and match number.
             Each element is None if a match is not running.
    :raises ValueError: If the request fails or the response is invalid.
    """
    return get_livecomp_game_time_full(api_url, latency_comp=False)


def get_livecomp_game_time_compensated(api_url: str) -> GAME_TIME_RTN:
    """
    Get the current game time from the Livecomp API, compensating for network latency.

    Game time is returned in seconds relative to the start of the match.

    :param api_url: The URL of the API endpoint to request.
    :return: A tuple containing the game time and match number.
             Each element is None if a match is not running.
    :raises ValueError: If the request fails or the response is invalid.
    """
    return get_livecomp_game_time_full(api_url, latency_comp=True)


available_game_time_fn = {
    'srcomp': get_srcomp_game_time,
    'srcomp_compensated': get_srcomp_game_time_compensated,
    'livecomp': get_livecomp_game_time,
    'livecomp_compensated': get_livecomp_game_time_compensated,
}
