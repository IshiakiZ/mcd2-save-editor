"""Release check: the built .exe answers as an MCP server over stdin and stdout.

    python tools/check_exe_mcp.py dist/MCD2SaveEditor.exe
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.helpers import hero_save_text, make_profile  # noqa: E402


def main(exe: str) -> int:
    folder = Path(tempfile.mkdtemp())
    profile = make_profile(folder / "saves", {"Character00000000-0000-1000-8000-000000000002": hero_save_text().encode()})
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_hero", "arguments": {"hero": "00000000"}}},
    ]
    run = subprocess.run(
        [exe, "mcp", "--profile", str(profile), "--backups", str(folder / "backups")],
        input="".join(json.dumps(message) + "\n" for message in messages).encode(),
        capture_output=True,
        timeout=120,
    )
    replies = [json.loads(line) for line in run.stdout.splitlines() if line.strip()]
    ids = [reply.get("id") for reply in replies]
    if ids != [1, 2, 3]:
        print(f"Expected replies 1, 2 and 3, got {ids}\nstdout: {run.stdout!r}\nstderr: {run.stderr!r}")
        return 1
    tools = {tool["name"] for tool in replies[1]["result"]["tools"]}
    hero = json.loads(replies[2]["result"]["content"][0]["text"])
    if "save_changes" not in tools or hero.get("name") != "Ranger Deluxe":
        print(f"Unexpected answers: tools {sorted(tools)}, hero {hero}")
        return 1
    print(f"OK: the .exe answers as an MCP server ({len(tools)} tools)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
