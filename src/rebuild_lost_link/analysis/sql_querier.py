"""Interactive SQL over the ``original`` and ``enriched`` Parquet tables.

Powered by Apache DataFusion (see :mod:`rebuild_lost_link.analysis.query`).
Without SQL it opens a REPL that lists the available tables and schemas, then
prompts for queries; with ``sql`` it runs a single query and exits. This is a
non-default analysis: it only runs when explicitly selected.
"""

from __future__ import annotations

from ..config import Config
from .query import run


def main(
    config: Config,
    output_dir: str,
    list_name: str = "all",
    sql: str | None = None,
    output: str | None = None,
    fmt: str | None = None,
    limit: int = 20,
) -> None:
    """Run one SQL query (``sql``) or open the REPL (``sql`` omitted).

    ``output_dir`` is accepted for the common analysis signature; results are
    only saved when ``output`` is given (format inferred from its extension, or
    ``fmt``).
    """
    run(config, sql, list_name=list_name, output=output, fmt=fmt, limit=limit)
