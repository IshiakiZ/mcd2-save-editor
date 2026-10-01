"""Reader/writer for Xbox app ("wgs") save containers.

Games installed through the Xbox app / PC Game Pass keep their saves under
``%LOCALAPPDATA%\\Packages\\<package>\\SystemAppData\\wgs\\<user>_<title>\\``::

    containers.index              list of named containers
    <folder guid>\\container.<N>   blob list for one container; N is its revision
    <folder guid>\\<blob guid>     raw bytes of one blob

Gaming Services syncs these files with the Xbox cloud. To change a container we
do what the game does (the layout and procedure match libNOM.io, which writes
No Man's Sky saves this way): write the blobs under new GUIDs, write
``container.<N+1>``, mark the container as modified in containers.index so it
gets uploaded, and only then delete the previous revision's files.
"""

from __future__ import annotations

import dataclasses
import os
import struct
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

INDEX_FILE = "containers.index"
INDEX_VERSION = 14
INDEX_FOOTER = 0x1000_0000
MANIFEST_VERSION = 4
BLOB_NAME_SIZE = 128  # bytes of zero-padded UTF-16LE

# Per-container sync states in containers.index.
SYNCED = 1
MODIFIED = 2
DELETED = 3
CREATED = 5
# Sync state of containers.index as a whole.
INDEX_MODIFIED = 2

SYNC_STATE_NAMES = {SYNCED: "synced", MODIFIED: "modified, not uploaded yet", DELETED: "deleted", CREATED: "new, not uploaded yet"}

_FILETIME_UNIX_EPOCH = 116_444_736_000_000_000  # 1970-01-01 in 100 ns ticks since 1601-01-01


class WgsFormatError(Exception):
    """The files do not match the container layout this module understands."""


def filetime_now() -> int:
    return time.time_ns() // 100 + _FILETIME_UNIX_EPOCH


def filetime_to_unix(filetime: int) -> float:
    return (filetime - _FILETIME_UNIX_EPOCH) / 10_000_000


@dataclass
class IndexEntry:
    name: str
    alt_name: str  # second identifier; Dungeons II repeats the name here
    etag: str  # cloud version tag, e.g. '"0x8DE0000000000001"'
    revision: int  # N in container.N
    sync_state: int
    folder: uuid.UUID
    mtime: int  # FILETIME
    reserved: int
    size: int  # total bytes of the container's blobs

    @property
    def folder_name(self) -> str:
        return self.folder.hex.upper()

    @property
    def manifest_name(self) -> str:
        return f"container.{self.revision}"


@dataclass
class ContainersIndex:
    version: int
    package: str
    mtime: int
    sync_state: int
    account: str
    footer: int
    entries: list[IndexEntry] = field(default_factory=list)

    def find(self, name: str) -> IndexEntry | None:
        return next((entry for entry in self.entries if entry.name == name), None)


@dataclass
class BlobRef:
    name: str
    cloud_guid: uuid.UUID  # name of the blob in the cloud
    local_guid: uuid.UUID  # name of the blob file on disk

    @property
    def file_name(self) -> str:
        return self.local_guid.hex.upper()


@dataclass
class Manifest:
    version: int
    blobs: list[BlobRef]


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def take(self, size: int) -> bytes:
        end = self.pos + size
        if end > len(self.data):
            raise WgsFormatError("file ends early")
        chunk = self.data[self.pos:end]
        self.pos = end
        return chunk

    def u8(self) -> int:
        return self.take(1)[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def guid(self) -> uuid.UUID:
        return uuid.UUID(bytes_le=self.take(16))

    def text(self) -> str:
        length = self.u32()
        return self.take(length * 2).decode("utf-16-le")

    def finish(self) -> None:
        if self.pos != len(self.data):
            raise WgsFormatError(f"{len(self.data) - self.pos} unexpected bytes at end of file")


def _put_text(out: bytearray, value: str) -> None:
    encoded = value.encode("utf-16-le")
    out += struct.pack("<I", len(encoded) // 2)
    out += encoded


def parse_index(data: bytes) -> ContainersIndex:
    reader = _Reader(data)
    version = reader.u32()
    if version != INDEX_VERSION:
        raise WgsFormatError(f"unsupported containers.index version {version} (expected {INDEX_VERSION})")
    count = reader.u64()
    index = ContainersIndex(
        version=version,
        package=reader.text(),
        mtime=reader.u64(),
        sync_state=reader.u32(),
        account=reader.text(),
        footer=reader.u64(),
    )
    if index.footer != INDEX_FOOTER:
        raise WgsFormatError(f"unexpected containers.index header value {index.footer:#x}")
    for _ in range(count):
        index.entries.append(
            IndexEntry(
                name=reader.text(),
                alt_name=reader.text(),
                etag=reader.text(),
                revision=reader.u8(),
                sync_state=reader.u32(),
                folder=reader.guid(),
                mtime=reader.u64(),
                reserved=reader.u64(),
                size=reader.u64(),
            )
        )
    reader.finish()
    return index


def serialize_index(index: ContainersIndex) -> bytes:
    out = bytearray(struct.pack("<IQ", index.version, len(index.entries)))
    _put_text(out, index.package)
    out += struct.pack("<QI", index.mtime, index.sync_state)
    _put_text(out, index.account)
    out += struct.pack("<Q", index.footer)
    for entry in index.entries:
        _put_text(out, entry.name)
        _put_text(out, entry.alt_name)
        _put_text(out, entry.etag)
        out += struct.pack("<BI", entry.revision, entry.sync_state)
        out += entry.folder.bytes_le
        out += struct.pack("<QQQ", entry.mtime, entry.reserved, entry.size)
    return bytes(out)


def parse_manifest(data: bytes) -> Manifest:
    reader = _Reader(data)
    version = reader.u32()
    if version != MANIFEST_VERSION:
        raise WgsFormatError(f"unsupported container file version {version} (expected {MANIFEST_VERSION})")
    blobs = []
    for _ in range(reader.u32()):
        name = reader.take(BLOB_NAME_SIZE).decode("utf-16-le").split("\0", 1)[0]
        blobs.append(BlobRef(name=name, cloud_guid=reader.guid(), local_guid=reader.guid()))
    reader.finish()
    return Manifest(version=version, blobs=blobs)


def serialize_manifest(manifest: Manifest) -> bytes:
    out = bytearray(struct.pack("<II", manifest.version, len(manifest.blobs)))
    for blob in manifest.blobs:
        name = blob.name.encode("utf-16-le")
        if len(name) > BLOB_NAME_SIZE:
            raise WgsFormatError(f"blob name too long: {blob.name!r}")
        out += name.ljust(BLOB_NAME_SIZE, b"\0")
        out += blob.cloud_guid.bytes_le
        out += blob.local_guid.bytes_le
    return bytes(out)


def read_index(profile: Path) -> ContainersIndex:
    return parse_index((Path(profile) / INDEX_FILE).read_bytes())


def read_manifest(profile: Path, entry: IndexEntry) -> Manifest:
    return parse_manifest((Path(profile) / entry.folder_name / entry.manifest_name).read_bytes())


def read_blobs(profile: Path, entry: IndexEntry) -> dict[str, bytes]:
    folder = Path(profile) / entry.folder_name
    return {blob.name: (folder / blob.file_name).read_bytes() for blob in read_manifest(profile, entry).blobs}


def _write_new_file(path: Path, data: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _replace_file(path: Path, data: bytes) -> None:
    temp = path.with_name(path.name + ".tmp")
    try:
        _write_new_file(temp, data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def write_container(profile: Path, name: str, blobs: dict[str, bytes]) -> IndexEntry:
    """Store new contents for the blobs of container ``name`` as a new revision.

    ``blobs`` must contain exactly the blobs the container already has. If any
    step fails before containers.index is replaced, the new files are removed
    and the previous revision stays in place. Returns the updated index entry.
    """
    profile = Path(profile)
    index = read_index(profile)
    entry = index.find(name)
    if entry is None:
        raise KeyError(f"no container named {name!r}")
    if entry.sync_state == DELETED:
        raise WgsFormatError(f"container {name!r} is marked as deleted")

    folder = profile / entry.folder_name
    old_manifest_path = folder / entry.manifest_name
    old_manifest = parse_manifest(old_manifest_path.read_bytes())
    if sorted(blob.name for blob in old_manifest.blobs) != sorted(blobs):
        raise ValueError(f"container {name!r} holds blobs {[b.name for b in old_manifest.blobs]}, got {sorted(blobs)}")

    # Every revision the game writes gives each blob one new ID, used both as its cloud name and its
    # file name. Keeping the old cloud name (as earlier versions of this editor did) tells the Xbox
    # app the cloud already has the data, so it can bring the old data back and lose the edit.
    new_refs = [BlobRef(blob.name, guid, guid) for blob, guid in ((blob, uuid.uuid4()) for blob in old_manifest.blobs)]
    now = filetime_now()
    new_entry = dataclasses.replace(
        entry,
        revision=1 if entry.revision >= 255 else entry.revision + 1,
        sync_state=MODIFIED if entry.sync_state == SYNCED else entry.sync_state,
        mtime=now,
        size=sum(len(data) for data in blobs.values()),
    )
    new_index = dataclasses.replace(
        index,
        mtime=now,
        sync_state=INDEX_MODIFIED,
        entries=[new_entry if item is entry else item for item in index.entries],
    )
    new_manifest_path = folder / new_entry.manifest_name

    written: list[Path] = []
    try:
        for ref in new_refs:
            path = folder / ref.file_name
            _write_new_file(path, blobs[ref.name])
            written.append(path)
        _write_new_file(new_manifest_path, serialize_manifest(Manifest(old_manifest.version, new_refs)))
        written.append(new_manifest_path)
        _replace_file(profile / INDEX_FILE, serialize_index(new_index))
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise

    # The new revision is live, so the previous one is no longer referenced.
    old_manifest_path.unlink(missing_ok=True)
    for blob in old_manifest.blobs:
        (folder / blob.file_name).unlink(missing_ok=True)
    return new_entry
