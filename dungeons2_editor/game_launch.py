"""Starting Minecraft Dungeons II from the editor.

The editor starts the copy of the game its open saves belong to. The Xbox app's copy (PC Game Pass and the
Microsoft Store) is started the way the Start menu starts it, from Windows' list of installed apps; Steam's is
started by Steam. Either way the editor only asks for the game to be started: it never runs the game's files
itself, and it adds nothing to how the game starts.
"""

from __future__ import annotations

import os
import subprocess
import sys

from .steam import STEAM_APP_ID

GAME = "Minecraft Dungeons II"
# The game's entry in Windows' list of apps, which is what its Start menu tile opens: the package's family name
# (the folder its saves are under, too) and the name of the app inside it.
XBOX_APP = "Microsoft.MinecraftDungeons2_8wekyb3d8bbwe!AppMinecraftDungeonsIIShipping"
APPS_FOLDER = "shell:AppsFolder\\"
STEAM_LINK = f"steam://rungameid/{STEAM_APP_ID}"
SHOPS = {"xbox": "the Xbox app", "steam": "Steam"}  # where each copy of the game is started by hand


class LaunchError(RuntimeError):
    """The game couldn't be started. The message says why, and where to start it instead."""


def target(layout: str | None, platform: str = sys.platform) -> str | None:
    """What to open to start the copy of the game that saves laid out this way belong to (``"xbox"`` or
    ``"steam"``, as ``saves.layout_of`` says), or None where the editor can't start it: no saves are open, the
    Xbox app's copy anywhere but on Windows, and Steam's on a Mac, where the game runs inside a Windows layer
    (CrossOver or Whisky) that has its own way of starting things."""
    if layout == "steam" and platform != "darwin":
        return STEAM_LINK
    if layout == "xbox" and platform == "win32":
        return APPS_FOLDER + XBOX_APP
    return None


def launch(layout: str | None, platform: str = sys.platform) -> None:
    """Start the game. Returns as soon as Windows or Steam has been asked; the game takes a moment to appear."""
    address = target(layout, platform)
    shop = SHOPS.get(layout or "", "the place you got it from")
    if address is None:
        raise LaunchError(f"The editor can't start the game from here. Start it from {shop}.")
    try:
        if platform == "win32":
            os.startfile(address)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", address], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError as exc:
        missing = "Steam doesn't seem to be installed" if layout == "steam" else f"Windows has no {GAME} from {shop} in its list of apps"
        raise LaunchError(f"{missing}, so the editor couldn't start the game. Start it from {shop}.") from exc
    except OSError as exc:
        raise LaunchError(f"The game didn't start ({exc}). Start it from {shop}.") from exc
