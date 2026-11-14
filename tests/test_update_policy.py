import datetime
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

s = importlib.util.spec_from_file_location(
    "ecosystem_policy", Path(__file__).resolve().parents[1] / "assets/ecosystem.py"
)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)


class Policies(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        manager = m.Manager(Path(temp.name), False)
        return manager

    def test_conflicts_and_channels(self):
        manager = self.fixture()
        self.assertEqual(manager.update_policy("passwords")["mode"], "manual")
        window = {"start": "23:00", "end": "02:00", "timezone": "Asia/Taipei"}
        policy = manager.policy("passwords", "beta", "auto", window, 0)
        self.assertEqual(policy["revision"], 1)
        self.assertEqual(policy["channel"], "beta")
        with self.assertRaises(m.ManagerError):
            manager.policy("passwords", "stable", "manual", window, 0)
        for key, value in [("start", "25:00"), ("timezone", "invalid/timezone")]:
            with self.assertRaises(m.ManagerError):
                manager.policy("passwords", "beta", "auto", {**window, key: value}, 1)

    def test_timezone_and_overnight_window(self):
        policy = {
            "window": {"start": "23:00", "end": "02:00", "timezone": "Asia/Taipei"}
        }
        self.assertTrue(
            m.Manager.in_window(
                policy,
                datetime.datetime(2026, 11, 14, 16, tzinfo=datetime.timezone.utc),
            )
        )
        self.assertFalse(
            m.Manager.in_window(
                policy, datetime.datetime(2026, 11, 14, 5, tzinfo=datetime.timezone.utc)
            )
        )

    def test_auto_requires_signed_specific_compatibility(self):
        state = {"version": "5.0.1"}
        candidate = {
            "version": "5.0.2",
            "signature_verified": True,
            "automatic_update": {
                "schema": 1,
                "from_versions": ["5.0.1"],
                "scope": "native-runtime",
                "data_compatibility": "backward-compatible",
                "requires_engine_change": False,
                "requires_hardware_build": False,
            },
        }
        self.assertTrue(m.Manager.automatic_eligible(state, candidate))
        for broken in [
            {**candidate, "signature_verified": False},
            {**candidate, "automatic_update": None},
            {**candidate, "version": "5.1.0"},
        ]:
            self.assertFalse(m.Manager.automatic_eligible(state, broken))
        self.assertFalse(m.Manager.automatic_eligible({"version": "5.0.0"}, candidate))

    def test_pm_catalog_preserves_technical_identifier(self):
        manager = self.fixture()
        self.assertEqual(manager.project("pm")[0], "proxy-manager")
        self.assertEqual(m.CATALOG["proxy-manager"]["repo"], "kagnode-pm")
