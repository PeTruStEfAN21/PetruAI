"""Shared fixtures: the `gpu` marker runs only with PETRU_GPU=1 (needs the RTX and the base weights)."""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("PETRU_GPU") == "1":
        return
    skip = pytest.mark.skip(reason="set PETRU_GPU=1 to run GPU tests")
    for item in items:
        if "gpu" in item.keywords:
            item.add_marker(skip)
