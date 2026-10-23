"""Compatibility import package for the relocated backend application."""

from pathlib import Path


__path__ = [
    str(Path(__file__).resolve().parent.parent / "backend" / "app")
]
