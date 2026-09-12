"""
OpenHands Nexus Unified Test Suite Runner.
Usage:
    python tests/runner.py              (Runs unit and integration tests)
    python tests/runner.py --all        (Runs unit, integration, and hardware tests)
    python tests/runner.py --unit       (Runs fast unit tests)
    python tests/runner.py --integration (Runs service integration tests)
    python tests/runner.py --hardware   (Runs CUDA, VRAM, and model inference tests)
"""

import sys
import os
import argparse
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description="OpenHands Nexus Test Runner")
    parser.add_argument("--all", action="store_true", help="Run all tests (unit, integration, hardware)")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--hardware", action="store_true", help="Run hardware and inference tests only")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args, unknown = parser.parse_known_args()

    test_dirs = []
    if args.all:
        test_dirs = ["tests/unit", "tests/integration", "tests/hardware"]
    elif args.unit:
        test_dirs = ["tests/unit"]
    elif args.integration:
        test_dirs = ["tests/integration"]
    elif args.hardware:
        test_dirs = ["tests/hardware"]
    else:
        # Default suite: unit + integration
        test_dirs = ["tests/unit", "tests/integration"]

    pytest_args = ["-v" if args.verbose else "-q", "--tb=short"]
    for td in test_dirs:
        p = PROJECT_ROOT / td
        if p.exists():
            pytest_args.append(str(p))

    if unknown:
        pytest_args.extend(unknown)

    print("\n" + "=" * 68)
    print("           OpenHands Nexus — Automated Test Runner")
    print(f" Suites: {', '.join(test_dirs)}")
    print("=" * 68 + "\n")

    pytest_args.extend(["-c", str(PROJECT_ROOT / "pyproject.toml"), "--rootdir", str(PROJECT_ROOT)])
    exit_code = pytest.main(pytest_args)

    print("\n" + "=" * 68)
    if exit_code == 0:
        print(" [PASSED] All selected test suites passed successfully.")
    else:
        print(f" [FAILED] Test run failed with exit code: {exit_code}")
    print("=" * 68 + "\n")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
