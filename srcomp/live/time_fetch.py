"""
Functions for fetching the current game time from supported APIs.

All functions must follow GAME_TIME_CALLABLE type signature.
As such, they must accept a single string argument (the API URL) and return a tuple.
The function must return a tuple containing the game time in seconds and the match number.
If a match is not currently running, both elements should be None.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Tuple

import requests

LOGGER = logging.getLogger(__name__)


class GameTimeFetch:
    """
    Base class for fetching the current game time from an API.

    Game time is returned in seconds relative to the start of the match.
    """

    abort_on_api_fail = True

    # Helper functions
    @staticmethod
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

    @staticmethod
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
    def get_game_time(self, api_url: str) -> tuple[float, int] | tuple[None, None]:
        """
        Get the current game time from the API.

        Game time is returned in seconds relative to the start of the match.

        :param api_url: The URL of the API endpoint to request.
        :return: A tuple containing the game time and match number.
                 Each element is None if a match is not running.
        :raises ValueError: If the request fails or the response is invalid.
        """
        raise NotImplementedError("This function must be implemented by the subclass")


class SRCompFetch(GameTimeFetch):
    """
    Get the current game time from the SRComp API, optionally compensating for network latency.

    Game time is returned in seconds relative to the start of the match.

    :param latency_comp: Whether to compensate for network latency.
    """

    abort_on_api_fail = True

    def __init__(self, latency_comp: bool):
        self._latency_comp = latency_comp
        super().__init__()

    def get_game_time(self, api_url: str) -> tuple[float, int] | tuple[None, None]:
        """
        Get the current game time from the SRComp API.

        Game time is returned in seconds relative to the start of the match.

        :param api_url: The URL of the API endpoint to request.
        :return: A tuple containing the game time and match number.
                Each element is None if a match is not running.
        :raises ValueError: If the request fails or the response is invalid.
        """
        latency, data = self.raw_request_json(api_url)

        try:
            if not data['matches']:
                LOGGER.debug("Not in a match")
                return None, None

            start_time = data['matches'][0]['times']['game']['start']
            current_time = data['time']
            match_num = data['matches'][0]['num']
        except (ValueError, IndexError, KeyError) as e:
            raise ValueError(f"Invalid API response: {e}")

        curr_time = self.load_timestamp(current_time)
        now = datetime.now(tz=curr_time.tzinfo)
        match_time = self.load_timestamp(start_time)

        game_time = (curr_time - match_time).total_seconds()
        if self._latency_comp:
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


class LivecompFetch(GameTimeFetch):
    """
    Get the current game time from Livecomp API, optionally compensating for network latency.

    Game time is returned in seconds relative to the start of the match.

    :param latency_comp: Whether to compensate for network latency.
    """

    abort_on_api_fail = False

    def __init__(self, latency_comp: bool):
        self._latency_comp = latency_comp
        super().__init__()

    def get_game_time(self, api_url: str) -> tuple[float, int] | tuple[None, None]:
        """
        Get the current game time from Livecomp API.

        Game time is returned in seconds relative to the start of the match.

        :param api_url: The URL of the API endpoint to request.
        :return: A tuple containing the game time and match number.
                Each element is None if a match is not running.
        :raises ValueError: If the request fails or the response is invalid.
        """
        latency, data = self.raw_request_json(api_url)

        try:
            if data['nextMatch'] is None:
                LOGGER.debug("Not in a match")
                return None, None

            start_time = data['nextMatch']['startsAt']
            current_time = data['nextMatch']['now']
            match_num = data['nextMatch']['matchNumber']
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(f"Invalid API response: {e}")

        curr_time = self.load_timestamp(current_time)
        now = datetime.now(tz=curr_time.tzinfo)
        match_time = self.load_timestamp(start_time)

        game_time = (curr_time - match_time).total_seconds()
        if self._latency_comp:
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


available_game_time_fn: dict[str, GameTimeFetch] = {
    'srcomp': SRCompFetch(False),
    'srcomp_compensated': SRCompFetch(True),
    'livecomp': LivecompFetch(False),
    'livecomp_compensated': LivecompFetch(True),
}
