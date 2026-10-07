"""Child-process bookkeeping.

Unreal tools start process trees (UnrealBuildTool -> compilers, the editor -> shader
workers). Killing only the parent leaves the rest running, so every process the studio
starts is registered here and terminated as a tree on timeout, cancellation and shutdown.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys

log = logging.getLogger(__name__)
_children: set[int] = set()


def register(pid: int) -> None:
    _children.add(pid)


def unregister(pid: int) -> None:
    _children.discard(pid)


def kill_tree(pid: int) -> None:
    """Terminate a process and everything it started. Safe to call for a process that already exited."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)
        else:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError, ProcessLookupError) as e:
        log.debug("kill_tree(%s): %s", pid, e)
    finally:
        unregister(pid)


def kill_all() -> int:
    """Called on shutdown: nothing the studio started may outlive it."""
    pids = list(_children)
    for pid in pids:
        kill_tree(pid)
    return len(pids)


def active() -> list[int]:
    return sorted(_children)
