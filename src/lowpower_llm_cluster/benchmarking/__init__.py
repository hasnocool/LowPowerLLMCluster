# src/lowpower_llm_cluster/benchmarking/__init__.py
"""Measured-performance benchmark harness for heterogeneous inference hardware."""

from .runner import run_profile

__all__ = ["run_profile"]
