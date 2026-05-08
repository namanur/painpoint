"""
conftest.py for pytest

Adds the project root to sys.path so that imports like 'from src.xxx import yyy' work.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Ensure src directory is also in path
src_path = project_root / "src"
if src_path.exists() and str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Set PYTHONPATH environment variable for subprocesses
import os
os.environ["PYTHONPATH"] = str(project_root)
