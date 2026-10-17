"""Git worktree isolation for agent(isolation="worktree")."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

worktree_path: ContextVar[Path | None] = ContextVar(
    "dialectica_workflow_worktree", default=None
)


class WorkflowWorktreeError(RuntimeError):
    """Raised when worktree isolation cannot be established."""


@dataclass
class _WorktreeHandle:
    path: Path
    branch: str
    dirty: bool = False


def _run_git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _repo_root() -> Path:
    result = _run_git("rev-parse", "--show-toplevel")
    if result.returncode != 0:
        raise WorkflowWorktreeError(
            "isolation='worktree' requires a git repository — "
            f"git rev-parse failed: {result.stderr.strip()}"
        )
    return Path(result.stdout.strip())


def _sanitize_label(label: str) -> str:
    sanitized = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)
    return sanitized[:40] or "agent"


@asynccontextmanager
async def worktree_session(
    *,
    label: str,
    run_id: str,
) -> AsyncIterator[_WorktreeHandle]:
    """Expose an absolute task-local path; never change the process cwd.

    Host tools must use worktree_path.get() explicitly (e.g. subprocess cwd).
    Worktrees isolate Git changes, not OS authority. Keep on status errors.
    """
    root = _repo_root()
    safe_label = _sanitize_label(label)
    short_id = run_id.replace("-", "")[:8]
    branch = f"wf_{safe_label}_{short_id}_{uuid.uuid4().hex[:8]}"
    tmp = Path(tempfile.mkdtemp(prefix=f"wf_{safe_label}_"))
    add = _run_git("worktree", "add", "-b", branch, str(tmp), cwd=root)
    if add.returncode != 0:
        shutil.rmtree(tmp)
        raise WorkflowWorktreeError(
            f"git worktree add failed: {add.stderr.strip() or add.stdout.strip()}"
        )
    handle = _WorktreeHandle(path=tmp, branch=branch)
    token = worktree_path.set(tmp)
    try:
        yield handle
    finally:
        worktree_path.reset(token)
        status = _run_git("status", "--porcelain", cwd=tmp)
        handle.dirty = status.returncode != 0 or bool(status.stdout.strip())
        if handle.dirty:
            logger.info("Worktree %s has changes; keeping at %s", branch, tmp)
        else:
            remove = _run_git("worktree", "remove", str(tmp), "--force", cwd=root)
            if remove.returncode != 0:
                logger.warning(
                    "git worktree remove failed for %s: %s",
                    tmp,
                    remove.stderr.strip(),
                )
