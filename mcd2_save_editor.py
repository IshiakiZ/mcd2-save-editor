"""Entry point for the packaged .exe; also runs the editor from source (python mcd2_save_editor.py)."""

import os
import sys

if sys.stdout is None:  # the windowed .exe has no console to print to
    sys.stdout = sys.stderr = open(os.devnull, "w")

from dungeons2_editor.cli import main  # noqa: E402

raise SystemExit(main())
