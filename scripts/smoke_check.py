"""Deterministic release check used by CD: hit a URL N times and fail if too many requests error.

Usage: python -m scripts.smoke_check --url http://localhost:8000/health --requests 20
"""

import argparse
import sys
import time
import urllib.error
import urllib.request


def wait_until_up(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(1)
    return False


def error_rate(url: str, requests: int) -> float:
    errors = 0
    for _ in range(requests):
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status >= 500:
                    errors += 1
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            errors += 1
    return errors / requests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    parser.add_argument("--startup-timeout", type=float, default=30)
    args = parser.parse_args(argv)

    if not wait_until_up(args.url, args.startup_timeout):
        print(f"FAIL: {args.url} never came up")
        return 1
    rate = error_rate(args.url, args.requests)
    print(f"error rate {rate:.0%} over {args.requests} requests (max {args.max_error_rate:.0%})")
    return 0 if rate <= args.max_error_rate else 1


if __name__ == "__main__":
    sys.exit(main())
