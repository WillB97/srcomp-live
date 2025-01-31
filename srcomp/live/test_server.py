#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from math import floor
from typing import Any, NamedTuple


class ServerConf(NamedTuple):
    """Global configuration of the server."""

    start_time: datetime = datetime.now(timezone.utc)
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


def get_match(curr_time: datetime) -> tuple[datetime, int] | None:
    """Calculate match number and start time for the given time."""
    elapsed = curr_time - _CONFIG.start_time
    if elapsed.total_seconds() < 0:
        return None

    slot_length = sum(MATCH_CONFIG.values())
    match_num = floor(elapsed.total_seconds() / slot_length) + _CONFIG.start_num

    if _CONFIG.end_num and match_num > _CONFIG.end_num:
        return None

    match_start = match_num * slot_length + MATCH_CONFIG["pre"]
    match_time = _CONFIG.start_time + timedelta(seconds=match_start)

    return (match_time, match_num)


class ServerHandler(BaseHTTPRequestHandler):
    """Handler for HTTP requests."""

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
        match_data = get_match(datetime.now(timezone.utc))
        if match_data is None:
            # No match ongoing
            payload["time"] = datetime.now(timezone.utc).isoformat()
            self.wfile.write(json.dumps(payload).encode())
            return

        match_time, match_num = match_data
        payload["matches"].append({
            "times": {
                "game": {"start": match_time.isoformat()}
            },
            "num": match_num
        })

        now = datetime.now(timezone.utc)
        payload["_debug"] = {"game_time": (now - match_time).total_seconds()}
        payload["_debug"]["slot_time"] = payload["_debug"]["game_time"] + MATCH_CONFIG["pre"]
        if payload["_debug"]["game_time"] < 0:
            payload["_debug"]["match_phase"] = "pre"
        elif payload["_debug"]["game_time"] < MATCH_CONFIG["match"]:
            payload["_debug"]["match_phase"] = "match"
        else:
            payload["_debug"]["match_phase"] = "post"
        payload["time"] = now.isoformat()
        self.wfile.write(json.dumps(payload).encode())


def run(args: argparse.Namespace) -> None:
    """Run the test server."""
    global _CONFIG
    server_address = ("127.0.0.1", args.port)
    _CONFIG = ServerConf(
        start_num=args.start_match,
        end_num=args.end_match,
        start_time=datetime.now(timezone.utc) + timedelta(seconds=args.start_delay),
    )

    httpd = HTTPServer(server_address, ServerHandler)

    print(f"Starting httpd on port {args.port}...")
    httpd.serve_forever()


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


if __name__ == "__main__":
    run(parse_args())
