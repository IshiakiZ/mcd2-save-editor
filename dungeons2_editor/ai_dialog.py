"""The "Connect an AI" window: how to let an AI assistant use the editor's MCP server (mcp_server.py)."""

from __future__ import annotations

import json
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .game_style import match_title_bar
from .layout import fit_to_contents, text_width
from .mcp_server import SERVER_NAME

INTRO = (
    "AI assistants that support MCP, like Claude Desktop and Claude Code, can use the editor to look at your heroes "
    "and change them for you: ask for 9,999 emeralds, a Unique sword or the Melee damage kit. The assistant sees your "
    "heroes' stats and items (not your sign-in or account details), collects its changes as a draft, and writes them "
    "only when you agree, with the game closed and your saves backed up first, just like Save to game here."
)


def server_command() -> list[str]:
    """How an assistant's app starts the editor's MCP server: this .exe, or this Python and the editor's script."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "mcp"]
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe" and python.with_name("python.exe").is_file():
        python = python.with_name("python.exe")  # the assistant talks to it over stdin and stdout
    return [str(python), str(Path(__file__).resolve().parent.parent / "mcd2_save_editor.py"), "mcp"]


def desktop_config(command: list[str]) -> str:
    """The part to add to Claude Desktop's claude_desktop_config.json."""
    return json.dumps({"mcpServers": {SERVER_NAME: {"command": command[0], "args": command[1:]}}}, indent=2)


def claude_code_command(command: list[str]) -> str:
    return subprocess.list2cmdline(["claude", "mcp", "add", SERVER_NAME, "--", *command])


class ConnectAiDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("Connect an AI assistant")
        self.transient(parent)
        match_title_bar(self)
        command = server_command()
        self.sections = {
            "desktop": desktop_config(command),
            "code": claude_code_command(command),
            "other": subprocess.list2cmdline(command),
        }
        wrap = text_width(self, 86)
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=INTRO, wraplength=wrap, justify="left").grid(row=0, column=0, columnspan=2, sticky="w")
        row = 1
        for key, heading, how in (
            ("desktop", "Claude Desktop", "In Claude Desktop, open Settings → Developer → Edit Config, add this to the file "
             "(inside \"mcpServers\" if it already has one), save it and restart Claude Desktop."),
            ("code", "Claude Code", "Run this in a terminal:"),
            ("other", "Other apps", "Any app that can start an MCP server over stdio (standard input and output) can run:"),
        ):
            ttk.Label(frame, text=heading, style="Heading.TLabel").grid(row=row, column=0, sticky="w", pady=(14, 2))
            ttk.Label(frame, text=how, style="Muted.TLabel", wraplength=wrap, justify="left").grid(row=row + 1, column=0, columnspan=2, sticky="w")
            lines = self.sections[key].count("\n") + 1 if key == "desktop" else 2  # commands wrap; Copy copies them whole
            text = tk.Text(frame, height=lines, wrap="none" if key == "desktop" else "char", font=("Consolas", 10), relief="flat", padx=6, pady=4)
            text.insert("1.0", self.sections[key])
            text.configure(state="disabled")
            text.grid(row=row + 2, column=0, sticky="ew", pady=(4, 0))
            ttk.Button(frame, text="Copy", command=lambda key=key: self.copy(key)).grid(row=row + 2, column=1, sticky="n", padx=(8, 0), pady=(4, 0))
            row += 3
        bottom = ttk.Frame(frame)
        bottom.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        self.message = tk.StringVar()
        ttk.Label(bottom, textvariable=self.message, style="Success.TLabel").pack(side="left")
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda _event: self.destroy())
        fit_to_contents(self, 760, 0)

    def copy(self, key: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.sections[key])
        self.message.set("Copied.")
