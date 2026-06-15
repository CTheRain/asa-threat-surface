#!/usr/bin/env python3
"""Offline safety tests for asa_sp_gate — no game process required."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from asa_sp_gate import (  # noqa: E402
    _check_battleye_disabled,
    _check_log_tail,
    JOIN_REMOTE_RE,
)


def _write_log(root: Path, text: str) -> None:
    log_dir = root / "Logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "ShooterGame.log").write_text(text, encoding="utf-8")


class TestLogSignals(unittest.TestCase):
    def test_blocks_remote_join_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_log(
                root,
                "Log: Joining official server 192.168.1.1:7777\n",
            )
            hits = _check_log_tail(root)
            self.assertTrue(hits)
            self.assertNotEqual(hits[0], "ShooterGame.log missing (cannot confirm session type)")

    def test_allows_clean_sp_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_log(
                root,
                "Log: Loading map TheIsland_WP\nLog: BattlEye disabled\n",
            )
            hits = _check_log_tail(root)
            self.assertEqual(hits, [])

    def test_join_regex_matches_official(self) -> None:
        self.assertTrue(JOIN_REMOTE_RE.search("Connected to Official Server"))


class TestBattlEyeGate(unittest.TestCase):
    def _proc(self, cmdline: list[str]) -> MagicMock:
        proc = MagicMock()
        proc.cmdline.return_value = cmdline
        return proc

    @patch("asa_sp_gate.psutil.process_iter", return_value=[])
    def test_cmdline_nobattleye_passes(self, _mock_iter: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_log(root, "Log: started\n")
            ok, reasons, _ = _check_battleye_disabled(self._proc(["ArkAscended.exe", "-NoBattlEye"]), root)
            self.assertTrue(ok)
            self.assertEqual(reasons, [])

    @patch("asa_sp_gate.psutil.process_iter")
    def test_nobattleye_still_blocks_if_be_service_running(self, mock_iter: MagicMock) -> None:
        be_proc = MagicMock()
        be_proc.info = {"name": "BEService.exe"}
        be_proc.pid = 9999
        mock_iter.return_value = [be_proc]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_log(root, "Log: started\n")
            ok, reasons, _ = _check_battleye_disabled(self._proc(["ArkAscended.exe", "-NoBattlEye"]), root)
            self.assertFalse(ok)
            self.assertTrue(any("BEService.exe" in r for r in reasons))

    @patch("asa_sp_gate.psutil.process_iter", return_value=[])
    def test_active_battleye_log_blocks(self, _mock_iter: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_log(root, "Log: BattlEye AntiCheat initialized\n")
            ok, reasons, _ = _check_battleye_disabled(self._proc(["ArkAscended.exe"]), root)
            self.assertFalse(ok)
            self.assertTrue(any("BattlEye appears active" in r for r in reasons))

    @patch("asa_sp_gate.psutil.process_iter", return_value=[])
    def test_disabled_log_passes_without_flag(self, _mock_iter: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_log(root, "Log: Launching with -NoBattlEye\n")
            ok, reasons, _ = _check_battleye_disabled(self._proc(["ArkAscended.exe"]), root)
            self.assertTrue(ok)
            self.assertEqual(reasons, [])

    @patch("asa_sp_gate.psutil.process_iter", return_value=[])
    def test_missing_log_blocks(self, _mock_iter: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ok, reasons, _ = _check_battleye_disabled(self._proc(["ArkAscended.exe"]), root)
            self.assertFalse(ok)
            self.assertTrue(any("BattlEye status unknown" in r for r in reasons))


if __name__ == "__main__":
    raise SystemExit(unittest.main())