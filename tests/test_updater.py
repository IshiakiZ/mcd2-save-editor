import contextlib
import hashlib
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from dungeons2_editor import cli, updater

URL = updater.DOWNLOADS + "v9.9.9/" + updater.ASSET_NAME


class Response(io.BytesIO):
    """What urlopen gives back, as far as the updater uses it."""

    def __init__(self, data: bytes, url: str = "https://release-assets.githubusercontent.com/x"):
        super().__init__(data)
        self.url = url

    def geturl(self) -> str:
        return self.url


def release_zip(files: dict[str, bytes] | None = None) -> bytes:
    files = files or {f"{updater.APP_FOLDER}/{updater.EXE_NAME}": b"new exe", f"{updater.APP_FOLDER}/_internal/data.bin": b"new data"}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    return buffer.getvalue()


def api_answer(version="9.9.9", data: bytes = b"", **asset) -> dict:
    listed = {"name": updater.ASSET_NAME, "browser_download_url": URL, "size": len(data), "digest": "sha256:" + hashlib.sha256(data).hexdigest()}
    listed.update(asset)
    return {"tag_name": "v" + version, "html_url": "https://github.com/IshiakiZ/mcd2-save-editor/releases/tag/v" + version, "assets": [listed]}


class VersionTests(unittest.TestCase):
    def test_versions_compare_as_numbers(self):
        self.assertEqual(updater.parse_version("v1.7.0"), (1, 7, 0))
        self.assertTrue(updater.is_newer("1.10.0", "1.9.9"))
        self.assertFalse(updater.is_newer("1.6.0", "1.6.0"))
        self.assertFalse(updater.is_newer("1.5.9", "1.6.0"))
        for junk in ("", "latest", "1.x", "1.2-beta"):
            self.assertIsNone(updater.parse_version(junk), junk)
            self.assertFalse(updater.is_newer(junk, "1.0.0"))


class ReleaseTests(unittest.TestCase):
    def test_reads_the_release_github_describes(self):
        release = updater.release_from(api_answer(data=b"zip bytes"))
        self.assertEqual((release.version, release.download_url, release.size), ("9.9.9", URL, 9))
        self.assertEqual(release.sha256, hashlib.sha256(b"zip bytes").hexdigest())
        self.assertTrue(release.page.endswith("/v9.9.9"))

    def test_ignores_releases_it_shouldnt_install(self):
        self.assertIsNone(updater.release_from({**api_answer(), "draft": True}))
        self.assertIsNone(updater.release_from({**api_answer(), "prerelease": True}))
        self.assertIsNone(updater.release_from(api_answer(name="Something.zip")))  # no editor zip
        self.assertIsNone(updater.release_from(api_answer(browser_download_url="https://example.com/MCD2SaveEditor.zip")))
        self.assertIsNone(updater.release_from(api_answer(version="nightly")))
        self.assertIsNone(updater.release_from(["not", "a", "release"]))
        self.assertIsNone(updater.release_from(api_answer(digest=None)).sha256)  # read, but never installed

    def test_check_finds_only_newer_versions_and_never_fails(self):
        import json

        answer = lambda version: (lambda url, timeout=0: Response(json.dumps(api_answer(version)).encode()))  # noqa: E731
        self.assertEqual(updater.check("1.6.0", answer("1.7.0")).version, "1.7.0")
        self.assertIsNone(updater.check("1.7.0", answer("1.7.0")))
        self.assertIsNone(updater.check("1.7.0", answer("1.6.0")))

        def offline(url, timeout=0):
            raise OSError("no network")

        self.assertIsNone(updater.check("1.0.0", offline))
        self.assertIsNone(updater.check("1.0.0", lambda url, timeout=0: Response(b"<html>not json")))

    def test_only_secure_addresses_are_opened(self):
        with self.assertRaises(updater.UpdateError):
            updater._open("http://api.github.com/repos/x")


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "update"
        self.data = release_zip()
        self.release = updater.release_from(api_answer(data=self.data))

    def serve(self, data=None, url="https://release-assets.githubusercontent.com/x"):
        return lambda asked, timeout=0: Response(self.data if data is None else data, url)

    def test_downloads_and_checks_the_zip(self):
        seen = []
        archive = updater.download(self.release, self.folder, lambda got, total: seen.append((got, total)), self.serve())
        self.assertEqual(archive.read_bytes(), self.data)
        self.assertEqual(seen[-1], (len(self.data), len(self.data)))
        self.assertEqual([path.name for path in self.folder.iterdir()], [updater.ASSET_NAME])

    def test_a_download_that_isnt_the_listed_file_is_thrown_away(self):
        tampered = self.data[:-1] + bytes([self.data[-1] ^ 1])
        for served in (tampered, self.data + b"extra", self.data[:-5]):
            with self.assertRaises(updater.UpdateError):
                updater.download(self.release, self.folder, opener=self.serve(served))
            self.assertEqual(list(self.folder.iterdir()), [])
        with self.assertRaises(updater.UpdateError):  # sent on to somewhere that isn't https
            updater.download(self.release, self.folder, opener=self.serve(url="http://mirror.example/x"))
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_no_checksum_no_install(self):
        unlisted = updater.release_from(api_answer(data=self.data, digest=None))
        with self.assertRaises(updater.UpdateError):
            updater.download(unlisted, self.folder, opener=self.serve())

    def test_unpacks_only_into_the_editors_folder(self):
        archive = self.folder / "good.zip"
        self.folder.mkdir()
        archive.write_bytes(self.data)
        app = updater.unpack(archive, self.folder)
        self.assertEqual((app / updater.EXE_NAME).read_bytes(), b"new exe")
        self.assertEqual((app / "_internal" / "data.bin").read_bytes(), b"new data")
        exe = f"{updater.APP_FOLDER}/{updater.EXE_NAME}"
        for bad in ("../evil.exe", "Other/file.txt", "/absolute.txt", f"{updater.APP_FOLDER}/../../evil.exe", "C:/evil.exe"):
            archive.write_bytes(release_zip({exe: b"x", bad: b"evil"}))
            with self.assertRaises(updater.UpdateError, msg=bad):
                updater.unpack(archive, self.folder / "bad")
            self.assertFalse((self.folder / "bad").exists(), bad)  # refused before anything is written
        archive.write_bytes(release_zip({f"{updater.APP_FOLDER}/readme.txt": b"no exe here"}))
        with self.assertRaises(updater.UpdateError):
            updater.unpack(archive, self.folder / "empty")
        archive.write_bytes(b"not a zip")
        with self.assertRaises(updater.UpdateError):
            updater.unpack(archive, self.folder / "junk")

    def test_stage_leaves_just_the_new_copy(self):
        with mock.patch.object(updater, "staging_dir", return_value=self.folder):
            self.folder.mkdir()
            (self.folder / "left over from last time.txt").write_text("old")
            app = updater.stage(self.release, opener=self.serve())
        self.assertEqual(app, self.folder / updater.APP_FOLDER)
        self.assertEqual([path.name for path in self.folder.iterdir()], [updater.APP_FOLDER])


class SwapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.target = root / "Games" / updater.APP_FOLDER
        self.staged = root / "data" / "update" / updater.APP_FOLDER
        for folder, version in ((self.target, b"old"), (self.staged, b"new")):
            (folder / "_internal").mkdir(parents=True)
            (folder / updater.EXE_NAME).write_bytes(version + b" exe")
            (folder / "_internal" / "data.bin").write_bytes(version + b" data")
        (self.target / "_internal" / "only in the old version.dll").write_bytes(b"x")

    def test_swaps_the_folder_for_the_new_copy(self):
        updater.apply_update(self.target, self.staged, wait=0, restart=False)
        self.assertEqual((self.target / updater.EXE_NAME).read_bytes(), b"new exe")
        self.assertEqual(sorted(path.name for path in (self.target / "_internal").iterdir()), ["data.bin"])
        self.assertEqual(sorted(path.name for path in self.target.parent.iterdir()), [updater.APP_FOLDER])  # nothing left beside it
        self.assertTrue((self.staged / updater.EXE_NAME).is_file())  # removed later, once it has stopped running

    def test_opens_the_editor_again(self):
        with mock.patch.object(updater, "_start") as start:
            updater.apply_update(self.target, self.staged, wait=0)
        start.assert_called_once_with([str(self.target.resolve() / updater.EXE_NAME)], self.target.resolve().parent)

    def test_refuses_folders_that_arent_the_editor(self):
        elsewhere = self.target.parent / "Documents"
        elsewhere.mkdir()
        (elsewhere / "thesis.docx").write_bytes(b"important")
        for target in (elsewhere, self.target.parent, self.staged, self.staged.parent, self.target / "missing"):
            with self.assertRaises(updater.UpdateError, msg=str(target)):
                updater.apply_update(target, self.staged, wait=0, restart=False)
        self.assertEqual((elsewhere / "thesis.docx").read_bytes(), b"important")
        self.assertEqual((self.target / updater.EXE_NAME).read_bytes(), b"old exe")
        (self.staged / updater.EXE_NAME).unlink()
        with self.assertRaises(updater.UpdateError):
            updater.apply_update(self.target, self.staged, wait=0, restart=False)

    def test_a_failed_copy_puts_the_old_version_back(self):
        with mock.patch("shutil.copytree", side_effect=OSError("disk full")):
            with self.assertRaises(updater.UpdateError) as caught:
                updater.apply_update(self.target, self.staged, wait=0, restart=False)
        self.assertIn("still there", str(caught.exception))
        self.assertEqual((self.target / updater.EXE_NAME).read_bytes(), b"old exe")
        self.assertTrue((self.target / "_internal" / "only in the old version.dll").is_file())
        self.assertEqual(sorted(path.name for path in self.target.parent.iterdir()), [updater.APP_FOLDER])

    def test_gives_up_when_the_old_editor_never_closes(self):
        with mock.patch("os.replace", side_effect=PermissionError("in use")), mock.patch("time.sleep"):
            with self.assertRaises(updater.UpdateError) as caught:
                updater.apply_update(self.target, self.staged, wait=0, restart=False)
        self.assertIn("still open", str(caught.exception))
        self.assertEqual((self.target / updater.EXE_NAME).read_bytes(), b"old exe")

    def test_clean_up_removes_what_an_update_leaves(self):
        aside = self.target.with_name(self.target.name + updater.OLD_SUFFIX)
        aside.mkdir()
        with mock.patch.object(updater, "staging_dir", return_value=self.staged.parent), mock.patch.object(updater, "app_dir", return_value=self.target):
            updater.clean_up(tries=1)
        self.assertFalse(self.staged.parent.exists())
        self.assertFalse(aside.exists())
        self.assertTrue((self.target / updater.EXE_NAME).is_file())

    def test_from_source_there_is_nothing_to_replace(self):
        self.assertIsNone(updater.app_dir())
        self.assertFalse(updater.can_replace())

    def test_the_new_copy_is_started_to_do_the_swap(self):
        with mock.patch.object(updater, "_start") as start, mock.patch.object(updater, "staging_dir", return_value=self.staged.parent):
            updater.start_swap(self.staged, self.target)
        command, cwd = start.call_args.args
        self.assertEqual(command, [str(self.staged / updater.EXE_NAME), "apply-update", "--target", str(self.target)])
        self.assertEqual(cwd, self.staged.parent.parent)  # not inside either folder, which would keep it in use
        with mock.patch.object(updater, "_start") as start, mock.patch.object(updater, "staging_dir", return_value=self.staged.parent):
            updater.start_swap(self.staged, self.target, restart=False)
        self.assertEqual(start.call_args.args[0][-1], "--no-restart")

    def test_update_command(self):
        release = updater.Release("99.0.0", "https://github.com/IshiakiZ/mcd2-save-editor/releases/tag/v99.0.0", URL, 19_000_000, "0" * 64)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            with mock.patch.object(updater, "check", return_value=None):
                self.assertEqual(cli.main(["update"]), 0)
            self.assertIn("latest version", out.getvalue())
            with mock.patch.object(updater, "check", return_value=release):  # from source: nothing to replace
                self.assertEqual(cli.main(["update"]), 0)
            self.assertIn(release.page, out.getvalue())
            with mock.patch.object(updater, "check", return_value=release), mock.patch.object(updater, "app_dir", return_value=self.target), \
                    mock.patch.object(updater, "stage", return_value=self.staged) as stage, mock.patch.object(updater, "start_swap") as swap:
                self.assertEqual(cli.main(["update", "--yes", "--no-restart"]), 0)
                stage.assert_called_once_with(release)
                swap.assert_called_once_with(self.staged, self.target, restart=False)
                stage.side_effect = updater.UpdateError("The download doesn't match")
                self.assertEqual(cli.main(["update", "--yes"]), 1)
            self.assertIn("The download doesn't match", out.getvalue())

    def test_apply_update_command(self):
        with mock.patch.object(updater, "apply_update") as apply:
            self.assertEqual(cli.main(["apply-update", "--target", str(self.target), "--no-restart", "--wait", "3"]), 0)
        apply.assert_called_once_with(self.target, Path(sys.executable).resolve().parent, wait=3.0, restart=False)
        with mock.patch.object(updater, "apply_update", side_effect=updater.UpdateError("no")), mock.patch.object(cli, "_update_failed") as failed, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["apply-update", "--target", str(self.target), "--no-restart"]), 1)
            failed.assert_not_called()  # a build check has nobody to tell
            self.assertEqual(cli.main(["apply-update", "--target", str(self.target)]), 1)
            failed.assert_called_once_with("no", self.target)


if __name__ == "__main__":
    unittest.main()
