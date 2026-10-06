"""Command line interface. Run ``python -m dungeons2_editor --help``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import document as doc
from . import saves, wgs


def _pick_profile(explicit: Path | None) -> saves.SaveProfile:
    if explicit is not None:
        return saves.SaveProfile(explicit)
    profiles = saves.find_profiles()
    if not profiles:
        raise SystemExit("No Minecraft Dungeons II saves found. Use --profile to point at a save folder (Xbox: has containers.index; Steam: has Character….sav files).")
    return saves.SaveProfile(profiles[0])


def _editable(profile: saves.SaveProfile, name: str) -> saves.Container:
    container = profile.get(name)
    if container is None:
        raise SystemExit(f"No container named {name!r}. Run the 'list' command to see them.")
    if container.kind is not saves.Kind.EDITABLE:
        raise SystemExit(f"{name} is {container.kind.value.lower()}: {container.note}")
    return container


def _confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def cmd_list(args: argparse.Namespace) -> int:
    profile = _pick_profile(args.profile)
    print(f"Profile: {profile.path}  ({'Steam' if profile.is_steam else 'Xbox app'} layout)")
    for container in profile.containers:
        entry = container.entry
        if profile.is_steam:
            print(f"  {container.name:<28} {container.kind.value:<10} {entry.size:>9,} bytes  {container.note}")
        else:
            sync = wgs.SYNC_STATE_NAMES.get(entry.sync_state, str(entry.sync_state))
            print(f"  {container.name:<28} {container.kind.value:<10} rev {entry.revision:<4} {entry.size:>9,} bytes  {sync}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    container = _editable(_pick_profile(args.profile), args.container)
    output = args.output or Path(f"{container.name}.json")
    output.write_text(json.dumps(container.decoded.document, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {output}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    profile = _pick_profile(args.profile)
    container = _editable(profile, args.container)
    document = json.loads(args.input.read_text(encoding="utf-8"))
    changes = doc.diff(container.decoded.document, document)
    if not changes:
        print("No differences; nothing to save.")
        return 0
    for path, old, new in changes[:40]:
        where = doc.describe_path(container.decoded.document if new is doc.MISSING else document, path)
        print(f"  {where}: {doc.format_value(old)} -> {doc.format_value(new)}")
    if len(changes) > 40:
        print(f"  ... and {len(changes) - 40} more")
    if not _confirm(f"Write {len(changes)} change(s) to {container.name}?", args.yes):
        print("Cancelled.")
        return 1
    backup = profile.save(container.name, document, args.backups)
    print(f"Saved. Previous version backed up to {backup}")
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    profile = _pick_profile(args.profile)
    print(f"Backed up to {saves.make_backup(profile.path, args.backups)}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    profile = _pick_profile(args.profile)
    backups = {backup.path.resolve(): backup for backup in saves.list_backups(args.backups)}
    backup = backups.get(args.backup.resolve())
    if backup is None:
        raise SystemExit(f"{args.backup} is not a backup made by this editor (looked in {args.backups}).")
    if not _confirm(f"Restore the save data from {backup.created:%Y-%m-%d %H:%M:%S} ({backup.reason})?", args.yes):
        print("Cancelled.")
        return 1
    problems = profile.restore_problems(backup)
    restored = profile.restore(backup, args.backups)
    if restored:
        print(f"Restored: {', '.join(restored)}")
    elif not problems:
        print("Nothing to restore: the backup matches the current save data.")
    for problem in problems:
        print(f"Not put back: {problem}")
    return 0 if restored or not problems else 1


def cmd_pictures(args: argparse.Namespace) -> int:
    from . import edition, icons, wiki

    if not edition.ONLINE:
        print(edition.offline_note("download pictures") + " Put your own in the icons folder, or paste them in the editor.")
        return 1
    pictures = wiki.list_pictures()
    folder = icons.IconLibrary(args.icons).ensure_folder() / "wiki"
    size = sum(picture.size for picture in pictures) / 1e6
    if not _confirm(f"Download {len(pictures)} item pictures ({size:.1f} MB) from minecraft.wiki into {folder}?", args.yes):
        print("Cancelled.")
        return 1

    def progress(number: int, total: int, name: str) -> None:
        print(f"\r  {number}/{total}  {name[:40]:<40}", end="", flush=True)

    downloaded, skipped = wiki.download_pictures(pictures, folder, progress)
    print(f"\nDownloaded {downloaded} pictures; {skipped} were already there.")
    return 0


def cmd_items(args: argparse.Namespace) -> int:
    """Every item the editor knows, with its ID and whether that ID has been seen in a real save."""
    from .hero import effect_book, enchantments, game_items

    items = game_items()
    for item in items:
        unique = f"  (Unique: {item.unique})" if item.unique else ""
        print(f"{item.kind:<9} {item.name:<32} {item.id:<44} {'confirmed' if item.confirmed else 'unconfirmed'}{unique}")
    print(f"{len(items)} items, {sum(item.confirmed for item in items)} with confirmed IDs, and {len(enchantments())} enchantments.")
    book = effect_book()
    print(
        f"{len({choice.effect for choice in book.effects})} gear effects ({len(book.effects)} tiers) and "
        f"{len({choice.effect for choice in book.enchantments})} enchantments ({len(book.enchantments)} tiers) that can be put on an item."
    )
    uniques = [item for item in items if item.unique]
    print(f"{sum(item.unique_own is not None for item in uniques)} of {len(uniques)} Uniques come with the effect of their own.")
    return 0 if items and enchantments() and book.effects and book.enchantments else 1


def cmd_verify(args: argparse.Namespace) -> int:
    """Check, without writing anything, that every editable container re-encodes byte for byte."""
    profile = _pick_profile(args.profile)
    ok = True
    if not profile.is_steam:
        index_bytes = (profile.path / wgs.INDEX_FILE).read_bytes()
        ok = wgs.serialize_index(wgs.parse_index(index_bytes)) == index_bytes
        print(f"containers.index round trip: {'exact' if ok else 'DIFFERENT'}")
    for container in profile.containers:
        if container.kind is saves.Kind.EDITABLE:
            exact = container.decoded.exact
            ok &= exact
            print(f"  {container.name}: {'exact' if exact else 'formatting would change'}")
        else:
            print(f"  {container.name}: {container.kind.value.lower()}, skipped")
    return 0 if ok else 1


def cmd_ids(args: argparse.Namespace) -> int:
    """The item IDs in your saves that the editor doesn't know yet, to share on GitHub."""
    from . import __version__
    from .share_ids import ISSUE_URL, report_text

    profile = _pick_profile(args.profile)
    report = report_text([c.hero for c in profile.containers if c.hero is not None], __version__)
    if not report:
        print("Everything in your saves is already in the editor's list.")
        return 0
    print(report)
    print(f"\nAdd what the game calls each item after the dash, and post it at {ISSUE_URL} (only item IDs and talisman effects, nothing else).")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """Run as an MCP server on stdin and stdout, for an AI assistant's app to start."""
    from .mcp_server import serve

    return serve(args.profile, args.backups)


def cmd_update(args: argparse.Namespace) -> int:
    """Look for a newer version on GitHub and install it, like the window's Update button."""
    from . import __version__, edition, updater

    if not edition.ONLINE:
        print(edition.offline_note("look for updates") + f" New versions are on {edition.NAME}.")
        return 1
    release = updater.check()
    if release is None:
        print(f"You have the latest version ({__version__}), or GitHub couldn't be reached.")
        return 0
    target = updater.app_dir()
    if target is None:
        print(f"Version {release.version} is out: {release.page}\nRun from source, the editor can't replace itself.")
        return 0
    if not _confirm(f"Update from {__version__} to {release.version} ({release.size / 1e6:.0f} MB from GitHub)?", args.yes):
        print("Cancelled.")
        return 1
    try:
        staged = updater.stage(release)
        updater.start_swap(staged, target, restart=not args.no_restart)
    except (updater.UpdateError, OSError) as exc:
        print(f"The update couldn't be installed: {exc}", file=sys.stderr)
        return 1
    print(f"Version {release.version} is downloaded and checked. It replaces this one as soon as this closes.")
    return 0


def cmd_apply_update(args: argparse.Namespace) -> int:
    """Swap the editor's folder for the new copy this runs from. The Update button starts it; see updater.py."""
    from . import updater

    try:
        updater.apply_update(args.target, Path(sys.executable).resolve().parent, wait=args.wait, restart=not args.no_restart)
    except updater.UpdateError as exc:
        print(exc, file=sys.stderr)
        if not args.no_restart:
            _update_failed(str(exc), args.target)
        return 1
    return 0


def _update_failed(why: str, target: Path) -> None:
    """Say why (this runs without a console), and open the editor that's still there."""
    import tkinter as tk
    from tkinter import messagebox

    from . import updater

    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("MCD2 Save Editor", f"The update couldn't be installed.\n\n{why}\n\nYou can download the new version from {updater.RELEASES_PAGE}", parent=root)
    root.destroy()
    if (Path(target) / updater.EXE_NAME).is_file():
        updater._start([str(Path(target) / updater.EXE_NAME)], Path(target).parent)


def main(argv: list[str] | None = None) -> int:
    # The folder options work before or after the command: "--profile X list" and "list --profile X".
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--profile", type=Path, default=argparse.SUPPRESS, help="save folder: contains containers.index (Xbox app) or Character….sav files (Steam). Default: auto-detect")
    shared.add_argument("--backups", type=Path, default=argparse.SUPPRESS, help="where backups are kept")
    shared.add_argument("--icons", type=Path, default=argparse.SUPPRESS, help="folder of item pictures")
    parser = argparse.ArgumentParser(prog="dungeons2_editor", description="Minecraft Dungeons II save editor.", parents=[shared])
    commands = parser.add_subparsers(dest="command", metavar="command")

    def command(name: str, help: str) -> argparse.ArgumentParser:
        return commands.add_parser(name, help=help, parents=[shared])

    gui_command = command("gui", "open the editor window (default)")
    gui_command.add_argument("--close-after", type=float, metavar="SECONDS", help="close the window again after this long (for testing a build)")
    command("list", "list the save containers")
    export = command("export", "write a container's data to a JSON file")
    export.add_argument("container")
    export.add_argument("output", nargs="?", type=Path)
    import_ = command("import", "save a JSON file into a container (makes a backup first)")
    import_.add_argument("container")
    import_.add_argument("input", type=Path)
    import_.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    command("backup", "back up the whole save folder")
    restore = command("restore", "put back the save data from a backup folder")
    restore.add_argument("backup", type=Path)
    restore.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    command("verify", "check that saves re-encode exactly (writes nothing)")
    command("items", "list every item the editor can add, with its ID")
    command("ids", "list the item IDs in your saves that the editor doesn't know yet, to share")
    command("mcp", "run as an MCP server (stdin/stdout) so an AI assistant can customise your heroes")
    pictures = command("pictures", "download item pictures from minecraft.wiki into the icons folder")
    pictures.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    update = command("update", "look for a newer version on GitHub and install it")
    update.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    update.add_argument("--no-restart", action="store_true", help="don't open the editor when it's done")
    # Not for people to run: the Update button starts the new copy with it, to replace the old one.
    apply_update = commands.add_parser("apply-update", parents=[shared])
    apply_update.add_argument("--target", type=Path, required=True)
    apply_update.add_argument("--wait", type=float, default=60)
    apply_update.add_argument("--no-restart", action="store_true")
    args = parser.parse_args(argv)
    # Defaults are filled in here rather than with set_defaults(), which would change the shared
    # options' defaults and make each command reset a --profile given before it.
    from .icons import DEFAULT_ICON_ROOT

    for name, default in (("profile", None), ("backups", saves.DEFAULT_BACKUP_ROOT), ("icons", DEFAULT_ICON_ROOT)):
        if getattr(args, name, None) is None:
            setattr(args, name, default)

    if args.command in (None, "gui"):
        from .gui import run

        return run(args.profile, args.backups, args.icons, getattr(args, "close_after", None))
    handler = {
        "list": cmd_list,
        "export": cmd_export,
        "import": cmd_import,
        "backup": cmd_backup,
        "restore": cmd_restore,
        "verify": cmd_verify,
        "items": cmd_items,
        "ids": cmd_ids,
        "mcp": cmd_mcp,
        "pictures": cmd_pictures,
        "update": cmd_update,
        "apply-update": cmd_apply_update,
    }[args.command]
    try:
        return handler(args)
    except (saves.GameRunningError, saves.StaleSaveError, saves.SaveFailedError, wgs.WgsFormatError) as exc:
        print(exc, file=sys.stderr)
        return 1
