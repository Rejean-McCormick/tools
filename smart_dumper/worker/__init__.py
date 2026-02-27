# worker/__init__.py
"""
Worker package public API.

Keep external imports stable:
    from yourpkg.worker import DumpWorker
"""

from .dump_worker import DumpWorker

__all__ = ["DumpWorker"]