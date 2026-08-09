"""Tests for the hardened end-to-end workflow orchestrator."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pipeline
from pipeline import E2ERunner


class E2ERunnerTests(unittest.TestCase):
    """Verify orchestration without changing WARP or running live scripts."""

    def setUp(self) -> None:
        """Create isolated state and mocked process dependencies."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temporary_directory.name)
        for filename in E2ERunner.STATE_FILES:
            state_path = self.project_root / filename
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                '["existing-job"]',
                encoding="utf-8",
            )
        self.command_runner = MagicMock()
        self.input_function = MagicMock(return_value="")
        self.sleep_function = MagicMock()
        self.logger_patch = patch("pipeline.LOGGER")
        self.logger = self.logger_patch.start()

    def tearDown(self) -> None:
        """Stop patches and remove isolated state."""

        self.logger_patch.stop()
        self.temporary_directory.cleanup()

    def test_default_run_preserves_state_and_orders_commands(self) -> None:
        """Preserve state unless --reset-state was explicitly requested."""

        self.command_runner.side_effect = self._successful_results()

        exit_code = self._runner().run()

        self.assertEqual(exit_code, 0)
        for filename in E2ERunner.STATE_FILES:
            with open(
                self.project_root / filename,
                "r",
                encoding="utf-8",
            ) as handle:
                self.assertEqual(json.load(handle), ["existing-job"])
        self.assertEqual(
            self.command_runner.call_args_list,
            self._expected_successful_calls(),
        )
        self.input_function.assert_not_called()
        self.sleep_function.assert_called_once_with(3)

    def test_reset_state_flag_clears_both_state_files(self) -> None:
        """Reset state only when the caller explicitly enables it."""

        self.command_runner.side_effect = self._successful_results()

        exit_code = self._runner().run(reset_state=True)

        self.assertEqual(exit_code, 0)
        for filename in E2ERunner.STATE_FILES:
            with open(
                self.project_root / filename,
                "r",
                encoding="utf-8",
            ) as handle:
                self.assertEqual(json.load(handle), [])

    def test_interactive_warp_failures_request_manual_fallback(self) -> None:
        """Prompt after missing disconnect and failed reconnect commands."""

        def run_command(
            command: list[str],
            **kwargs: object,
        ) -> subprocess.CompletedProcess[bytes]:
            """Simulate recoverable WARP automation failures."""

            if command == ["warp-cli", "disconnect"]:
                raise FileNotFoundError("warp-cli")
            if command == ["warp-cli", "connect"]:
                return self._completed(
                    command,
                    return_code=1,
                    stderr=b"service unavailable",
                )
            return self._completed(command)

        self.command_runner.side_effect = run_command

        exit_code = self._runner().run()

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.input_function.call_count, 2)
        self.assertIn(
            "turn OFF Cloudflare WARP",
            self.input_function.call_args_list[0].args[0],
        )
        self.assertIn(
            "turn ON Cloudflare WARP",
            self.input_function.call_args_list[1].args[0],
        )

    def test_non_interactive_warp_failure_aborts_without_input(self) -> None:
        """Abort unattended execution instead of blocking on input."""

        self.command_runner.side_effect = FileNotFoundError("warp-cli")

        exit_code = self._runner(non_interactive=True).run()

        self.assertEqual(exit_code, 1)
        self.input_function.assert_not_called()
        self.assertEqual(
            self.command_runner.call_args_list,
            [
                call(
                    ["warp-cli", "disconnect"],
                    capture_output=True,
                    timeout=30,
                ),
                call(
                    ["warp-cli", "connect"],
                    capture_output=True,
                    timeout=30,
                ),
            ],
        )
        self.logger.critical.assert_called()

    def test_producer_timeout_restores_warp_and_runs_consumer(self) -> None:
        """Handle a bounded producer timeout and reconnect before delivery."""

        self.command_runner.side_effect = [
            self._completed(["warp-cli", "disconnect"]),
            subprocess.TimeoutExpired(
                cmd=[sys.executable, "-m", "scrapers.orchestrator"],
                timeout=900,
            ),
            self._completed(["warp-cli", "connect"]),
            self._completed(
                [sys.executable, "-m", "notifications.dispatcher"]
            ),
        ]

        exit_code = self._runner().run()

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            self.command_runner.call_args_list,
            self._expected_successful_calls(),
        )
        self.logger.error.assert_any_call(
            "⏱️ %s timed out after %s seconds.",
            "scrapers.orchestrator",
            900,
        )

    def test_subprocess_crash_reconnects_warp_in_finally(self) -> None:
        """Reconnect WARP when an unexpected producer exception escapes."""

        self.command_runner.side_effect = [
            self._completed(["warp-cli", "disconnect"]),
            RuntimeError("subprocess crashed"),
            self._completed(["warp-cli", "connect"]),
        ]

        exit_code = self._runner().run()

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            self.command_runner.call_args_list[-1],
            call(
                ["warp-cli", "connect"],
                capture_output=True,
                timeout=30,
            ),
        )

    def test_keyboard_interrupt_reconnects_warp_and_returns_130(self) -> None:
        """Restore WARP after Ctrl+C and report an interrupted exit code."""

        self.command_runner.side_effect = [
            self._completed(["warp-cli", "disconnect"]),
            KeyboardInterrupt(),
            self._completed(["warp-cli", "connect"]),
        ]

        exit_code = self._runner().run()

        self.assertEqual(exit_code, 130)
        self.assertEqual(
            self.command_runner.call_args_list[-1],
            call(
                ["warp-cli", "connect"],
                capture_output=True,
                timeout=30,
            ),
        )

    def test_main_maps_command_line_flags_to_runner(self) -> None:
        """Pass argparse flags into the orchestrator."""

        with patch("pipeline.E2ERunner") as runner_class:
            runner_class.return_value.run.return_value = 0

            exit_code = pipeline.main(
                ["--reset-state", "--non-interactive"]
            )

        self.assertEqual(exit_code, 0)
        runner_class.assert_called_once_with(non_interactive=True)
        runner_class.return_value.run.assert_called_once_with(
            reset_state=True
        )

    def _runner(self, non_interactive: bool = False) -> E2ERunner:
        """Build an orchestrator using only mocked dependencies."""

        return E2ERunner(
            project_root=self.project_root,
            command_runner=self.command_runner,
            input_function=self.input_function,
            sleep_function=self.sleep_function,
            non_interactive=non_interactive,
        )

    def _successful_results(
        self,
    ) -> list[subprocess.CompletedProcess[bytes]]:
        """Return successful results for the complete command sequence."""

        return [
            self._completed(["warp-cli", "disconnect"]),
            self._completed(
                [sys.executable, "-m", "scrapers.orchestrator"]
            ),
            self._completed(["warp-cli", "connect"]),
            self._completed(
                [sys.executable, "-m", "notifications.dispatcher"]
            ),
        ]

    def _expected_successful_calls(self) -> list[call]:
        """Return the complete expected subprocess call sequence."""

        return [
            call(
                ["warp-cli", "disconnect"],
                capture_output=True,
                timeout=30,
            ),
            call(
                [sys.executable, "-m", "scrapers.orchestrator"],
                cwd=self.project_root,
                timeout=900,
            ),
            call(
                ["warp-cli", "connect"],
                capture_output=True,
                timeout=30,
            ),
            call(
                [sys.executable, "-m", "notifications.dispatcher"],
                cwd=self.project_root,
                timeout=300,
            ),
        ]

    @staticmethod
    def _completed(
        command: list[str],
        return_code: int = 0,
        stderr: bytes = b"",
    ) -> subprocess.CompletedProcess[bytes]:
        """Create a deterministic subprocess result."""

        return subprocess.CompletedProcess(
            args=command,
            returncode=return_code,
            stdout=b"",
            stderr=stderr,
        )


if __name__ == "__main__":
    unittest.main()
