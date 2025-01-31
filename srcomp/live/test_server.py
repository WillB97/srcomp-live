#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from math import floor
from time import time
from typing import Any, NamedTuple

LOGGER = logging.getLogger(__name__)


class ServerConf(NamedTuple):
    """Global configuration of the server."""

    start_time: float = time()
    start_num: int = 0
    end_num: int | None = None


_CONFIG = ServerConf()
MATCH_CONFIG = {
    "pre": 60,
    "match": 150,
    "post": 90
}
BASE_TEMPLATE = {
    "matches": [],
    "time": "",
}


def get_match(curr_time: float) -> tuple[float, int] | None:
    """Calculate match number and start time for the given time."""
    elapsed = curr_time - _CONFIG.start_time
    if elapsed < 0:
        return None

    slot_length = sum(MATCH_CONFIG.values())
    match_num = floor(elapsed / slot_length) + _CONFIG.start_num

    if _CONFIG.end_num and match_num > _CONFIG.end_num:
        return None

    match_start = match_num * slot_length + MATCH_CONFIG["pre"]
    match_time = _CONFIG.start_time + match_start

    return (match_time, match_num)


class ServerHandler(BaseHTTPRequestHandler):
    """Handler for HTTP requests."""

    def log_message(self, format: str, *args: Any) -> None:
        """Inhibit internal logging."""
        pass

    def do_HEAD(self) -> None:
        """Generate response for HEAD request."""
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

    def do_GET(self) -> None:
        """Generate response for GET request."""
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

        payload: dict[str, Any] = deepcopy(BASE_TEMPLATE)
        match_data = get_match(time())
        if match_data is None:
            # No match ongoing
            payload["time"] = datetime.now(timezone.utc).isoformat()
            self.wfile.write(json.dumps(payload).encode())
            LOGGER.info("No match currently running")
            return

        match_time, match_num = match_data
        payload["matches"].append({
            "times": {
                "game": {
                    "start": datetime.fromtimestamp(match_time, tz=timezone.utc).isoformat()
                }
            },
            "num": match_num
        })

        payload["_debug"] = {"game_time": time() - match_time}
        payload["_debug"]["slot_time"] = payload["_debug"]["game_time"] + MATCH_CONFIG["pre"]
        if payload["_debug"]["game_time"] < 0:
            payload["_debug"]["match_phase"] = "pre"
        elif payload["_debug"]["game_time"] < MATCH_CONFIG["match"]:
            payload["_debug"]["match_phase"] = "match"
        else:
            payload["_debug"]["match_phase"] = "post"
        payload["time"] = datetime.now(timezone.utc).isoformat()
        self.wfile.write(json.dumps(payload).encode())
        LOGGER.info(f"Match {match_num}, match time: {payload['_debug']['game_time']:.3f}")


def run(args: argparse.Namespace) -> None:
    """Run the test server."""
    global _CONFIG
    server_address = ("127.0.0.1", args.port)
    _CONFIG = ServerConf(
        start_num=args.start_match,
        end_num=args.end_match,
        start_time=time() + args.start_delay,
    )
    first_match = datetime.fromtimestamp(
        _CONFIG.start_time + MATCH_CONFIG["pre"],
        timezone.utc
    )
    LOGGER.info(f"First match starts at {first_match}")

    httpd = HTTPServer(server_address, ServerHandler)

    LOGGER.info(f"Starting httpd on port {args.port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Exiting")


def parse_args() -> argparse.Namespace:
    """Parse command-line args."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p", "--port", help="The port to bind the server to.", type=int, default=8008)
    parser.add_argument(
        "--start-delay", type=float, default=0, help="Seconds to wait before starting matches")
    parser.add_argument(
        "--start-match", type=int, default=0,
        help="The match number to use for the first match")
    parser.add_argument("--end-match", type=int, default=None, help="The highest match to run")

    return parser.parse_args()


def init_logging() -> None:
    """Setup default logging."""
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")


if __name__ == "__main__":
    init_logging()
    run(parse_args())
