"""Start Token Saver with python app.py, using the project's environment."""
from pathlib import Path
import os
import subprocess
import sys


def main():
    project = Path(__file__).resolve().parent
    os.chdir(project)
    environment = project / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if python.is_file() and Path(sys.prefix).resolve() != environment.resolve():
        try:
            return subprocess.call([str(python), "-m", "token_saver", *sys.argv[1:]])
        except KeyboardInterrupt:
            return 130
    try:
        from token_saver.cli import main as launch
    except ModuleNotFoundError:
        launcher = r".\start.bat" if os.name == "nt" else "sh start.sh"
        print(f"Dependencies are not installed. Run {launcher} once, then use python app.py.", file=sys.stderr)
        return 1
    launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
