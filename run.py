#!/usr/bin/env python3
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from interfaces.cli import main

if __name__ == "__main__":
    sys.exit(main())

