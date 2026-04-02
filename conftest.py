"""Root conftest.py for the git worktree at .worktrees/fix/vocab-service.

This conftest ensures that Python imports resolve to *this* worktree's source
tree rather than the main workspace's /app/src (which is registered in the
shared .venv/lib/.../coda.pth editable install).
"""

import sys
from pathlib import Path

# Prepend the worktree's src/ so it takes precedence over /app/src on sys.path.
_worktree_src = str(Path(__file__).parent / "src")
if _worktree_src not in sys.path:
    sys.path.insert(0, _worktree_src)
