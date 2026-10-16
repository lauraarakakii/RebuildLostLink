"""Stages of the main execution: repository, matching and enrichment.

Each stage is its own module exposing ``main(config, ...)``;
:mod:`rebuild_lost_link.steps.main` orchestrates them in order.
"""
