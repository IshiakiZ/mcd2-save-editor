"""Release step: writes the details Windows shows for the .exe (Properties > Details: product, version, who made
it), in the form PyInstaller's --version-file takes.

    python tools/make_version_info.py build/version-info.txt
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dungeons2_editor import __version__  # noqa: E402
from dungeons2_editor.paths import APP_NAME  # noqa: E402

EXE_NAME = "MCD2SaveEditor"
DETAILS = {
    "CompanyName": "Ishiaki",
    "FileDescription": APP_NAME,
    "FileVersion": __version__,
    "InternalName": EXE_NAME,
    "LegalCopyright": "Copyright (c) 2026 Ishiaki. MIT License.",
    "OriginalFilename": EXE_NAME + ".exe",
    "ProductName": APP_NAME,
    "ProductVersion": __version__,
    "Comments": "Unofficial fan project. Not affiliated with or endorsed by Mojang Studios or Microsoft.",
}


def version_info() -> str:
    numbers = tuple(int(part) for part in __version__.split(".")) + (0,) * 4
    strings = ", ".join(f"StringStruct({name!r}, {value!r})" for name, value in DETAILS.items())
    return (
        "VSVersionInfo(\n"
        f"  ffi=FixedFileInfo(filevers={numbers[:4]}, prodvers={numbers[:4]}, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
        "  kids=[\n"
        f"    StringFileInfo([StringTable('040904B0', [{strings}])]),\n"
        "    VarFileInfo([VarStruct('Translation', [1033, 1200])]),\n"
        "  ],\n"
        ")\n"
    )


if __name__ == "__main__":
    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(version_info(), encoding="utf-8")
    print(f"Wrote {target} for {APP_NAME} {__version__}")
