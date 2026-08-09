"""Resolve project directories independently of the current working directory."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
LOGS_DIR = PROJECT_ROOT / "logs"
PROMPTS_DIR = CONFIG_DIR / "prompts"
ARTIFACTS_DIR = LOGS_DIR / "artifacts"
