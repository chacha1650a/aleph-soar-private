"""Create an isolated team environment and verify the scaffold."""

import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info < (3, 12):
        raise SystemExit("Python 3.12 or newer is required; 3.13 is used in CI.")
    environment = ROOT / ".venv"
    if not environment.resolve().is_relative_to(ROOT):
        raise SystemExit("The .venv path must stay inside this repository.")
    if environment.exists() and not (environment / "pyvenv.cfg").is_file():
        raise SystemExit("Existing .venv is not a virtual environment; left untouched.")
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executable.is_file():
        raise SystemExit("Existing .venv has no interpreter for this operating system.")
    commands = [
        [str(executable), "-m", "pip", "install", "-r", "requirements-dev.lock"],
        [str(executable), "-m", "pip", "install", "--no-deps", "--no-build-isolation", "-e", "."],
        [str(executable), "-m", "pytest", "-q"],
    ]
    try:
        for command in commands:
            subprocess.run(command, cwd=ROOT, check=True)
    except subprocess.CalledProcessError as error:
        return error.returncode
    print("Workspace verified. Use the .venv interpreter for development commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
