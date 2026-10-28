"""Test-only server: create_folder makes its change, then hangs before the result is recorded.

Used to kill the process in the worst possible window (side effect done,
outcome not yet saved) and prove restart recovery reports it honestly.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import uvicorn  # noqa: E402

from app.tools.filesystem import CreateFolderTool  # noqa: E402

_real = CreateFolderTool.execute


def _change_then_hang(self, args):
    result = _real(self, args)
    time.sleep(120)
    return result


CreateFolderTool.execute = _change_then_hang

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
