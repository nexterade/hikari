"""Refresh a project status display until interrupted."""
from __future__ import annotations
import os
import time
from typing import Callable

def watch(render: Callable[[], str], interval: int = 2, sleep: Callable[[float], None] = time.sleep, clear: bool = True) -> None:
    if not 1 <= interval <= 60: raise ValueError("interval must be between 1 and 60 seconds")
    try:
        while True:
            if clear and "NO_COLOR" not in os.environ: print("\033[2J\033[H", end="")
            print(render()); print(f"WATCH MODE — refresh tiap {interval}s · Ctrl+C untuk stop", flush=True); sleep(interval)
    except KeyboardInterrupt: print("\nWatch stopped.")
