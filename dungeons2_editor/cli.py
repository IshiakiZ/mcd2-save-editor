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
        raise SystemExit("No Minecraft Dungeons II saves found. Use --profile to point at a folder with containers.index.")
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
    print(f"Profile: {profile.path}")
    for container in profile.containers:
        entry = container.entry
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
    restored = profile.restore(backup, args.backups)
    print(f"Restored: {', '.join(restored)}" if restored else "Nothing to restore: the backup matches the current save data.")
    return 0


def cmd_pictures(args: argparse.Namespace) -> int:
    from . import icons, wiki

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


def cmd_verify(args: argparse.Namespace) -> int:
    """Check, without writing anything, that every editable container re-encodes byte for byte."""
    profile = _pick_profile(args.profile)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dungeons2_editor", description="Minecraft Dungeons II save editor.")
    parser.add_argument("--profile", type=Path, help="save folder that contains containers.index (default: auto-detect)")
    parser.add_argument("--backups", type=Path, default=saves.DEFAULT_BACKUP_ROOT, help="where backups are kept")
    parser.add_argument("--icons", type=Path, default=None, help="folder of item pictures (default: icons next to the editor)")
    commands = parser.add_subparsers(dest="command", metavar="command")
    commands.add_parser("gui", help="open the editor window (default)")
    commands.add_parser("list", help="list the save containers")
    export = commands.add_parser("export", help="write a container's data to a JSON file")
    export.add_argument("container")
    export.add_argument("output", nargs="?", type=Path)
    import_ = commands.add_parser("import", help="save a JSON file into a container (makes a backup first)")
    import_.add_argument("container")
    import_.add_argument("input", type=Path)
    import_.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    commands.add_parser("backup", help="back up the whole save folder")
    restore = commands.add_parser("restore", help="put back the save data from a backup folder")
    restore.add_argument("backup", type=Path)
    restore.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    commands.add_parser("verify", help="check that saves re-encode exactly (writes nothing)")
    pictures = commands.add_parser("pictures", help="download item pictures from minecraft.wiki into the icons folder")
    pictures.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    args = parser.parse_args(argv)
    if args.icons is None:
        from .icons import DEFAULT_ICON_ROOT

        args.icons = DEFAULT_ICON_ROOT

    if args.command in (None, "gui"):
        from .gui import run

        return run(args.profile, args.backups, args.icons)
    handler = {
        "list": cmd_list,
        "export": cmd_export,
        "import": cmd_import,
        "backup": cmd_backup,
        "restore": cmd_restore,
        "verify": cmd_verify,
        "pictures": cmd_pictures,
    }[args.command]
    try:
        return handler(args)
    except (saves.GameRunningError, saves.StaleSaveError, saves.SaveFailedError, wgs.WgsFormatError) as exc:
        print(exc, file=sys.stderr)
        return 1
