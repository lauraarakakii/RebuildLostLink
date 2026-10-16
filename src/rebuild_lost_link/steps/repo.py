"""Step ``repo``: make sure the Linux Git repository is available."""

from __future__ import annotations

import dataclasses

from ..config import Config
from ..repo_setup import ensure_repo


def main(config: Config, force: bool = False) -> None:
    """Validate the clone at ``paths.repo_path``, cloning it when allowed.

    Cloning happens when ``repo.auto_clone`` is true, or when ``force`` is set
    (an explicit user action overrides only ``auto_clone``). An existing clone
    is never touched.
    """
    repo_config = config.repo
    if force and not repo_config.auto_clone:
        repo_config = dataclasses.replace(repo_config, auto_clone=True)
    ensure_repo(repo_config, config.paths.repo_path)
