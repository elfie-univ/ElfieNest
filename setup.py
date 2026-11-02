"""Prepare ignored metadata storage before setuptools reads setup.cfg."""

from pathlib import Path

from setuptools import setup

Path(__file__).resolve().parent.joinpath("build", "metadata").mkdir(
    parents=True, exist_ok=True
)
setup()
