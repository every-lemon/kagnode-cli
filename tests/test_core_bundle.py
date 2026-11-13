"""Helper import orchestration; crypto is mocked here and real signatures are
checked separately against the published Core artifacts during release."""

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
    "core_bundle", ROOT / "scripts/bundle_core_manager.py"
)
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class CoreBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.release = Path(self.temporary.name) / "release"
        for directory in (
            "assets",
            "vendor/core-source/assets",
            "vendor/core-source/packages/python",
        ):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        self.release.mkdir()
        self.key = b"fixture public key\n"
        self.helper = b"# corresponding manager fixture\n"
        (self.root / "vendor/core-source/assets/release-public.pem").write_bytes(
            self.key
        )
        self.old = b'PUBLIC_KEY="fixture public key\\n"\nLIMIT=67108864\ndef verify_signature(raw,sig):\n if sig!=b"fixture": raise ValueError("Invalid signature")\n'
        (self.root / "assets/core_manager.py").write_bytes(self.old)
        source = self.release / "kagnode-core-5.0.6-source.tar.gz"
        with tarfile.open(source, "w:gz") as archive:
            info = tarfile.TarInfo("core/packages/python/manager.py")
            info.size = len(self.helper)
            archive.addfile(info, io.BytesIO(self.helper))
        wheel = self.release / "kagnode_core-5.0.6-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("kagnode_core_manager.py", self.helper)
        manifest = {
            "schema": 1,
            "version": "5.0.6",
            "source_commit": "a" * 40,
            "packages": [
                {
                    "name": p.name,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    "size": p.stat().st_size,
                }
                for p in (source, wheel)
            ],
        }
        (self.release / "release-manifest.json").write_text(json.dumps(manifest))
        (self.release / "release-manifest.sig").write_bytes(b"fixture")

    def git_source(self, args, **kwargs):
        return (
            self.helper
            if args[-1].endswith(":packages/python/manager.py")
            else self.key
        )

    def test_import_requires_signed_source_wheel_and_git_correspondence(self):
        with (
            patch.object(bundle, "ROOT", self.root),
            patch.object(
                bundle.subprocess, "check_output", side_effect=self.git_source
            ),
        ):
            bundle.bundle(self.release, self.root)
        self.assertEqual(
            (self.root / "assets/core_manager.py").read_bytes(), self.helper
        )
        manifest = json.loads(
            (self.root / "assets/core-manager-manifest.json").read_text()
        )
        self.assertEqual(
            manifest["public_key_sha256"], hashlib.sha256(self.key).hexdigest()
        )
        self.assertEqual(manifest["upgrade_policy"], "explicit-review")

    def test_changed_signature_or_package_never_replaces_helper(self):
        for kind in ("signature", "package"):
            with self.subTest(kind=kind):
                target = self.release / (
                    "release-manifest.sig"
                    if kind == "signature"
                    else "kagnode_core-5.0.6-py3-none-any.whl"
                )
                original = target.read_bytes()
                target.write_bytes(original + b"changed")
                with patch.object(bundle, "ROOT", self.root):
                    with self.assertRaises(ValueError):
                        bundle.bundle(self.release, self.root)
                self.assertEqual(
                    (self.root / "assets/core_manager.py").read_bytes(), self.old
                )
                target.write_bytes(original)

    def test_git_disagreement_never_replaces_helper(self):
        with (
            patch.object(bundle, "ROOT", self.root),
            patch.object(
                bundle.subprocess, "check_output", return_value=b"wrong source"
            ),
        ):
            with self.assertRaisesRegex(ValueError, "Git source"):
                bundle.bundle(self.release, self.root)
        self.assertEqual((self.root / "assets/core_manager.py").read_bytes(), self.old)


if __name__ == "__main__":
    unittest.main()
