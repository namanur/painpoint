"""
Allow running local_cli as a module: python -m local_cli
"""

from .main import intake

if __name__ == "__main__":
    intake()
