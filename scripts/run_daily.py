#!/usr/bin/env python3
"""Run an optional collector and then process the latest job candidates."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


SKILL_DIR = Path(__file__).resolve().parent.parent


def read_json(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"config must be a JSON object: {path}")
    return data


def resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def format_command(
    command: List[Any],
    input_path: Path,
    preferences_path: Path,
    project_path: Path,
) -> List[str]:
    values = {
        "skill_dir": str(SKILL_DIR),
        "input": str(input_path),
        "preferences": str(preferences_path),
        "project_config": str(project_path),
    }
    return [str(part).format(**values) for part in command]


def assert_fresh_input(path: Path, max_age_minutes: int) -> None:
    if not path.exists():
        raise FileNotFoundError(f"collector did not create input: {path}")
    age_seconds = time.time() - path.stat().st_mtime
    if age_seconds > max_age_minutes * 60:
        raise RuntimeError(
            f"input is stale ({age_seconds / 60:.1f} minutes > {max_age_minutes}): {path}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-config", required=True)
    parser.add_argument("--date")
    parser.add_argument("--scheduled", action="store_true")
    parser.add_argument("--skip-collector", action="store_true")
    parser.add_argument(
        "--heartbeat",
        action="store_true",
        help="only speak up on new or changed jobs (heartbeat push)",
    )
    args = parser.parse_args()

    try:
        project_path = Path(args.project_config).expanduser().resolve()
        project = read_json(project_path)
        project_base = project_path.parent
        paths = project["paths"]
        input_path = resolve(project_base, paths["input"])
        preferences_path = resolve(project_base, paths["preferences"])
        state_dir = resolve(project_base, paths["state_dir"])

        collector = project.get("collector", {})
        command = collector.get("command", [])
        if not isinstance(command, list):
            raise ValueError("collector.command must be an array")

        if args.scheduled and not command:
            raise RuntimeError(
                "scheduled collection requires project collector.command; "
                "configure a background-capable Agent command first"
            )

        if command and not args.skip_collector:
            formatted = format_command(
                command,
                input_path,
                preferences_path,
                project_path,
            )
            working_directory = resolve(
                project_base,
                collector.get("working_directory", ".."),
            )
            input_path.parent.mkdir(parents=True, exist_ok=True)
            completed = subprocess.run(formatted, cwd=working_directory, check=False)
            if completed.returncode != 0:
                raise RuntimeError(
                    f"collector failed with exit code {completed.returncode}"
                )
            assert_fresh_input(
                input_path,
                int(collector.get("max_input_age_minutes", 180)),
            )
        elif not input_path.exists():
            raise FileNotFoundError(
                f"missing input: {input_path}; run the Agent collection step first"
            )

        radar_command = [
            sys.executable,
            str(SKILL_DIR / "scripts" / "radar.py"),
            "run",
            "--input",
            str(input_path),
            "--preferences",
            str(preferences_path),
            "--project-config",
            str(project_path),
            "--state-dir",
            str(state_dir),
            "--output-format",
            "chat",
        ]
        preferences = read_json(preferences_path)
        notify_on_update = bool(
            preferences.get("schedule", {}).get("notify_on_update", False)
        )
        if args.heartbeat or notify_on_update:
            radar_command.append("--heartbeat")
        if args.date:
            radar_command.extend(["--date", args.date])
        completed = subprocess.run(radar_command, check=False)
        return completed.returncode
    except (KeyError, OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
