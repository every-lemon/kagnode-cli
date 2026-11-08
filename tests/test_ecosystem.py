"""Release selection, extraction and transitions are tested without live services."""

import importlib.util
import copy
import io
import json
import os
import signal
import sys
import socket
import subprocess
import threading
import time
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets"))
import ecosystem as eco


def archive(entries):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        for name, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == "link":
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/shadow"
            elif kind == "device":
                info.type = tarfile.CHRTYPE
            else:
                info.size = 4
            bundle.addfile(info, io.BytesIO(b"test") if kind == "file" else None)
    return buffer.getvalue()


class EcosystemTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "kagnode"
        self.manager = eco.Manager(self.root, False)

    def test_urls_are_repository_bound_and_do_not_allow_credentials(self):
        for url in [
            "http://github.com/x",
            "https://github.com.evil.test/x",
            "https://user:secret@github.com/x",
            "https://github.com/another/project/releases/download/v1/a",
        ]:
            with self.assertRaises(eco.ManagerError):
                eco.https_url(url, "kagnode-cli")
        self.assertTrue(
            eco.https_url(
                "https://github.com/every-lemon/kagnode-cli/releases/download/v1/a",
                "kagnode-cli",
            )
        )

    def test_archive_rejects_traversal_links_devices_duplicate_paths_and_roots(self):
        for entries in [
            [("../outside", "file")],
            [("/absolute", "file")],
            [("root/link", "link")],
            [("root/device", "device")],
            [("root/a", "file"), ("root/a", "file")],
            [("one/a", "file"), ("two/b", "file")],
        ]:
            output = self.root / "output"
            output.mkdir(parents=True, exist_ok=True)
            packed = self.root / "archive.tar.gz"
            packed.write_bytes(archive(entries))
            with self.assertRaises(eco.ManagerError):
                eco.source_archive(packed, output)
            self.assertEqual(list(output.iterdir()), [])

    def test_archive_normalizes_permissions_and_root(self):
        self.root.mkdir()
        packed = self.root / "a.tar.gz"
        packed.write_bytes(archive([("release/docs/file", "file")]))
        output = self.root / "source"
        output.mkdir()
        eco.source_archive(packed, output)
        self.assertEqual((output / "docs/file").read_bytes(), b"test")
        self.assertEqual((output / "docs/file").stat().st_mode & 0o777, 0o644)

    def test_unknown_projects_and_symlink_roots_are_rejected(self):
        with self.assertRaises(eco.ManagerError):
            self.manager.project("../anything")
        self.root.symlink_to(self.root.parent)
        with self.assertRaises(eco.ManagerError):
            eco.Manager(self.root, False)

    def fixtures(self, preview=True):
        repo = "kagnode-passwords"
        source = archive([("release/README.md", "file")])
        name = repo + "_0.6_source.tar.gz"
        prefix = "https://github.com/every-lemon/" + repo + "/releases/download/v0.6/"
        manifest = {
            "schema": 1,
            "repository": "every-lemon/" + repo,
            "source_commit": "a" * 40,
            "version": "0.6",
            "assets": {
                name: {
                    "size": len(source),
                    "sha256": eco.hashlib.sha256(source).hexdigest(),
                }
            },
        }
        release = {
            "id": 42,
            "tag_name": "v0.6",
            "draft": False,
            "prerelease": preview,
            "assets": [
                {
                    "name": "release-manifest.json",
                    "browser_download_url": prefix + "release-manifest.json",
                },
                {"name": name, "browser_download_url": prefix + name},
            ],
        }

        def fetch(url, limit=0):
            if "api.github.com" in url:
                return json.dumps([release]).encode()
            if url.endswith("release-manifest.json"):
                return json.dumps(manifest).encode()
            return source

        return fetch, manifest, release

    def test_preview_requires_explicit_selection_and_pins_release(self):
        fetch, _, _ = self.fixtures()
        with patch.object(eco, "request", fetch):
            self.assertFalse(self.manager.check("passwords", "stable")["available"])
            self.assertEqual(
                self.manager.check("passwords", "preview")["release_id"], 42
            )
            with self.assertRaisesRegex(eco.ManagerError, "changed since review"):
                self.manager.install("passwords", "preview", 41)

    def test_wrong_manifest_identity_cannot_install(self):
        fetch, manifest, _ = self.fixtures()
        manifest["repository"] = "other/repo"
        with patch.object(eco, "request", fetch):
            with self.assertRaises(eco.ManagerError):
                self.manager.check("passwords", "preview")

    def test_install_and_repeat_are_safe_and_keep_existing_data(self):
        fetch, _, _ = self.fixtures()
        with patch.object(eco, "request", fetch), patch.object(self.manager, "prepare"):
            result = self.manager.install("passwords", "preview", 42)
            self.assertEqual(result["installed"], "0.6")
            self.assertFalse(result["needs_recovery"])
            self.assertFalse((self.root / "passwords/activation.json").exists())
            root = self.root / "passwords"
            (root / "data/private.fixture").write_text("keep this data")
            before = (root / "current").resolve()
            self.assertEqual(
                self.manager.install("passwords", "preview", 42)["message"],
                "Already installed",
            )
            self.assertEqual((root / "current").resolve(), before)
            self.assertEqual(
                (root / "data/private.fixture").read_text(), "keep this data"
            )

    def test_state_write_failure_blocks_further_updates_without_network(self):
        fetch, manifest, _ = self.fixtures()
        with patch.object(eco, "request", fetch), patch.object(self.manager, "prepare"):
            self.manager.install("passwords", "preview")
        path = self.root / "passwords"
        (path / "data/private.fixture").write_text("retain")
        manifest["source_commit"] = "b" * 40
        original_atomic = eco.atomic

        def fail_state(target, value, *args, **kwargs):
            if target == path / "state.json":
                raise OSError("metadata disk full")
            return original_atomic(target, value, *args, **kwargs)

        with (
            patch.object(eco, "request", fetch),
            patch.object(self.manager, "prepare"),
            patch.object(eco, "atomic", fail_state),
        ):
            with self.assertRaisesRegex(OSError, "metadata disk full"):
                self.manager.install("passwords", "preview")
        self.assertTrue(self.manager.status("passwords")["needs_recovery"])
        self.assertFalse(self.manager.status("passwords")["can_apply"])
        self.assertEqual((path / "data/private.fixture").read_text(), "retain")
        with patch.object(eco, "request") as network:
            with self.assertRaisesRegex(eco.ManagerError, "recovery review"):
                self.manager.install("passwords", "preview")
            network.assert_not_called()

    def test_killed_activation_survives_in_a_new_manager(self):
        fetch, manifest, _ = self.fixtures()
        with patch.object(eco, "request", fetch), patch.object(self.manager, "prepare"):
            self.manager.install("passwords", "preview")
        path = self.root / "passwords"
        old = (path / "current").resolve()
        (path / "data/private.fixture").write_text("retain")
        manifest["source_commit"] = "b" * 40
        original_atomic = eco.atomic
        child = os.fork()
        if child == 0:
            try:

                def kill_at_metadata(target, value, *args, **kwargs):
                    if target == path / "state.json":
                        os.kill(os.getpid(), signal.SIGKILL)
                    return original_atomic(target, value, *args, **kwargs)

                with (
                    patch.object(eco, "request", fetch),
                    patch.object(self.manager, "prepare"),
                    patch.object(eco, "atomic", kill_at_metadata),
                ):
                    self.manager.install("passwords", "preview")
            finally:
                os._exit(99)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), -signal.SIGKILL)
        self.assertNotEqual((path / "current").resolve(), old)
        self.assertEqual(eco.read(path / "state.json")["source_commit"], "a" * 40)
        restarted = eco.Manager(self.root, False)
        self.assertTrue(restarted.status("passwords")["needs_recovery"])
        with patch.object(eco, "request") as network:
            with self.assertRaisesRegex(eco.ManagerError, "recovery review"):
                restarted.install("passwords", "preview")
            network.assert_not_called()
        self.assertEqual((path / "data/private.fixture").read_text(), "retain")

    def test_native_metadata_failure_keeps_activation_marker(self):
        fetch, _, _ = self.fixtures()
        with patch.object(eco, "request", fetch):
            candidate = self.manager.check("passwords", "preview")
        path = self.root / "mail"
        path.mkdir(parents=True)
        eco.atomic(
            path / "state.json",
            {
                "native_binding": {
                    "profile": "mail",
                    "guards": {
                        field: "0" * 64
                        for field in eco.NATIVE_PROFILES["mail"]["guards"]
                    },
                }
            },
        )
        original_atomic = eco.atomic

        def fail_state(target, value, *args, **kwargs):
            if target == path / "state.json":
                raise OSError("metadata disk full")
            return original_atomic(target, value, *args, **kwargs)

        def native_apply(*args):
            self.assertTrue((path / "activation.json").exists())

        with (
            patch.object(self.manager, "check", return_value=candidate),
            patch.object(eco, "request", fetch),
            patch.object(self.manager, "prepare"),
            patch.object(self.manager, "apply_native", side_effect=native_apply),
            patch.object(eco, "atomic", fail_state),
        ):
            with self.assertRaisesRegex(OSError, "metadata disk full"):
                self.manager.install("mail", "preview")
        self.assertTrue(self.manager.status("mail")["needs_recovery"])
        self.assertFalse(self.manager.status("mail")["can_apply"])

    def test_signed_native_failure_keeps_marker_before_running_updater(self):
        path = self.root / "vpn"
        path.mkdir(parents=True)
        state = {
            "version": "old",
            "native_binding": {
                "profile": "vpn",
                "guards": {
                    field: "0" * 64 for field in eco.NATIVE_PROFILES["vpn"]["guards"]
                },
            },
        }
        eco.atomic(path / "state.json", state)
        data = b"mock updater; never executed"
        candidate = {
            "release_id": 42,
            "version": "new",
            "changed": True,
            "prerelease": True,
            "size": len(data),
            "sha256": eco.hashlib.sha256(data).hexdigest(),
            "url": "fixture",
            "channel": "preview",
        }

        def fail_updater(*args, **kwargs):
            self.assertTrue((path / "activation.json").exists())
            raise eco.subprocess.TimeoutExpired("mock", 1800)

        with (
            patch.object(self.manager, "check", return_value=candidate),
            patch.object(eco, "request", return_value=data),
            patch.object(eco.subprocess, "run", side_effect=fail_updater),
        ):
            with self.assertRaises(eco.subprocess.TimeoutExpired):
                self.manager.install("vpn", "preview")
        self.assertTrue(self.manager.status("vpn")["needs_recovery"])
        self.assertEqual(eco.read(path / "state.json"), state)

    def test_recovery_blocks_setup_and_cli_activation(self):
        for name in ("passwords", "cli"):
            path = self.root / name
            path.mkdir(parents=True)
            eco.atomic(path / "state.json", {"version": "fixture"})
            eco.atomic(path / "activation.json", {"adapter": "managed"})
        with patch.object(self.manager, "service") as service:
            with self.assertRaisesRegex(eco.ManagerError, "recovery review"):
                self.manager.setup("passwords", "https://vault.example.com")
            with self.assertRaisesRegex(eco.ManagerError, "recovery review"):
                self.manager.activate_cli()
            service.assert_not_called()

    def test_unreadable_host_migration_status_is_not_reported_safe(self):
        with patch.object(
            self.manager, "migration_pending", side_effect=PermissionError
        ):
            status = self.manager.status("mail")
        self.assertFalse(status["can_apply"])
        self.assertIn("sudo", status["message"])

    def test_damaged_metadata_returns_recovery_status_and_preserves_bytes(self):
        path = self.root / "passwords"
        path.mkdir(parents=True)
        for filename, raw in [
            ("state.json", "{"),
            ("state.json", "[]"),
            ("state.json", '{"active":"false"}'),
            ("state.json", '{"active":true,"active":false}'),
            ("operation.json", "[]"),
            ("candidate.json", "{"),
        ]:
            with self.subTest(file=filename, raw=raw):
                for name in ("state.json", "operation.json", "candidate.json"):
                    (path / name).unlink(missing_ok=True)
                eco.atomic(path / "state.json", {"version": "fixture", "active": False})
                (path / filename).write_text(raw)
                result = self.manager.status("passwords")
                self.assertTrue(result["needs_recovery"])
                self.assertFalse(result["can_apply"])
                self.assertIn(filename, json.dumps(result["metadata_errors"]))
                with patch.object(eco, "request") as network:
                    with self.assertRaises(eco.ManagerError):
                        self.manager.install("passwords", "preview")
                    network.assert_not_called()
                self.assertEqual((path / filename).read_text(), raw)

    def test_metadata_reader_rejects_nonregular_and_oversized_files(self):
        path = self.root / "passwords"
        path.mkdir(parents=True)
        state = path / "state.json"
        for kind in ("directory", "fifo", "oversized", "symlink"):
            with self.subTest(kind=kind):
                if kind == "directory":
                    state.mkdir()
                elif kind == "fifo":
                    os.mkfifo(state)
                elif kind == "oversized":
                    state.write_text(" " * (1024 * 1024) + "{}")
                else:
                    target = self.root / "foreign"
                    target.write_text("private fixture")
                    state.symlink_to(target)
                with self.assertRaises(eco.MetadataError):
                    eco.read(state)
                if kind == "directory":
                    state.rmdir()
                else:
                    state.unlink()

    def test_null_candidate_cache_is_a_valid_no_release_result(self):
        path = self.root / "passwords"
        eco.atomic(path / "candidate.json", None)
        status = self.manager.status("passwords")
        self.assertFalse(status["needs_recovery"])
        self.assertIsNone(status["candidate"])
        self.assertEqual(status["metadata_errors"], [])

    def test_status_distinguishes_live_operation_from_abandoned_marker(self):
        path = self.root / "passwords"
        eco.atomic(path / "activation.json", {"adapter": "managed"})
        with self.manager.lock("passwords"):
            busy = self.manager.status("passwords")
            self.assertTrue(busy["in_progress"])
            self.assertFalse(busy["needs_recovery"])
            self.assertFalse(busy["can_apply"])
        stopped = self.manager.status("passwords")
        self.assertFalse(stopped["in_progress"])
        self.assertTrue(stopped["needs_recovery"])
        self.assertFalse(stopped["can_apply"])

    def test_progress_label_without_live_lock_is_not_a_running_operation(self):
        eco.atomic(self.root / "passwords/operation.json", {"phase": "preparing"})
        result = self.manager.status("passwords")
        self.assertFalse(result["in_progress"])

    def test_fifo_application_lock_fails_without_hanging(self):
        path = self.root / "passwords"
        path.mkdir(parents=True)
        lock = path / ".lock"
        os.mkfifo(lock)
        helper = Path(__file__).resolve().parents[1] / "assets"
        code = "import sys;sys.path.insert(0,sys.argv[1]);from ecosystem import Manager\nwith Manager(sys.argv[2],False).lock('passwords'): pass"
        try:
            result = subprocess.run(
                [sys.executable, "-c", code, str(helper), str(self.root)],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except subprocess.TimeoutExpired:
            self.fail("A FIFO lock blocked the update process")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid local metadata", result.stderr)
        self.assertTrue(lock.exists())

    def test_nonregular_lock_status_does_not_claim_update_is_available(self):
        path = self.root / "passwords"
        path.mkdir(parents=True)
        os.mkfifo(path / ".lock")
        status = self.manager.status("passwords")
        self.assertTrue(status["needs_recovery"])
        self.assertFalse(status["can_apply"])
        self.assertIn(".lock", json.dumps(status["metadata_errors"]))

    def test_lock_handle_preserves_inode_and_existing_contents(self):
        path = self.root / "control.lock"
        path.parent.mkdir(parents=True)
        path.write_text("existing diagnostic bytes")
        before = path.stat().st_ino
        with eco.lock_handle(path, create=True):
            self.assertEqual(path.stat().st_ino, before)
        self.assertEqual(path.read_text(), "existing diagnostic bytes")
        self.assertEqual(path.stat().st_ino, before)
        new = self.root / "new.lock"
        with eco.lock_handle(new, create=True):
            self.assertEqual(new.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(
        os.geteuid() == 0, "Daemon and privileged lock fixture requires root"
    )
    def test_invalid_application_native_and_daemon_locks_fail_without_mutation(self):
        helper = Path(__file__).resolve().parents[1] / "assets"
        code = """import sys
sys.path.insert(0,sys.argv[1])
from unittest.mock import patch
import ecosystem as e
m=e.Manager(sys.argv[2],False,system_root=sys.argv[3])
try:
    if sys.argv[4]=='app':
        with m.lock('passwords'): pass
    elif sys.argv[4]=='native':
        with m.native_lock('mail'): pass
    else:
        with patch.object(e,'serve_locked',return_value=None): e.serve(m)
except e.ManagerError as error:
    print(str(error));sys.exit(7)
sys.exit(0)
"""
        paths = {
            "app": self.root / "passwords/.lock",
            "native": self.root.parent
            / "var/lib/kagnode-migrations/ecosystem-mail.lock",
            "daemon": self.root / ".manager.lock",
        }
        for scope, path in paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            for kind in ("fifo", "directory", "symlink", "hardlink"):
                with self.subTest(scope=scope, kind=kind):
                    foreign = self.root / "foreign.fixture"
                    foreign.write_text("preserve unrelated data")
                    info = foreign.stat()
                    if kind == "fifo":
                        os.mkfifo(path)
                    elif kind == "directory":
                        path.mkdir()
                    elif kind == "symlink":
                        path.symlink_to(foreign)
                    else:
                        os.link(foreign, path)
                    try:
                        result = subprocess.run(
                            [
                                sys.executable,
                                "-c",
                                code,
                                str(helper),
                                str(self.root),
                                str(self.root.parent),
                                scope,
                            ],
                            capture_output=True,
                            text=True,
                            timeout=2,
                        )
                        self.assertEqual(
                            result.returncode, 7, result.stdout + result.stderr
                        )
                        self.assertTrue(path.exists() or path.is_symlink())
                        self.assertEqual(foreign.read_text(), "preserve unrelated data")
                        self.assertEqual(
                            (foreign.stat().st_ino, foreign.stat().st_mode),
                            (info.st_ino, info.st_mode),
                        )
                    finally:
                        if path.is_dir() and not path.is_symlink():
                            path.rmdir()
                        else:
                            path.unlink(missing_ok=True)
                        foreign.unlink()

    @unittest.skipUnless(
        os.geteuid() == 0, "Privileged ownership fixture requires root"
    )
    def test_privileged_locks_reject_foreign_owner_or_writable_mode(self):
        path = self.root / "control.lock"
        path.parent.mkdir(parents=True)
        path.write_text("preserve lock bytes")
        path.chmod(0o666)
        with self.assertRaises(eco.MetadataError):
            with eco.lock_handle(path, create=True, privileged=True):
                pass
        self.assertEqual(path.stat().st_mode & 0o777, 0o666)
        path.chmod(0o644)
        os.chown(path, 65534, 65534)
        with self.assertRaises(eco.MetadataError):
            with eco.lock_handle(path, create=True, privileged=True):
                pass
        self.assertEqual(path.stat().st_uid, 65534)
        os.chown(path, 0, 0)
        inode = path.stat().st_ino
        with eco.lock_handle(path, create=True, privileged=True):
            pass
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.stat().st_ino, inode)
        self.assertEqual(path.read_text(), "preserve lock bytes")

    def test_checksum_failure_never_activates(self):
        fetch, manifest, _ = self.fixtures()
        next(iter(manifest["assets"].values()))["sha256"] = "0" * 64
        with (
            patch.object(eco, "request", fetch),
            patch.object(self.manager, "prepare") as prepare,
        ):
            with self.assertRaisesRegex(eco.ManagerError, "SHA-256"):
                self.manager.install("passwords", "preview")
            prepare.assert_not_called()
        self.assertFalse((self.root / "passwords/current").exists())

    def test_failed_build_keeps_current_and_data(self):
        fetch, manifest, _ = self.fixtures()
        with patch.object(eco, "request", fetch), patch.object(self.manager, "prepare"):
            self.manager.install("passwords", "preview")
        old = (self.root / "passwords/current").resolve()
        manifest["source_commit"] = "b" * 40
        with (
            patch.object(eco, "request", fetch),
            patch.object(
                self.manager, "prepare", side_effect=eco.ManagerError("build failed")
            ),
        ):
            with self.assertRaises(eco.ManagerError):
                self.manager.install("passwords", "preview")
        self.assertEqual((self.root / "passwords/current").resolve(), old)
        self.assertEqual(
            eco.read(self.root / "passwords/operation.json")["phase"], "failed"
        )

    def test_failed_backup_restarts_old_service_without_activation(self):
        fetch, manifest, _ = self.fixtures()
        with patch.object(eco, "request", fetch), patch.object(self.manager, "prepare"):
            self.manager.install("passwords", "preview")
        path = self.root / "passwords"
        old = (path / "current").resolve()
        eco.atomic(
            path / "state.json", {**eco.read(path / "state.json"), "active": True}
        )
        manifest["source_commit"] = "b" * 40
        with (
            patch.object(eco, "request", fetch),
            patch.object(self.manager, "prepare"),
            patch.object(self.manager, "backup", side_effect=OSError("disk full")),
            patch.object(self.manager, "service") as service,
        ):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.manager.install("passwords", "preview")
        self.assertEqual((path / "current").resolve(), old)
        self.assertEqual(service.call_args_list[-1].args, ("passwords", "start"))
        self.assertFalse(self.manager.status("passwords")["needs_recovery"])

    def test_failed_health_stops_candidate_and_records_recovery(self):
        fetch, manifest, _ = self.fixtures()
        with patch.object(eco, "request", fetch), patch.object(self.manager, "prepare"):
            self.manager.install("passwords", "preview")
        path = self.root / "passwords"
        (path / "data/private.fixture").write_text("retain")
        eco.atomic(
            path / "state.json", {**eco.read(path / "state.json"), "active": True}
        )
        manifest["source_commit"] = "b" * 40
        with (
            patch.object(eco, "request", fetch),
            patch.object(self.manager, "prepare"),
            patch.object(
                self.manager, "healthy", side_effect=eco.ManagerError("unhealthy")
            ),
            patch.object(self.manager, "service") as service,
        ):
            with self.assertRaisesRegex(eco.ManagerError, "unhealthy"):
                self.manager.install("passwords", "preview")
        self.assertFalse(eco.read(path / "state.json")["active"])
        self.assertTrue(eco.read(path / "state.json")["needs_recovery"])
        self.assertEqual((path / "data/private.fixture").read_text(), "retain")
        self.assertEqual(service.call_args_list[-1].args, ("passwords", "stop"))
        self.assertEqual(
            len(list((path / "backups").glob("*/data/private.fixture"))), 1
        )

    def test_simultaneous_install_is_rejected(self):
        with self.manager.lock("passwords"):
            with self.assertRaisesRegex(eco.ManagerError, "already running"):
                with self.manager.lock("passwords"):
                    pass

    def test_managed_symlink_state_is_rejected(self):
        path = self.root / "passwords"
        path.mkdir(parents=True)
        (path / "state.json").symlink_to(self.root / "foreign")
        with self.assertRaises(eco.ManagerError):
            self.manager.status("passwords")

    def test_cli_activation_keeps_existing_executables(self):
        path = self.root / "cli"
        release = path / "releases/fixture"
        release.mkdir(parents=True)
        binary = release / "kagnode"
        binary.write_text("fixture executable")
        binary.chmod(0o755)
        (path / "current").symlink_to("releases/fixture")
        destination = self.root / "bin/kagnode"
        with patch.object(eco, "CLI_LINK", destination):
            self.manager.activate_cli()
            self.assertEqual(destination.resolve(), binary)
            self.assertIn("already active", self.manager.activate_cli()["message"])
            destination.unlink()
            destination.write_text("existing executable")
            with self.assertRaisesRegex(eco.ManagerError, "existing"):
                self.manager.activate_cli()
            self.assertEqual(destination.read_text(), "existing executable")

    def test_bitwarden_plan_is_digest_pinned_and_registration_disabled(self):
        image = "vaultwarden/server@sha256:" + "a" * 64
        result = eco.bitwarden_setup(self.root, "https://vault.example.test", image)
        service = result["compose"]["services"]["vaultwarden"]
        self.assertEqual(service["image"], image)
        self.assertEqual(service["environment"]["SIGNUPS_ALLOWED"], "false")
        self.assertEqual(service["ports"], ["127.0.0.1:8816:80"])
        self.assertFalse(self.root.exists())
        for bad in ["vaultwarden/server:latest", "attacker/server@sha256:" + "a" * 64]:
            with self.assertRaises(eco.ManagerError):
                eco.bitwarden_setup(self.root, "https://vault.example.test", bad)

    @unittest.skipUnless(os.geteuid() == 0, "engine installation requires root")
    def test_bitwarden_setup_keeps_secrets_private_and_preserves_existing_engine(self):
        temp = tempfile.TemporaryDirectory(dir="/root")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "kagnode"
        image = "vaultwarden/server@sha256:" + "a" * 64
        with patch.object(eco.subprocess, "run") as run:
            result = eco.bitwarden_setup(
                self.root, "https://vault.example.test", image, apply=True
            )
            base = self.root / "passwords/bitwarden"
            token = (base / "admin.env").read_text()
            self.assertTrue(token.startswith("ADMIN_TOKEN="))
            self.assertEqual((base / "admin.env").stat().st_mode & 0o777, 0o600)
            self.assertEqual(base.stat().st_mode & 0o777, 0o700)
            self.assertNotIn(token.split("=", 1)[1].strip(), json.dumps(result))
            compose = json.loads((base / "compose.json").read_text())
            service = compose["services"]["vaultwarden"]
            self.assertEqual(service["image"], image)
            self.assertEqual(service["env_file"], ["./admin.env"])
            self.assertEqual(service["environment"]["INVITATIONS_ALLOWED"], "false")
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args_list[0].args[0][-1], "pull")
            self.assertEqual(run.call_args_list[1].args[0][-2:], ["up", "-d"])
            (base / "data/vault-fixture").write_text("retained")
            with self.assertRaisesRegex(eco.ManagerError, "Existing engine"):
                eco.bitwarden_setup(
                    self.root, "https://vault.example.test", image, apply=True
                )
            self.assertEqual((base / "data/vault-fixture").read_text(), "retained")
            self.assertEqual((base / "admin.env").read_text(), token)
            self.assertEqual(run.call_count, 2)


class SignatureTests(unittest.TestCase):
    def test_vpn_rejects_manifest_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            native = Path(tmp)
            manager = eco.Manager(native / "kagnode", False)
            (native / "VERSION").write_text("4.1.0-beta.1")
            key = native / "fixture-key.pem"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "openssl",
                    "pkey",
                    "-in",
                    str(key),
                    "-pubout",
                    "-out",
                    str(native / "release-key.pem"),
                ],
                check=True,
                capture_output=True,
            )
            content = json.dumps(
                {
                    "schema": 1,
                    "version": "4.2.0-beta.1",
                    "platform": "ubuntu-24.04-amd64",
                    "assets": {"update.sh": {"sha256": "a" * 64, "size": 4}},
                }
            ).encode()
            manifest = native / "manifest.json"
            manifest.write_bytes(content)
            signature = native / "manifest.sig"
            subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-sign",
                    "-inkey",
                    str(key),
                    "-rawin",
                    "-in",
                    str(manifest),
                    "-out",
                    str(signature),
                ],
                check=True,
                capture_output=True,
            )
            prefix = "https://github.com/every-lemon/kagnode-vpn/releases/download/v4.2.0-beta.1/"
            release = {
                "id": 5,
                "tag_name": "v4.2.0-beta.1",
                "prerelease": True,
                "assets": [
                    {"name": name, "browser_download_url": prefix + name}
                    for name in ("manifest.json", "manifest.sig", "update.sh")
                ],
            }

            def fetch(url, limit=0):
                if "api.github.com" in url:
                    return json.dumps([release]).encode()
                return (
                    signature.read_bytes()
                    if url.endswith("manifest.sig")
                    else manifest.read_bytes()
                )

            with (
                patch.object(eco, "request", fetch),
                patch.object(manager, "native_root", return_value=native),
            ):
                candidate = manager.check_vpn(native / "vpn", "preview")
                self.assertEqual(candidate["signature"], "verified")
                self.assertTrue(candidate["changed"])
                with self.assertRaises(eco.ManagerError):
                    manager.check_vpn(native / "vpn", "stable")
                manifest.write_bytes(content.replace(b"4.2.0", b"4.3.0"))
                with self.assertRaises(subprocess.CalledProcessError):
                    manager.check_vpn(native / "vpn", "preview")


class SocketManagerTests(unittest.TestCase):
    @unittest.skipUnless(
        os.geteuid() == 0, "Unix socket owner/peer test requires root fixture"
    )
    def test_restart_stale_socket_request_bounds_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "kagnode"
            manager = eco.Manager(root, False)
            eco.atomic(
                root / "manager.json",
                {"panels": {"passwords": {"uid": 65533, "gid": 65534}}},
            )
            Path(tmp).chmod(0o755)
            root.chmod(0o755)
            (root / "run").mkdir()
            path = root / "run/passwords.sock"
            stale = socket.socket(socket.AF_UNIX)
            stale.bind(str(path))
            stale.close()
            eco.atomic(root / "passwords/operation.json", {"phase": "preparing"})
            for iteration in range(3):
                if iteration == 2:
                    (root / "passwords/operation.json").write_text("{")
                stop = threading.Event()
                errors = []

                def start():
                    try:
                        eco.serve(manager, stop)
                    except Exception as error:
                        errors.append(error)

                thread = threading.Thread(target=start)
                thread.start()
                try:
                    deadline = time.monotonic() + 4
                    while True:
                        try:
                            connection = socket.socket(socket.AF_UNIX)
                            connection.settimeout(1)
                            connection.connect(str(path))
                            break
                        except OSError:
                            connection.close()
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(0.02)
                    body = b'{"action":"state"}'
                    connection.sendall(
                        b"POST / HTTP/1.0\r\nContent-Length: "
                        + str(len(body)).encode()
                        + b"\r\n\r\n"
                        + body
                    )
                    response = b""
                    while chunk := connection.recv(65536):
                        response += chunk
                    connection.close()
                    self.assertIn(b"200 OK", response)
                    if iteration < 2:
                        self.assertIn(b'"interrupted"', response)
                    else:
                        payload = json.loads(response.split(b"\r\n\r\n", 1)[1])
                        self.assertFalse(payload["can_apply"])
                        self.assertEqual(
                            payload["metadata_errors"][0]["file"], "operation.json"
                        )
                        self.assertEqual(
                            (root / "passwords/operation.json").read_text(), "{"
                        )
                        eco.atomic(root / "passwords/state.json", [])
                        with patch.object(eco, "request") as network:
                            for action in ("state", "check"):
                                with socket.socket(socket.AF_UNIX) as fresh:
                                    fresh.connect(str(path))
                                    data = json.dumps({"action": action}).encode()
                                    fresh.sendall(
                                        b"POST / HTTP/1.0\r\nContent-Length: "
                                        + str(len(data)).encode()
                                        + b"\r\n\r\n"
                                        + data
                                    )
                                    result = b""
                                    while chunk := fresh.recv(65536):
                                        result += chunk
                                    self.assertIn(
                                        b"200 OK"
                                        if action == "state"
                                        else b"400 Bad Request",
                                        result,
                                    )
                                    self.assertIn(b"state.json", result)
                            network.assert_not_called()
                        self.assertEqual(
                            json.loads((root / "passwords/state.json").read_text()), []
                        )
                    probe = subprocess.run(
                        [
                            eco.sys.executable,
                            "-c",
                            'import socket,sys;s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1]);s.sendall(b\'POST / HTTP/1.0\\r\\nContent-Length: 18\\r\\n\\r\\n{"action":"state"}\');print(s.recv(65536).decode())',
                            str(path),
                        ],
                        user=65534,
                        group=65534,
                        extra_groups=[],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    self.assertEqual(probe.returncode, 0, probe.stderr)
                    self.assertIn("400 Bad Request", probe.stdout)
                    with self.assertRaisesRegex(eco.ManagerError, "already running"):
                        eco.serve(manager, threading.Event())
                    with socket.socket(socket.AF_UNIX) as connection:
                        connection.connect(str(path))
                        connection.sendall(
                            b"POST / HTTP/1.0\r\nContent-Length: 999999\r\n\r\n"
                        )
                        self.assertIn(b"400 Bad Request", connection.recv(65536))
                finally:
                    stop.set()
                    thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
                self.assertFalse(path.exists())
                self.assertEqual(errors, [])


class NativeAdapters(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.manager = eco.Manager(self.root / "kagnode", False)
        self.native = self.root / "native"
        self.native.mkdir()
        self.release = self.root / "new"
        self.release.mkdir()
        for directory in [self.native, self.release]:
            (directory / "schema").write_text("unchanged schema")
            (directory / "web").mkdir()
        (self.native / "web/app.py").write_text("old web")
        (self.release / "web/app.py").write_text("new web")
        self.profile = {
            "code": str(self.native),
            "guards": ["schema"],
            "payload": ["web"],
            "services": ["fake.service"],
        }
        self.state = {
            "native_binding": {
                "profile": "mail",
                "guards": {
                    "schema": eco.hashlib.sha256(b"unchanged schema").hexdigest()
                },
            }
        }
        self.app = self.root / "kagnode/mail"
        self.app.mkdir(parents=True)

    def test_missing_or_extra_native_guards_cannot_skip_checks(self):
        for guards in ({}, {"schema": "0" * 64, "../foreign": "0" * 64}):
            with (
                self.subTest(guards=guards),
                patch.dict(eco.NATIVE_PROFILES, {"mail": self.profile}),
                patch.object(self.manager, "native_root") as native,
                patch.object(eco.subprocess, "run") as run,
            ):
                state = {"native_binding": {"profile": "mail", "guards": guards}}
                with self.assertRaisesRegex(eco.ManagerError, "guard inventory"):
                    self.manager.apply_native("mail", self.app, self.release, state)
                native.assert_not_called()
                run.assert_not_called()

    def test_native_web_update_does_not_touch_user_data(self):
        (self.native / "private.sqlite3").write_bytes(b"keep user data")
        with (
            patch.dict(eco.NATIVE_PROFILES, {"mail": self.profile}),
            patch.object(self.manager, "native_root", return_value=self.native),
            patch.object(eco.subprocess, "run") as run,
        ):
            run.return_value.returncode = 0
            self.manager.apply_native("mail", self.app, self.release, self.state)
        self.assertEqual((self.native / "web/app.py").read_text(), "new web")
        self.assertEqual(
            (self.native / "private.sqlite3").read_bytes(), b"keep user data"
        )
        saved = list((self.app / "backups").glob("native-*/web/app.py"))
        self.assertEqual(saved[0].read_text(), "old web")

    def test_schema_changes_fail_before_stopping_services(self):
        (self.release / "schema").write_text("changed schema")
        with (
            patch.dict(eco.NATIVE_PROFILES, {"mail": self.profile}),
            patch.object(self.manager, "native_root", return_value=self.native),
            patch.object(eco.subprocess, "run") as run,
        ):
            with self.assertRaisesRegex(eco.ManagerError, "guard changed"):
                self.manager.apply_native("mail", self.app, self.release, self.state)
            run.assert_not_called()
        self.assertEqual((self.native / "web/app.py").read_text(), "old web")

    def test_failed_native_activation_rolls_back_code_only(self):
        def run(args, **kwargs):
            if args[1] == "start" and kwargs.get("check"):
                raise eco.subprocess.CalledProcessError(1, args)
            return eco.subprocess.CompletedProcess(args, 0)

        with (
            patch.dict(eco.NATIVE_PROFILES, {"mail": self.profile}),
            patch.object(self.manager, "native_root", return_value=self.native),
            patch.object(eco.subprocess, "run", side_effect=run),
        ):
            with self.assertRaises(eco.subprocess.CalledProcessError):
                self.manager.apply_native("mail", self.app, self.release, self.state)
        self.assertEqual((self.native / "web/app.py").read_text(), "old web")

    def migration_fixture(self):
        source = self.root / "opt/kagnode/mail/kagnode"
        source.mkdir(parents=True)
        (source / "web.py").write_text("identity fixture")
        data = self.root / "var/lib/kagnode/mail"
        data.mkdir(parents=True)
        (data / "directory.sqlite3").write_text("fixture data")
        script = Path(__file__).resolve().parents[1] / "assets/consolidate.py"
        return script, [
            "python3",
            str(script),
            "mail",
            "--root",
            str(self.root),
            "--destination",
            "/srv/kagnode",
        ]

    def test_migration_rejects_foreign_record_before_moving_any_source(self):
        _, args = self.migration_fixture()
        plan = json.loads(subprocess.check_output(args))
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        (unrelated / "private.fixture").write_text("not part of Mail")
        plan["records"][1].update(
            old="/unrelated", backup="unrelated.before-kagnode-ecosystem-mail"
        )
        journal = self.root / "journal.json"
        journal.write_text(json.dumps(plan))
        result = subprocess.run(
            args + ["--apply", "--journal", str(journal)],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid migration journal", result.stderr)
        self.assertFalse((self.root / "opt/kagnode/mail").is_symlink())
        self.assertEqual(
            (unrelated / "private.fixture").read_text(), "not part of Mail"
        )

    def test_mail_portal_guard_rejects_mixed_installation(self):
        _, args = self.migration_fixture()
        source = self.root / "opt/kagnode/mail"
        (source / "PLAN.md").write_text("portal content; preserve")
        result = subprocess.run(args + ["--apply"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("portal data", result.stderr)
        self.assertFalse(source.is_symlink())
        self.assertEqual((source / "PLAN.md").read_text(), "portal content; preserve")

    def test_malformed_journals_fail_readably_without_moving_files(self):
        _, args = self.migration_fixture()
        plan = json.loads(subprocess.check_output(args))
        cases = []
        for key, values in {
            "schema": [2, True],
            "created": [-1, "now", True],
            "status": ["running", {}],
            "records": [None, {}, [], ["record"]],
        }.items():
            for value in values:
                document = copy.deepcopy(plan)
                document[key] = value
                cases.append((key + repr(value), document))
        for key, values in {
            "old": ["/unrelated", "/opt/kagnode/mail/../mail", []],
            "new": ["/unrelated", "../escape"],
            "backup": [str(self.root / "unrelated"), "../escape"],
            "stage": ["finished", "copying", {}],
            "digest": ["z" * 64, 42],
            "retained_new": ["../escape", "/absolute/path"],
        }.items():
            for value in values:
                document = copy.deepcopy(plan)
                document["records"][0][key] = value
                cases.append((key + repr(value), document))
        for label, records in [
            ("duplicate", plan["records"] + [plan["records"][0]]),
            ("missing runtime", plan["records"][1:]),
            ("out of order", list(reversed(plan["records"]))),
        ]:
            document = copy.deepcopy(plan)
            document["records"] = records
            cases.append((label, document))
        document = copy.deepcopy(plan)
        document["status"] = "complete"
        cases.append(("false completion", document))
        cases.append(("top-level array", []))
        raw_cases = [(label, json.dumps(doc)) for label, doc in cases]
        raw_cases.extend(
            [
                ("invalid JSON", "{"),
                ("duplicate field", '{"project":"ecosystem-mail","project":"other"}'),
            ]
        )
        journal = self.root / "journal.json"
        for label, raw in raw_cases:
            with self.subTest(case=label):
                journal.write_text(raw)
                result = subprocess.run(
                    args + ["--journal", str(journal)], capture_output=True, text=True
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid migration journal", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(journal.read_text(), raw)
                self.assertFalse((self.root / "opt/kagnode/mail").is_symlink())
        self.assertFalse((self.root / "srv").exists())

    def test_saved_inventory_mismatch_stops_before_other_records_move(self):
        _, args = self.migration_fixture()
        plan = json.loads(subprocess.check_output(args))
        plan["records"][1].update(stage="ready", digest="0" * 64)
        journal = self.root / "journal.json"
        saved = json.dumps(plan)
        journal.write_text(saved)
        result = subprocess.run(
            args + ["--apply", "--journal", str(journal)],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("original inventory changed", result.stderr)
        self.assertFalse((self.root / "opt/kagnode/mail").is_symlink())
        self.assertFalse((self.root / "var/lib/kagnode/mail").is_symlink())
        self.assertEqual(journal.read_text(), saved)
        self.assertEqual(
            (self.root / "var/lib/kagnode/mail/directory.sqlite3").read_text(),
            "fixture data",
        )

    def test_backup_symlink_cannot_supply_foreign_data(self):
        _, args = self.migration_fixture()
        plan = json.loads(subprocess.check_output(args))
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        backup = self.root / plan["records"][0]["backup"]
        backup.symlink_to(unrelated, target_is_directory=True)
        journal = self.root / "journal.json"
        journal.write_text(json.dumps(plan))
        result = subprocess.run(
            args + ["--apply", "--journal", str(journal)],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid migration journal", result.stderr)
        self.assertFalse((self.root / "opt/kagnode/mail").is_symlink())
        self.assertTrue(backup.is_symlink())

    def test_journal_cannot_move_with_application_or_follow_symlink_parent(self):
        _, args = self.migration_fixture()
        plan = json.loads(subprocess.check_output(args))
        inside = self.root / "opt/kagnode/mail/journal.json"
        inside.write_text(json.dumps(plan))
        result = subprocess.run(
            args + ["--apply", "--journal", str(inside)], capture_output=True, text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("journal must remain outside", result.stderr)
        self.assertFalse((self.root / "opt/kagnode/mail").is_symlink())
        external = self.root / "external"
        external.mkdir()
        (external / "journal.json").write_text(json.dumps(plan))
        link = self.root / "link"
        link.symlink_to(external, target_is_directory=True)
        result = subprocess.run(
            args + ["--journal", str(link / "journal.json")],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)

    def test_nonregular_and_oversized_journals_are_rejected(self):
        _, args = self.migration_fixture()
        for name in ("directory", "fifo", "oversized"):
            journal = self.root / name
            if name == "directory":
                journal.mkdir()
            elif name == "fifo":
                os.mkfifo(journal)
            else:
                journal.write_text(" " * (1024 * 1024) + "{}")
            with self.subTest(kind=name):
                result = subprocess.run(
                    args + ["--journal", str(journal)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("regular JSON file", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_unknown_destination_link_and_missing_rollback_backup_are_rejected(self):
        _, args = self.migration_fixture()
        subprocess.run(args + ["--apply"], check=True, capture_output=True)
        source = self.root / "opt/kagnode/mail"
        target = source.resolve()
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        source.unlink()
        source.symlink_to(unrelated, target_is_directory=True)
        result = subprocess.run(args + ["--apply"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source link", result.stderr)
        source.unlink()
        source.symlink_to(target, target_is_directory=True)
        backup = self.root / "opt/kagnode/mail.before-kagnode-ecosystem-mail"
        backup.rename(backup.with_name("retained-outside-journal"))
        result = subprocess.run(args + ["--rollback"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("retained original is missing", result.stderr)
        self.assertTrue(source.is_symlink())
        self.assertTrue(target.is_dir())
        self.assertEqual(
            (self.root / "srv/kagnode/mail/data/directory.sqlite3").read_text(),
            "fixture data",
        )

    def test_interrupted_rollback_resumes_without_losing_new_writes(self):
        script, args = self.migration_fixture()
        subprocess.run(args + ["--apply"], check=True, capture_output=True)
        data = self.root / "srv/kagnode/mail/data"
        (data / "new-message").write_text("keep new writes")
        spec = importlib.util.spec_from_file_location("rollback_fixture", script)
        migration = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"ecosystem": eco}):
            spec.loader.exec_module(migration)
        backup = self.root / "var/lib/kagnode/mail.before-kagnode-ecosystem-mail"
        original_rename = Path.rename
        child = os.fork()
        if child == 0:
            try:

                def restore_then_kill(source, target):
                    result = original_rename(source, target)
                    if source == backup:
                        os.kill(os.getpid(), signal.SIGKILL)
                    return result

                with (
                    patch.object(sys, "argv", args[1:] + ["--rollback"]),
                    patch.object(Path, "rename", restore_then_kill),
                ):
                    migration.main()
            finally:
                os._exit(99)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), -signal.SIGKILL)
        journal = self.root / "var/lib/kagnode-migrations/ecosystem-mail.json"
        self.assertEqual(json.loads(journal.read_text())["status"], "rolling-back")
        wrong = subprocess.run(args + ["--apply"], capture_output=True, text=True)
        self.assertNotEqual(wrong.returncode, 0)
        self.assertIn("resume with --rollback", wrong.stderr)
        subprocess.run(args + ["--rollback"], check=True, capture_output=True)
        restored = self.root / "var/lib/kagnode/mail"
        self.assertFalse(restored.is_symlink())
        self.assertEqual((restored / "directory.sqlite3").read_text(), "fixture data")
        final = json.loads(journal.read_text())
        self.assertEqual(final["status"], "rolled-back")
        self.assertTrue(all(row["stage"] == "rolled-back" for row in final["records"]))
        row = next(row for row in final["records"] if row["new"].endswith("/data"))
        self.assertEqual(
            (self.root / row["retained_new"] / "new-message").read_text(),
            "keep new writes",
        )
        manager = eco.Manager(self.root / "srv/kagnode", False, system_root=self.root)
        self.assertFalse(manager.status("mail")["needs_recovery"])

    def test_rollback_collision_is_rejected_before_removing_links(self):
        _, args = self.migration_fixture()
        subprocess.run(args + ["--apply"], check=True, capture_output=True)
        journal = self.root / "var/lib/kagnode-migrations/ecosystem-mail.json"
        plan = json.loads(journal.read_text())
        row = plan["records"][1]
        row["retained_new"] = row["new"].lstrip("/") + ".after-migration-123"
        retained = self.root / row["retained_new"]
        retained.mkdir()
        (retained / "private.fixture").write_text("retain older quarantine")
        journal.write_text(json.dumps(plan))
        saved = journal.read_bytes()
        result = subprocess.run(args + ["--rollback"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("retained-write destination already exists", result.stderr)
        self.assertTrue((self.root / "var/lib/kagnode/mail").is_symlink())
        self.assertTrue((self.root / "opt/kagnode/mail").is_symlink())
        self.assertEqual(journal.read_bytes(), saved)
        self.assertEqual(
            (retained / "private.fixture").read_text(), "retain older quarantine"
        )

    def test_corrupt_migration_marker_has_readable_failure(self):
        _, args = self.migration_fixture()
        manager = eco.Manager(self.root / "srv/kagnode", False, system_root=self.root)
        with manager.lock("mail"):
            marker = manager.migration_marker("mail")
            marker.write_text("{")
        result = subprocess.run(args + ["--apply"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid migration journal", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.root / "opt/kagnode/mail").is_symlink())
        self.assertEqual(marker.read_text(), "{")

    def test_legacy_journal_without_schema_still_resumes(self):
        _, args = self.migration_fixture()
        plan = json.loads(subprocess.check_output(args))
        plan.pop("schema", None)
        journal = self.root / "legacy-journal.json"
        journal.write_text(json.dumps(plan))
        subprocess.run(
            args + ["--apply", "--journal", str(journal)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            args + ["--rollback", "--journal", str(journal)],
            check=True,
            capture_output=True,
        )
        self.assertFalse((self.root / "var/lib/kagnode/mail").is_symlink())
        self.assertEqual(
            (self.root / "var/lib/kagnode/mail/directory.sqlite3").read_text(),
            "fixture data",
        )

    def test_migration_preview_creates_no_locks_or_destination(self):
        _, args = self.migration_fixture()
        subprocess.run(args, check=True, capture_output=True)
        self.assertFalse((self.root / "srv").exists())
        self.assertFalse((self.root / "var/lib/kagnode-migrations").exists())
        self.assertFalse((self.root / "opt/kagnode/mail").is_symlink())

    def test_migration_rejects_running_update_before_moving_files(self):
        _, args = self.migration_fixture()
        manager = eco.Manager(self.root / "srv/kagnode", False)
        with manager.lock("mail"):
            result = subprocess.run(args + ["--apply"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another operation", result.stderr)
        self.assertFalse((self.root / "opt/kagnode/mail").is_symlink())
        self.assertEqual(
            (self.root / "var/lib/kagnode/mail/directory.sqlite3").read_text(),
            "fixture data",
        )

    def test_migration_rejects_unresolved_update_recovery(self):
        _, args = self.migration_fixture()
        manager = eco.Manager(self.root / "srv/kagnode", False)
        with manager.lock("mail") as path:
            eco.atomic(path / "activation.json", {"adapter": "native-web"})
        result = subprocess.run(args + ["--apply"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("recovery review", result.stderr)
        self.assertFalse((self.root / "opt/kagnode/mail").is_symlink())

    def test_native_lock_is_shared_across_destination_roots(self):
        _, args = self.migration_fixture()
        other = eco.Manager(self.root / "other/root", False, system_root=self.root)
        with other.lock("mail"):
            result = subprocess.run(args + ["--apply"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another operation", result.stderr)
        self.assertFalse((self.root / "opt/kagnode/mail").is_symlink())

    def test_killed_migration_blocks_updates_then_resumes_without_data_loss(self):
        script, args = self.migration_fixture()
        spec = importlib.util.spec_from_file_location("consolidation_fixture", script)
        migration = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"ecosystem": eco}):
            spec.loader.exec_module(migration)
        child = os.fork()
        if child == 0:
            try:

                def kill_before_copy(command, **kwargs):
                    if command[0] == "cp":
                        os.kill(os.getpid(), signal.SIGKILL)
                    raise AssertionError(
                        "Unexpected process in isolated migration fixture"
                    )

                with (
                    patch.object(sys, "argv", args[1:] + ["--apply"]),
                    patch.object(eco.subprocess, "run", side_effect=kill_before_copy),
                ):
                    migration.main()
            finally:
                os._exit(99)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), -signal.SIGKILL)
        manager = eco.Manager(self.root / "srv/kagnode", False, system_root=self.root)
        self.assertTrue(manager.status("mail")["needs_recovery"])
        self.assertFalse(manager.status("mail")["can_apply"])
        other = eco.Manager(self.root / "other/root", False, system_root=self.root)
        self.assertTrue(other.status("mail")["needs_recovery"])
        with patch.object(eco, "request") as network:
            with self.assertRaisesRegex(eco.ManagerError, "recovery review"):
                other.install("mail", "preview")
            network.assert_not_called()
        wrong = subprocess.run(
            args + ["--apply", "--journal", str(self.root / "other-journal.json")],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(wrong.returncode, 0)
        self.assertIn("another journal", wrong.stderr)
        subprocess.run(args + ["--apply"], check=True, capture_output=True)
        self.assertFalse(manager.status("mail")["needs_recovery"])
        self.assertFalse(other.status("mail")["needs_recovery"])
        self.assertEqual(
            (self.root / "srv/kagnode/mail/data/directory.sqlite3").read_text(),
            "fixture data",
        )
        self.assertTrue((self.root / "opt/kagnode/mail").is_symlink())

    def test_false_complete_legacy_journal_requires_recovery(self):
        manager = eco.Manager(self.root / "srv/kagnode", False, system_root=self.root)
        journal = self.root / "var/lib/kagnode-migrations/ecosystem-mail.json"
        for records in ([], [{"stage": "rolled-back"}], [{"stage": "complete"}]):
            with self.subTest(records=records):
                eco.atomic(journal, {"status": "complete", "records": records})
                result = manager.status("mail")
                self.assertTrue(result["needs_recovery"])
                self.assertFalse(result["can_apply"])

    def test_legacy_complete_label_cannot_hide_partial_rollback(self):
        _, args = self.migration_fixture()
        subprocess.run(args + ["--apply"], check=True, capture_output=True)
        journal = self.root / "var/lib/kagnode-migrations/ecosystem-mail.json"
        previous = json.loads(journal.read_text())
        previous["records"][1]["stage"] = "rolled-back"
        eco.atomic(journal, previous)
        before = journal.read_bytes()
        manager = eco.Manager(self.root / "srv/kagnode", False, system_root=self.root)
        result = manager.status("mail")
        self.assertTrue(result["needs_recovery"])
        self.assertFalse(result["can_apply"])
        self.assertEqual(journal.read_bytes(), before)

    def test_legacy_incomplete_journal_also_blocks_native_updates(self):
        _, args = self.migration_fixture()
        plan = json.loads(subprocess.check_output(args))
        plan.pop("schema", None)
        manager = eco.Manager(self.root / "srv/kagnode", False, system_root=self.root)
        journal = self.root / "var/lib/kagnode-migrations/ecosystem-mail.json"
        eco.atomic(journal, plan)
        self.assertTrue(manager.status("mail")["needs_recovery"])
        subprocess.run(args + ["--apply"], check=True, capture_output=True)
        self.assertFalse(manager.status("mail")["needs_recovery"])

    def test_migration_retains_originals_and_new_writes_on_rollback(self):
        import subprocess

        script = Path(__file__).resolve().parents[1] / "assets/consolidate.py"
        source = self.root / "opt/kagnode/mail/kagnode"
        source.mkdir(parents=True)
        (source / "web.py").write_text("identity fixture")
        data = self.root / "var/lib/kagnode/mail"
        data.mkdir(parents=True)
        (data / "directory.sqlite3").write_text("fixture data")
        args = [
            "python3",
            str(script),
            "mail",
            "--root",
            str(self.root),
            "--destination",
            "/srv/kagnode",
        ]
        subprocess.run(args + ["--apply"], check=True, capture_output=True)
        relocated = self.root / "srv/kagnode/mail/data"
        self.assertEqual((relocated / "directory.sqlite3").read_text(), "fixture data")
        self.assertTrue(data.is_symlink())
        (relocated / "new-message").write_text("keep new writes")
        subprocess.run(args + ["--rollback"], check=True, capture_output=True)
        self.assertFalse(data.is_symlink())
        self.assertEqual((data / "directory.sqlite3").read_text(), "fixture data")
        retained = list(
            (self.root / "srv/kagnode/mail").glob("data.after-migration-*/new-message")
        )
        self.assertEqual(retained[0].read_text(), "keep new writes")
