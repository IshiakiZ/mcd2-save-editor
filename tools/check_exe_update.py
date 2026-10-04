"""Release check: the built editor can replace an older copy of itself, which is what the Update button ends with.

    python tools/check_exe_update.py dist/MCD2SaveEditor

Makes an "installed" copy and a "downloaded" copy of the built folder, then has the downloaded copy's own
apply-update command swap the installed one for itself, and checks the result still runs.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXE = "MCD2SaveEditor.exe"


def main(built: str) -> int:
    source = Path(built).resolve()
    work = Path(tempfile.mkdtemp())
    installed = work / "Games" / source.name
    downloaded = work / "update" / source.name
    shutil.copytree(source, installed)
    shutil.copytree(source, downloaded)
    (installed / "only in the old version.txt").write_text("gone after the update")
    (downloaded / "only in the new version.txt").write_text("there after the update")

    run = subprocess.run([str(downloaded / EXE), "apply-update", "--target", str(installed), "--no-restart", "--wait", "30"], timeout=300)
    problems = []
    if run.returncode != 0:
        problems.append(f"apply-update exited with code {run.returncode}")
    if not (installed / "only in the new version.txt").is_file():
        problems.append("the new version's files aren't in the installed folder")
    if (installed / "only in the old version.txt").exists():
        problems.append("the old version's files are still in the installed folder")
    left = sorted(path.name for path in installed.parent.iterdir())
    if left != [source.name]:
        problems.append(f"something was left next to the installed folder: {left}")
    if not problems and subprocess.run([str(installed / EXE), "items"], timeout=300).returncode != 0:
        problems.append("the replaced editor doesn't run")
    shutil.rmtree(work, ignore_errors=True)
    if problems:
        print("The editor couldn't replace an older copy of itself: " + "; ".join(problems))
        return 1
    print("OK: the editor replaces an older copy of itself, and the result runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
