#!/usr/bin/env python3
"""
Universal Adhoc: Type Input Tool (Alias for write_input.py)
"""

from __future__ import annotations
import sys
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from server.templates.adhocs.write_input import main

if __name__ == "__main__":
    main()
