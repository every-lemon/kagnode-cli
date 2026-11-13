"""Project installer orchestration; no packages, services or host configuration."""

import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import signal
import time
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets"))
import ecosystem as eco
import installer
from installer_protocol import (
    plan_digest,
    read_request,
    reviewed_plan,
    write_result,
    ProtocolError,
)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "apps"
        self.manager = eco.Manager(self.root, False)
        self.app = self.root / "mail"
        self.release = self.app / "releases" / "5.0.1"
        (self.release / "scripts").mkdir(parents=True)
        (self.release / "scripts/kagnode-installer.py").write_text("# fixture")
        (self.app / "current").symlink_to(self.release)
        (self.app / "state.json").write_text(json.dumps({"version": "5.0.1"}))
        self.review = Path(self.temporary.name) / "review.json"

    def plan(self, request):
        value = {
            "schema": 1,
            "project": "mail",
            "operation_id": request["operation_id"],
            "supported": True,
            "manual_steps": [],
            "changes": ["fixture configuration"],
            "managed_paths": ["/retained-native-path"],
        }
        value["plan_sha256"] = plan_digest(value)
        return value

    def fixture(self, adapter, action, request):
        if action == "plan":
            return self.plan(request)
        return {
            "schema": 1,
            "project": "mail",
            "operation_id": request["operation_id"],
            "state": "completed",
            "health": {"ok": True},
        }

    def test_reviewed_apply_requires_fresh_plan_and_separate_health(self):
        calls = []

        def invoke(adapter, action, request):
            calls.append(action)
            return self.fixture(adapter, action, request)

        with patch.object(installer, "invoke", side_effect=invoke):
            installer.operate(self.manager, "mail", "plan", save_plan=self.review)
            installer.operate(self.manager, "mail", "apply", review_file=self.review)
        self.assertEqual(calls, ["plan", "plan", "apply", "health"])
        self.assertEqual(
            json.loads((self.app / "setup-operation.json").read_text())["state"],
            "completed",
        )

    def test_plan_drift_and_unsupported_capability_never_apply(self):
        with patch.object(installer, "invoke", side_effect=self.fixture):
            installer.operate(self.manager, "mail", "plan", save_plan=self.review)

        def drift(adapter, action, request):
            value = self.plan(request)
            value["changes"] = ["different"]
            value["plan_sha256"] = plan_digest(value)
            return value

        with patch.object(installer, "invoke", side_effect=drift) as invoked:
            with self.assertRaisesRegex(ProtocolError, "changed"):
                installer.operate(
                    self.manager, "mail", "apply", review_file=self.review
                )
            self.assertEqual(invoked.call_count, 1)
        self.assertFalse((self.app / "setup-operation.json").exists())

    def test_zero_exit_without_health_cannot_claim_success(self):
        with patch.object(installer, "invoke", side_effect=self.fixture):
            installer.operate(self.manager, "mail", "plan", save_plan=self.review)

        def failure(adapter, action, request):
            value = self.fixture(adapter, action, request)
            if action == "apply":
                value["health"]["ok"] = False
            return value

        with patch.object(installer, "invoke", side_effect=failure):
            with self.assertRaisesRegex(ProtocolError, "healthy"):
                installer.operate(
                    self.manager, "mail", "apply", review_file=self.review
                )
        self.assertEqual(
            json.loads((self.app / "setup-operation.json").read_text())["state"],
            "needs_recovery",
        )

    def test_missing_adapter_and_external_current_rejected(self):
        (self.release / "scripts/kagnode-installer.py").unlink()
        with self.assertRaisesRegex(ProtocolError, "no typed installer"):
            installer.operate(self.manager, "mail", "plan")
        (self.app / "current").unlink()
        (self.app / "current").symlink_to(Path(self.temporary.name))
        with self.assertRaisesRegex(ProtocolError, "outside"):
            installer.operate(self.manager, "mail", "plan")

    def test_private_files_reject_symlinks_hardlinks_and_fifo_without_hanging(self):
        source = Path(self.temporary.name) / "input.json"
        source.write_text("{}")
        source.chmod(0o600)
        hard = source.with_name("hard")
        os.link(source, hard)
        with self.assertRaises(ProtocolError):
            installer.private_json(hard)
        hard.unlink()
        link = source.with_name("link")
        link.symlink_to(source)
        with self.assertRaises(OSError):
            installer.private_json(link)
        fifo = source.with_name("fifo")
        os.mkfifo(fifo)
        with self.assertRaises(ProtocolError):
            installer.private_json(fifo)

    def test_changed_adapter_requires_new_review(self):
        with patch.object(installer, "invoke", side_effect=self.fixture):
            installer.operate(self.manager, "mail", "plan", save_plan=self.review)
        (self.release / "scripts/kagnode-installer.py").write_text("# changed fixture")
        with patch.object(installer, "invoke") as invoked:
            with self.assertRaisesRegex(ProtocolError, "source changed"):
                installer.operate(
                    self.manager, "mail", "apply", review_file=self.review
                )
            invoked.assert_not_called()

    def test_recovery_needs_fresh_recovery_intent(self):
        with patch.object(installer, "invoke", side_effect=self.fixture):
            installer.operate(self.manager, "mail", "plan", save_plan=self.review)
            with self.assertRaisesRegex(ProtocolError, "intent"):
                installer.operate(
                    self.manager, "mail", "recover", review_file=self.review
                )
        original = json.loads(self.review.read_text())["request"]

        def failure(adapter, action, request):
            value = self.fixture(adapter, action, request)
            if action == "apply":
                value["health"]["ok"] = False
            return value

        with patch.object(installer, "invoke", side_effect=failure):
            with self.assertRaises(ProtocolError):
                installer.operate(
                    self.manager, "mail", "apply", review_file=self.review
                )
        self.review.unlink()
        with patch.object(installer, "invoke", side_effect=self.fixture):
            installer.operate(
                self.manager, "mail", "plan", save_plan=self.review, recovery=True
            )
            reviewed = json.loads(self.review.read_text())["request"]
            self.assertEqual(reviewed["operation_id"], original["operation_id"])
            self.assertEqual(reviewed["intent"], "recover")
            installer.operate(self.manager, "mail", "recover", review_file=self.review)
        self.assertEqual(
            json.loads((self.app / "setup-operation.json").read_text())["state"],
            "completed",
        )

    def test_interactive_apply_requires_real_terminal(self):
        def interactive(adapter, action, request):
            value = self.plan(request)
            value["interactive"] = True
            value["plan_sha256"] = plan_digest(value)
            return value

        with patch.object(installer, "invoke", side_effect=interactive):
            installer.operate(self.manager, "mail", "plan", save_plan=self.review)
            with patch.object(sys.stdin, "isatty", return_value=False):
                with self.assertRaisesRegex(ProtocolError, "real terminal"):
                    installer.operate(
                        self.manager, "mail", "apply", review_file=self.review
                    )
        self.assertFalse((self.app / "setup-operation.json").exists())

    def test_json_ambiguity_is_rejected(self):
        for raw in ('{"root":"one","root":"two"}', '{"number":NaN}'):
            self.review.write_text(raw)
            self.review.chmod(0o600)
            with self.assertRaises(ProtocolError):
                installer.private_json(self.review)

    def test_fresh_application_source_does_not_provision_dependencies(self):
        path = self.root / "passwords"
        path.mkdir()
        with (
            patch.object(self.manager, "user") as user,
            patch.object(eco.subprocess, "run") as run,
        ):
            self.manager.prepare("passwords", path, self.release)
            user.assert_not_called()
            run.assert_not_called()

    def test_cancelled_helper_reaps_its_owned_wrapper(self):
        marker = Path(self.temporary.name) / "child-pid"
        script = self.release / "scripts/kagnode-installer.py"
        script.write_text(
            "import os,time\nfrom pathlib import Path\nPath("
            + repr(str(marker))
            + ").write_text(str(os.getpid()))\ntime.sleep(60)\n"
        )
        code = "import sys;from pathlib import Path;import installer;installer.invoke(Path(sys.argv[1]),'apply',{})"
        child = subprocess.Popen(
            [sys.executable, "-c", code, str(script)],
            env={**os.environ, "PYTHONPATH": str(Path(eco.__file__).parent)},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(marker.exists())
            wrapper_pid = int(marker.read_text())
            child.send_signal(signal.SIGTERM)
            child.wait(timeout=5)
            self.assertNotEqual(child.returncode, 0)
            self.assertFalse(Path("/proc", str(wrapper_pid)).exists())
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()

    def test_output_never_replaces_existing_file(self):
        self.review.write_text("retained")
        self.review.chmod(0o600)
        with self.assertRaises(ProtocolError):
            write_result(self.review, {"new": True})
        self.assertEqual(self.review.read_text(), "retained")


if __name__ == "__main__":
    unittest.main()
