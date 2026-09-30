"""Dump the readable Angelscript caches shipped with Minecraft Dungeons II (codename "Spicewood").

The game's 8.4 GB of assets are AES-encrypted IoStore containers, but three script caches ship in
plaintext next to them. This script extracts what they expose:

  data/game_schema.txt    every game-specific C++ class/struct bound to script, with fields and functions
  data/script_modules.txt every Angelscript module (.as file) compiled into the game
  data/cpp_headers.txt    the C++ header tree referenced by the bindings

Read-only: nothing in the game install is modified.

Usage:  python mcd2_script_dump.py ["C:\\XboxGames\\Minecraft Dungeons II"]
"""
import os
import re
import sys

DEFAULT_INSTALL = r"C:\XboxGames\Minecraft Dungeons II"
GAME_MODULE = re.compile(
    r"^/Script/(Dungeons|Spicewood\w*|SW\w+|QuestsFeature|InventorySystem|Achievements|"
    r"WorldTiles|Minimap|Onboarding|WorldMesh|UIStateContainer|WorldTimeOfDay)\."
)


def length_prefixed_strings(data):
    """Yield strings stored as int32 length (including NUL) followed by the NUL-terminated text."""
    for m in re.finditer(rb"[\x20-\x7e]{2,}\x00", data):
        start = m.start()
        if start >= 4 and int.from_bytes(data[start - 4:start], "little") == m.end() - start:
            yield m.group()[:-1].decode("ascii")


def parse_binds(data):
    """Group the bind cache into classes: '/Script/Module.Class' starts a record, followed by
    property declarations ('Type Name') and function signatures ('Ret Name(args)')."""
    classes, current, previous = [], None, None
    for s in length_prefixed_strings(data):
        if s.startswith("/Script/"):
            current = {"name": previous, "path": s, "props": [], "funcs": []}
            classes.append(current)
        elif current is not None and " " in s and not s.startswith("/"):
            if "(" in s:
                current["funcs"].append(s)
            elif re.match(r"^[\w:<>,\* ]+ \w+$", s):
                current["props"].append(s)
        previous = s
    return classes


def main():
    install = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INSTALL
    script_dir = os.path.join(install, "Content", "Dungeons", "Script")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(script_dir, "Binds.Cache"), "rb") as f:
        classes = [c for c in parse_binds(f.read()) if GAME_MODULE.match(c["path"])]
    with open(os.path.join(out_dir, "game_schema.txt"), "w", encoding="utf-8") as out:
        for c in sorted(classes, key=lambda c: c["path"]):
            out.write(f"### {c['name']}  ({c['path']})\n")
            out.writelines(f"    {p}\n" for p in c["props"])
            out.writelines(f"    fn {fn}\n" for fn in c["funcs"])

    with open(os.path.join(script_dir, "PrecompiledScript.Cache"), "rb") as f:
        text = f.read()
    modules = sorted({m.decode() for m in re.findall(rb"[\w/]+\.as(?=\x00)", text)})
    with open(os.path.join(out_dir, "script_modules.txt"), "w", encoding="utf-8") as out:
        out.writelines(f"{m}\n" for m in modules)

    with open(os.path.join(script_dir, "Binds.Cache.Headers"), "rb") as f:
        headers = sorted({re.sub(r"^(\.\./)+", "", h) for h in length_prefixed_strings(f.read())
                          if h.endswith(".h") and "/Spicewood/" in h})
    with open(os.path.join(out_dir, "cpp_headers.txt"), "w", encoding="utf-8") as out:
        out.writelines(f"{h}\n" for h in headers)

    print(f"{len(classes)} game classes, {len(modules)} script modules, {len(headers)} headers -> {out_dir}")


if __name__ == "__main__":
    main()
