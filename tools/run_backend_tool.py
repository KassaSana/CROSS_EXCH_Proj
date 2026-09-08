from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_backend_tool.py MODULE [ARGS...]", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[1]
    executable = "python.exe" if os.name == "nt" else "python"
    python = root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / executable
    if not python.is_file():
        print("backend environment missing; run `uv sync --locked --extra dev`", file=sys.stderr)
        return 2

    result = subprocess.run(
        [str(python), "-m", *sys.argv[1:]],
        cwd=root,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
