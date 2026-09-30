import struct
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from dungeons2_editor import wgs

from .helpers import BASE_TIME, index_bytes, make_profile, manifest_bytes, snapshot


def _entry(name: str, revision: int = 21, sync: int = 1) -> dict:
    return {"name": name, "etag": '"0x8DE0000000000001"', "revision": revision, "sync": sync, "folder": uuid.uuid4(), "mtime": BASE_TIME, "size": 8689}


class ParseTests(unittest.TestCase):
    def test_index_fields(self):
        first, second = _entry("GlobalSaveDataDefault"), _entry("Guidbin", revision=4)
        index = wgs.parse_index(index_bytes([first, second]))
        self.assertEqual(index.package.split("!")[0], "Microsoft.MinecraftDungeons2_8wekyb3d8bbwe")
        self.assertEqual(index.sync_state, 3)
        self.assertEqual([entry.name for entry in index.entries], ["GlobalSaveDataDefault", "Guidbin"])
        entry = index.entries[0]
        self.assertEqual((entry.alt_name, entry.etag, entry.revision, entry.sync_state), ("GlobalSaveDataDefault", '"0x8DE0000000000001"', 21, 1))
        self.assertEqual(entry.folder, first["folder"])
        self.assertEqual(entry.size, 8689)
        self.assertEqual(entry.folder_name, first["folder"].hex.upper())

    def test_index_and_manifest_round_trip_exactly(self):
        data = index_bytes([_entry("A"), _entry("B", revision=255, sync=5)])
        self.assertEqual(wgs.serialize_index(wgs.parse_index(data)), data)
        guid = uuid.uuid4()
        manifest = manifest_bytes([("Data", guid, guid), ("Thumbnail", uuid.uuid4(), uuid.uuid4())])
        self.assertEqual(wgs.serialize_manifest(wgs.parse_manifest(manifest)), manifest)

    def test_manifest_second_guid_is_the_file_name(self):
        cloud, local = uuid.uuid4(), uuid.uuid4()
        blob = wgs.parse_manifest(manifest_bytes([("Data", cloud, local)])).blobs[0]
        self.assertEqual((blob.name, blob.cloud_guid, blob.file_name), ("Data", cloud, local.hex.upper()))

    def test_rejects_files_it_does_not_understand(self):
        good = index_bytes([_entry("A")])
        for bad in (struct.pack("<I", 13) + good[4:], good + b"\0", good[:-3]):
            with self.assertRaises(wgs.WgsFormatError):
                wgs.parse_index(bad)
        with self.assertRaises(wgs.WgsFormatError):
            wgs.parse_manifest(struct.pack("<II", 5, 0))


class WriteContainerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.profile = make_profile(Path(self.temp.name), {"GlobalSaveDataDefault": b"old data", "Guidbin": b"other"})

    def test_writes_a_new_revision_like_the_game(self):
        before = wgs.read_index(self.profile)
        old_entry = before.find("GlobalSaveDataDefault")
        old_blob = wgs.read_manifest(self.profile, old_entry).blobs[0]

        new_entry = wgs.write_container(self.profile, "GlobalSaveDataDefault", {"Data": b"new data!"})

        after = wgs.read_index(self.profile)
        self.assertEqual(after.find("GlobalSaveDataDefault"), new_entry)
        self.assertEqual(new_entry.revision, old_entry.revision + 1)
        self.assertEqual(new_entry.sync_state, wgs.MODIFIED)
        self.assertEqual(new_entry.size, len(b"new data!"))
        self.assertGreater(new_entry.mtime, old_entry.mtime)
        self.assertEqual((new_entry.etag, new_entry.folder, new_entry.name, new_entry.alt_name), (old_entry.etag, old_entry.folder, old_entry.name, old_entry.alt_name))
        self.assertEqual(after.sync_state, wgs.INDEX_MODIFIED)
        self.assertEqual(after.find("Guidbin"), before.find("Guidbin"))
        self.assertEqual((after.package, after.account, after.footer), (before.package, before.account, before.footer))

        new_blob = wgs.read_manifest(self.profile, new_entry).blobs[0]
        self.assertEqual(new_blob.cloud_guid, old_blob.cloud_guid)
        self.assertNotEqual(new_blob.local_guid, old_blob.local_guid)
        self.assertEqual(wgs.read_blobs(self.profile, new_entry), {"Data": b"new data!"})
        folder = self.profile / new_entry.folder_name
        self.assertEqual(sorted(path.name for path in folder.iterdir()), sorted([new_blob.file_name, "container.5"]))

    def test_revision_wraps_after_255(self):
        profile = make_profile(Path(self.temp.name) / "wrap", {"A": b"x"}, revisions={"A": 255})
        self.assertEqual(wgs.write_container(profile, "A", {"Data": b"y"}).revision, 1)
        self.assertEqual(wgs.read_blobs(profile, wgs.read_index(profile).find("A")), {"Data": b"y"})

    def test_not_yet_uploaded_state_is_kept(self):
        profile = make_profile(Path(self.temp.name) / "created", {"A": b"x"}, sync={"A": wgs.CREATED})
        self.assertEqual(wgs.write_container(profile, "A", {"Data": b"y"}).sync_state, wgs.CREATED)

    def test_failure_before_index_swap_leaves_everything_as_it_was(self):
        before = snapshot(self.profile)
        with mock.patch.object(wgs, "_replace_file", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                wgs.write_container(self.profile, "GlobalSaveDataDefault", {"Data": b"new"})
        self.assertEqual(snapshot(self.profile), before)

    def test_blob_names_must_match(self):
        before = snapshot(self.profile)
        with self.assertRaises(ValueError):
            wgs.write_container(self.profile, "GlobalSaveDataDefault", {"Other": b"new"})
        with self.assertRaises(KeyError):
            wgs.write_container(self.profile, "Missing", {"Data": b"new"})
        self.assertEqual(snapshot(self.profile), before)


if __name__ == "__main__":
    unittest.main()
