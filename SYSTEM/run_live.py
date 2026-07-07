#!/usr/bin/env python3
from __future__ import annotations

import sys

from engine.core.lifecycle import run_live_main


def main() -> int:
    return run_live_main()


if __name__ == "__main__":
    sys.exit(main())
