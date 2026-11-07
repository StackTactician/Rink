#!/usr/bin/env python3
"""Compatibility entry point. The implementation lives in the nkiri package.

Usage:
  python3 nkiri.py search "resident evil"
  python3 nkiri.py list [--type movie|series|drama] [--limit 20]
  python3 nkiri.py show <id-or-url>
  python3 nkiri.py download <id-or-url> [--out DIR] [--list]
  python3 nkiri.py open <id-or-url>

Equivalent: python3 -m nkiri <command>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nkiri.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
