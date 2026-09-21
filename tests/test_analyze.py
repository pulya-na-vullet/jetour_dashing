"""Parser tests using the synthetic demo session."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hu_diag.analyze import analyze_session, write_report
from hu_diag.demo import write_demo_session


class DemoAnalyzeTest(unittest.TestCase):
    def test_no_camera2_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "hu_diag_demo"
            write_demo_session(session)
            report = write_report(session)
            self.assertEqual(report["verdict"], "NO_CAMERA2")
            self.assertTrue((session / "report.md").exists())
            self.assertIn("com.autochips.avm", report["packages_of_interest"])
            self.assertIn("com.jetour.dvr", report["packages_of_interest"])
            stages = [s["stage"] for s in report["snapshots"]]
            self.assertIn("idle", stages)
            self.assertIn("avm360", stages)
            self.assertIn("reverse", stages)
            avm = next(s for s in report["snapshots"] if s["stage"] == "avm360")
            self.assertEqual(avm["resumed_activity"], "com.autochips.avm/.AvmActivity")
            self.assertEqual(report["identity"]["adb_id"], "uid=2000(shell) gid=2000(shell)")
            self.assertEqual(report["identity"]["selinux"], "Enforcing")
            md = (session / "report.md").read_text(encoding="utf-8")
            self.assertIn("NO_CAMERA2", md)
            json.loads((session / "report.json").read_text(encoding="utf-8"))

    def test_exclusive_lock_when_clients_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "hu_diag_demo"
            write_demo_session(session)
            idle_cam = session / "02_idle" / "dumpsys_media_camera.txt"
            idle_cam.write_text(
                "Number of camera devices: 4\n"
                "Camera ID: 0\nCamera ID: 1\nCamera ID: 2\nCamera ID: 3\n",
                encoding="utf-8",
            )
            avm_cam = session / "03_avm360" / "dumpsys_media_camera.txt"
            avm_cam.write_text(
                "Number of camera devices: 4\n"
                "Camera ID: 0\nCamera ID: 1\nCamera ID: 2\nCamera ID: 3\n"
                "Client: com.autochips.avm\n"
                "ERROR_CAMERA_IN_USE\n",
                encoding="utf-8",
            )
            report = analyze_session(session)
            self.assertEqual(report["verdict"], "EXCLUSIVE_LOCK")

    def test_cp1251_does_not_crash_on_arrows(self) -> None:
        from hu_diag.console import ascii_safe
        from hu_diag.commands import SNAPSHOT_STAGES
        from hu_diag.analyze import render_markdown, analyze_session

        raw = "USB \u2192 Device \u2192 OK. Cable USB-A \u2014 USB-A. Report."
        encoded = ascii_safe(raw).encode("cp1251")
        self.assertIn(b"->", encoded)
        for _stage, title, how in SNAPSHOT_STAGES:
            ascii_safe(title).encode("cp1251")
            ascii_safe(how).encode("cp1251")
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "hu_diag_demo"
            write_demo_session(session)
            report = analyze_session(session)
            ascii_safe(render_markdown(report)).encode("cp1251")
            ascii_safe(report["summary_ru"]).encode("cp1251")



if __name__ == "__main__":
    unittest.main()
