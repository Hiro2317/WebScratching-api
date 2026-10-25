"""Entry point used by PyInstaller to build a standalone executable.

Equivalent to running `python -m cinema_scraper.cli`.
"""
import sys

from cinema_scraper.cli import main

if __name__ == "__main__":
    sys.exit(main())
