"""Security and reproducibility checks for source/archive release tooling."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "kagnode_release", ROOT / "scripts/release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_archives_are_reproducible_and_have_identical_payloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            source.write_bytes(b"KagNode release fixture\n")
            a, b = root / "a", root / "b"
            a.mkdir()
            b.mkdir()
            release.archives([("docs/source.txt", source)], "fixture", a, 1793952000)
            release.archives([("docs/source.txt", source)], "fixture", b, 1793952000)
            for path in a.iterdir():
                self.assertEqual(path.read_bytes(), (b / path.name).read_bytes())
                if path.suffix == ".zip":
                    with zipfile.ZipFile(path) as archive:
                        self.assertEqual(
                            archive.namelist(), ["fixture/docs/source.txt"]
                        )
                        self.assertEqual(
                            archive.read(archive.namelist()[0]), source.read_bytes()
                        )
                else:
                    with tarfile.open(path) as archive:
                        member = archive.getmembers()[0]
                        self.assertTrue(member.isfile())
                        self.assertEqual(member.uid, 0)
                        self.assertEqual(member.name, "fixture/docs/source.txt")
                        self.assertEqual(
                            archive.extractfile(member).read(), source.read_bytes()
                        )

    def test_source_publication_rejects_escape_symlink_and_private_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "packaging").mkdir()
            (root / "file").write_text("fixture")
            (root / "link").symlink_to(root / "file")
            (root / "key").write_text("-----BEGIN " + "PRIVATE KEY-----\nfixture\n")
            for name in [
                "../escape",
                "/absolute",
                "link",
                "runtime/account.json",
                "data.sqlite",
                "key",
            ]:
                (root / "packaging/source-files.json").write_text(json.dumps([name]))
                with patch.object(release, "ROOT", root):
                    with self.assertRaises(ValueError, msg=name):
                        release.source_files()

    def test_repository_version_resolves_without_relabeling_product(self):
        cfg, product, version = release.identity()
        self.assertIn("packaging.", version)
        self.assertTrue(version.startswith(product))
        self.assertIs(type(cfg["revision"]), int)
        self.assertGreaterEqual(cfg["revision"], 1)
        self.assertTrue(version.endswith("packaging." + str(cfg["revision"])))


if __name__ == "__main__":
    unittest.main()
