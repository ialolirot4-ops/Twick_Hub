"""Shared test fixtures.

Sets ``QT_QPA_PLATFORM=offscreen`` before anything imports Qt, so the whole
suite runs without a display — this container, CI, either one.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from twitchlink_next.bootstrap.container import Container
from twitchlink_next.bootstrap.dependencies import build_container
from twitchlink_next.config.settings import AppConfig


@pytest.fixture
def config(tmp_path) -> AppConfig:
    return AppConfig(data_dir=tmp_path, database_url=f"sqlite:///{tmp_path}/test.db")


@pytest.fixture
def container(config: AppConfig) -> Container:
    return build_container(config)
