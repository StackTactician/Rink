#!/usr/bin/env python3
"""Compatibility entry point. The implementation lives in the rink package.

Usage:
  python3 rink.py search "resident evil"
  python3 rink.py list [--type movie|series|drama] [--limit 20]
  python3 rink.py show <id-or-url>
  python3 rink.py download <id-or-url> [--out DIR] [--list]
  python3 rink.py open <id-or-url>

Equivalent: python3 -m rink <command>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rink.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
