"""Run dbt with the repository's project and profile."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys

from .config import Settings

LOGGER = logging.getLogger(__name__)


def run_dbt(settings: Settings, command: str = "build", extra: list[str] | None = None) -> int:
    cfg = settings.raw["dbt"]
    project_dir = settings.root / cfg["project_dir"]
    profiles_dir = settings.root / cfg["profiles_dir"]

    executable = shutil.which("dbt")
    if executable is None:
        candidate = os.path.join(os.path.dirname(sys.executable), "Scripts", "dbt.exe")
        executable = candidate if os.path.exists(candidate) else None
    if executable is None:
        raise RuntimeError("dbt is not installed. Run: python -m pip install -r requirements.txt")

    env = os.environ.copy()
    db = settings.database
    env.update({
        "AIR_DB_HOST": str(db["host"]),
        "AIR_DB_PORT": str(db["port"]),
        "AIR_DB_NAME": str(db["dbname"]),
        "AIR_DB_USER": str(db["user"]),
        "AIR_DB_PASSWORD": str(db.get("password") or ""),
    })
    args = [
        executable, command,
        "--project-dir", str(project_dir),
        "--profiles-dir", str(profiles_dir),
        "--target", cfg.get("target", "dev"),
        *(extra or []),
    ]
    LOGGER.info("Running: dbt %s", " ".join(args[1:]))
    return subprocess.call(args, cwd=str(project_dir), env=env)
