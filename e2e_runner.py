"""Run the complete scrape-and-notify workflow with WARP coordination."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Sequence

from paths import DATA_DIR, PROJECT_ROOT
from storage.drivers.atomic_json import AtomicJsonListStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
LOGGER = logging.getLogger(__name__)

CommandRunner = Callable[..., subprocess.CompletedProcess[bytes]]
InputFunction = Callable[[str], str]
SleepFunction = Callable[[float], None]


class E2ERunner:
    """Orchestrate optional reset, scraping, WARP, and alert delivery."""

    STATE_FILES = (
        DATA_DIR.relative_to(PROJECT_ROOT) / "jobs_history.json",
        DATA_DIR.relative_to(PROJECT_ROOT) / "pending_alerts.json",
    )
    WARP_TIMEOUT_SECONDS = 30
    SCRIPT_TIMEOUTS = {
        "scrapers.orchestrator": 900,
        "send_alerts.py": 300,
    }

    def __init__(
        self,
        project_root: str | Path | None = None,
        command_runner: CommandRunner = subprocess.run,
        input_function: InputFunction = input,
        sleep_function: SleepFunction = time.sleep,
        non_interactive: bool = False,
    ) -> None:
        """Inject runtime dependencies and interaction policy."""

        self.project_root = (
            Path(project_root)
            if project_root is not None
            else PROJECT_ROOT
        )
        self.command_runner = command_runner
        self.input_function = input_function
        self.sleep_function = sleep_function
        self.non_interactive = non_interactive

    def run(self, reset_state: bool = False) -> int:
        """Execute the workflow and always attempt to restore WARP."""

        LOGGER.info("🚀 Starting the end-to-end job pipeline.")
        if reset_state:
            self._reset_state()
        else:
            LOGGER.info(
                "🧾 Preserving data/jobs_history.json and "
                "data/pending_alerts.json."
            )

        producer_code: int | None = None
        consumer_code: int | None = None
        pipeline_aborted = False
        interrupted = False
        warp_connected = False

        try:
            warp_disconnected = self._set_warp(
                action="disconnect",
                fallback_prompt=(
                    "⚠️ Please turn OFF Cloudflare WARP manually and "
                    "press ENTER to continue..."
                ),
            )
            if not warp_disconnected:
                pipeline_aborted = True
            else:
                producer_code = self._run_python_script(
                    script_name="scrapers.orchestrator",
                    phase_name="Producer scraping phase",
                    emoji="🔎",
                )

                warp_connected = self._set_warp(
                    action="connect",
                    fallback_prompt=(
                        "⚠️ Please turn ON Cloudflare WARP manually and "
                        "press ENTER to continue..."
                    ),
                )
                if not warp_connected:
                    pipeline_aborted = True
                else:
                    LOGGER.info(
                        "⏳ Waiting 3 seconds for the network to stabilize."
                    )
                    self.sleep_function(3)
                    consumer_code = self._run_python_script(
                        script_name="send_alerts.py",
                        phase_name="Consumer alerting phase",
                        emoji="📨",
                    )
        except KeyboardInterrupt:
            interrupted = True
            LOGGER.critical("🛑 E2E pipeline interrupted by the user.")
        except Exception:
            pipeline_aborted = True
            LOGGER.exception("❌ Unexpected E2E pipeline failure.")
        finally:
            if not warp_connected:
                LOGGER.warning(
                    "🛡️ Restoring Cloudflare WARP before exiting."
                )
                warp_connected = self._set_warp(
                    action="connect",
                    fallback_prompt=(
                        "⚠️ Please turn ON Cloudflare WARP manually and "
                        "press ENTER to continue..."
                    ),
                )

        if interrupted:
            return 130
        if not warp_connected or pipeline_aborted:
            LOGGER.critical("❌ E2E pipeline aborted safely.")
            return 1
        if producer_code == 0 and consumer_code == 0:
            LOGGER.info("✅ E2E pipeline completed successfully.")
            return 0

        LOGGER.error(
            "❌ E2E pipeline completed with errors "
            "(producer=%s, consumer=%s).",
            producer_code,
            consumer_code,
        )
        return 1

    def _reset_state(self) -> None:
        """Atomically reset history and pending alerts to empty arrays."""

        LOGGER.warning(
            "🧹 --reset-state enabled; clearing local workflow state."
        )
        for filename in self.STATE_FILES:
            AtomicJsonListStore(self.project_root / filename).write([])
            LOGGER.info("✅ Reset %s.", filename)

    def _set_warp(self, action: str, fallback_prompt: str) -> bool:
        """Run one bounded WARP command or request a manual switch."""

        state = "OFF" if action == "disconnect" else "ON"
        LOGGER.info("🛡️ Turning Cloudflare WARP %s.", state)
        try:
            result = self.command_runner(
                ["warp-cli", action],
                capture_output=True,
                timeout=self.WARP_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            return self._handle_warp_failure(
                fallback_prompt,
                "warp-cli was not found",
            )
        except subprocess.TimeoutExpired:
            return self._handle_warp_failure(
                fallback_prompt,
                f"warp-cli {action} timed out",
            )
        except Exception as error:
            return self._handle_warp_failure(
                fallback_prompt,
                f"warp-cli {action} crashed: {type(error).__name__}",
            )

        if result.returncode == 0:
            LOGGER.info("✅ Cloudflare WARP is now %s.", state)
            return True

        error_output = self._decode_output(result.stderr)
        return self._handle_warp_failure(
            fallback_prompt,
            (
                f"warp-cli {action} failed with code "
                f"{result.returncode}: "
                f"{error_output or 'no error output'}"
            ),
        )

    def _handle_warp_failure(
        self,
        fallback_prompt: str,
        reason: str,
    ) -> bool:
        """Abort unattended runs or pause interactive runs for recovery."""

        if self.non_interactive:
            LOGGER.critical("❌ %s; non-interactive mode cannot recover.", reason)
            return False

        LOGGER.warning("⚠️ %s; manual action required.", reason)
        try:
            self.input_function(fallback_prompt)
        except EOFError:
            LOGGER.critical("❌ Manual WARP confirmation was unavailable.")
            return False
        return True

    def _run_python_script(
        self,
        script_name: str,
        phase_name: str,
        emoji: str,
    ) -> int:
        """Run one workflow script with the active interpreter and timeout."""

        timeout = self.SCRIPT_TIMEOUTS[script_name]
        LOGGER.info("%s Starting %s: %s", emoji, phase_name, script_name)
        command = (
            [sys.executable, "-m", script_name]
            if script_name == "scrapers.orchestrator"
            else [sys.executable, script_name]
        )
        try:
            result = self.command_runner(
                command,
                cwd=self.project_root,
                timeout=timeout,
            )
        except FileNotFoundError:
            LOGGER.error("❌ Could not start %s.", script_name)
            return 127
        except subprocess.TimeoutExpired:
            LOGGER.error(
                "⏱️ %s timed out after %s seconds.",
                script_name,
                timeout,
            )
            return 124

        if result.returncode == 0:
            LOGGER.info("✅ %s completed successfully.", phase_name)
        else:
            LOGGER.error(
                "❌ %s failed with code %s.",
                phase_name,
                result.returncode,
            )
        return result.returncode

    @staticmethod
    def _decode_output(value: bytes | str | None) -> str:
        """Decode captured subprocess output for diagnostics."""

        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace").strip()
        return value.strip()


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for safe E2E execution."""

    parser = argparse.ArgumentParser(
        description="Run scraping and Telegram delivery with WARP switching.",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help=(
            "Clear data/jobs_history.json and data/pending_alerts.json "
            "before running."
        ),
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Abort instead of prompting when WARP automation fails.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI flags and run the production E2E orchestrator."""

    arguments = build_argument_parser().parse_args(argv)
    runner = E2ERunner(non_interactive=arguments.non_interactive)
    return runner.run(reset_state=arguments.reset_state)


if __name__ == "__main__":
    raise SystemExit(main())
