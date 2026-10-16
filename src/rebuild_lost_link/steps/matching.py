"""Step ``matching``: link patch emails to the commits that integrate them."""

from __future__ import annotations

from ..config import Config
from ..pipeline import run


def main(config: Config) -> None:
    """Write one match CSV per list, resuming from checkpoints when present."""
    run(config)
